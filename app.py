"""
app.py の役割:
  サーバーの本体です。Vercelが最初に読み込むファイルです。
  入口(URL)は2つ:
    POST /callback       … LINEからのメッセージを受け取る(Webhook)
    GET  /api/keepalive  … Vercel Cron が1日1回呼ぶ。Supabaseの停止防止
"""
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request

import config
from config import get_env
from dify_client import DifyError, ask_dify
from line_client import hash_user_id, reply_text, verify_signature
from supabase_client import get_recent_questions, get_user, insert_chat_log, keepalive_read, save_user, touch_user

logger = logging.getLogger("linebot")
app = FastAPI()


def _is_fresh(updated_at: str | None) -> bool:
    """最後のやり取りから24時間以内なら True。"""
    if not updated_at:
        return False
    last = datetime.fromisoformat(updated_at)
    return datetime.now(timezone.utc) - last < timedelta(hours=config.CONVERSATION_TTL_HOURS)


async def log_chat(user_hash: str, question: str, answer: str, conversation_id: str | None) -> None:
    """会話ログを保存する。失敗してもLINEへの返信には影響させない(例外を握りつぶす)。"""
    try:
        await insert_chat_log(user_hash, question, answer, conversation_id)
    except Exception:
        logger.exception("chat_logs の保存に失敗しました(返信には影響なし)")


_AFTER_RESUME = re.compile(r"^[\s、,。:：]*(?:で(?![すき]))?[\s、,。:：]*")
_NON_TEXT_LOG = re.compile(r"^\[[a-z_]+\]$")  # スタンプなどのログ(例: [sticker])


def split_resume(text: str) -> str | None:
    """「前回の続き」で始まるなら、その後ろの文章(質問)を返す。始まらなければ None。
    例: 「前回の続きで料金は?」→「料金は?」/「前回の続き」だけ → 空文字"""
    if not text.startswith(config.CMD_RESUME):
        return None
    return _AFTER_RESUME.sub("", text[len(config.CMD_RESUME):], count=1).strip()


def pick_last_topic(questions: list[str]) -> str | None:
    """新しい順の質問リストから、最後の「通常の質問」を選ぶ(合言葉・スタンプは飛ばす)。"""
    for q in questions:
        q = q.strip()
        if q in (config.CMD_RESUME, config.CMD_RESTART) or _NON_TEXT_LOG.match(q):
            continue
        rest = split_resume(q)  # 「前回の続きで料金は?」は後ろの「料金は?」を使う
        if rest is not None:
            q = rest
        if q:
            return q
    return None


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


async def handle_text(reply_token: str, line_user_id: str, text: str) -> None:
    """テキストメッセージ1件を処理して返信し、最後にログを保存する。"""
    user_hash = hash_user_id(line_user_id)
    text = text.strip()
    row = await get_user(user_hash)
    saved_id = row.get("conversation_id") if row else None

    # --- 特別コマンド:「前回の続き」(これだけ送られたとき)---
    follow_up = split_resume(text)
    if follow_up == "":
        if saved_id:
            await touch_user(user_hash)  # 24時間の期限を今からに延ばす
            topic = pick_last_topic(await get_recent_questions(user_hash))
            if topic:
                msg = config.MSG_RESUME_WITH_TOPIC.format(
                    topic=shorten(topic, config.RESUME_TOPIC_MAX_LENGTH)
                )
            else:
                msg = config.MSG_RESUME
        else:
            msg = config.MSG_RESUME_NOT_FOUND
        await reply_text(reply_token, msg)
        await log_chat(user_hash, text, msg, saved_id)
        return

    # --- 特別コマンド:「最初から」---
    if text == config.CMD_RESTART:
        await save_user(user_hash, None)  # 会話IDを消す → 次の質問は新しい会話
        await reply_text(reply_token, config.MSG_RESTART)
        await log_chat(user_hash, text, config.MSG_RESTART, None)
        return

    # --- 通常の質問 ---
    if follow_up:
        # 「前回の続きで料金は?」→ 前回の会話IDを(24時間を過ぎていても)使い、後ろの文章を質問にする
        conversation_id = saved_id
        question = follow_up
    else:
        # 24時間以内なら続き、過ぎていれば新しい会話
        conversation_id = saved_id if (saved_id and _is_fresh(row.get("updated_at"))) else None
        question = text
    try:
        try:
            answer, new_id = await ask_dify(question, user_hash, conversation_id)
        except DifyError as e:
            # 保存していた会話がDify側で消えている場合は、新しい会話でやり直す
            if conversation_id and e.status_code == 404:
                answer, new_id = await ask_dify(question, user_hash, None)
            else:
                raise
    except DifyError as e:
        logger.error("Dify error: %s", e)
        await reply_text(reply_token, config.MSG_DIFY_ERROR)
        await log_chat(user_hash, text, config.MSG_DIFY_ERROR, conversation_id)
        return

    await save_user(user_hash, new_id or conversation_id)
    await reply_text(reply_token, answer)
    await log_chat(user_hash, text, answer, new_id or conversation_id)


@app.post("/callback")
async def callback(request: Request):
    body = await request.body()
    # 1. 署名の検証(LINE以外からのアクセスを拒否)
    if not verify_signature(body, request.headers.get("x-line-signature", "")):
        raise HTTPException(status_code=400, detail="invalid signature")

    # 2. イベントを1件ずつ処理
    for event in json.loads(body).get("events", []):
        if event.get("type") != "message":
            continue
        reply_token = event.get("replyToken")
        line_user_id = event.get("source", {}).get("userId")
        if not reply_token or not line_user_id:
            continue
        try:
            message = event.get("message", {})
            if message.get("type") == "text":
                await handle_text(reply_token, line_user_id, message.get("text", ""))
            else:
                # スタンプ・画像など
                await reply_text(reply_token, config.MSG_NON_TEXT)
                await log_chat(
                    hash_user_id(line_user_id),
                    f"[{message.get('type', 'unknown')}]",
                    config.MSG_NON_TEXT,
                    None,
                )
        except Exception:
            # 1件の失敗で全体を止めない(LINEに200を返し、再送を避ける)
            logger.exception("event handling failed")
    return {"status": "ok"}


@app.get("/api/keepalive")
async def keepalive(request: Request):
    # Vercel Cron は「Authorization: Bearer <CRON_SECRET>」を付けて呼んでくる
    expected = f"Bearer {get_env('CRON_SECRET')}"
    if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
        raise HTTPException(status_code=401, detail="unauthorized")
    count = await keepalive_read()
    return {"status": "ok", "rows_read": count}
