"""
supabase_client.py の役割:
  Supabaseの line_users テーブルを読み書きします。
  テーブルの中身(1ユーザー1行):
    line_user_hash  … LINEユーザーIDをSHA-256でハッシュ化したもの(主キー)
    conversation_id … Difyの会話ID
    updated_at      … 最後にやり取りした時刻
  Vercelは実行のたびにメモリが消えるため、会話IDをここに保存しておきます。
"""
from datetime import datetime, timezone

import httpx

from config import get_env


def _base() -> tuple[str, dict]:
    """接続先URLと認証ヘッダーを作る。"""
    url = get_env("SUPABASE_URL").rstrip("/") + "/rest/v1/line_users"
    # sb_secret_ のキーは apikey ヘッダーだけで使う
    headers = {"apikey": get_env("SUPABASE_SECRET_KEY"), "Content-Type": "application/json"}
    return url, headers


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_user(user_hash: str) -> dict | None:
    """ユーザーの行を取得。無ければ None。"""
    url, headers = _base()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            url,
            headers=headers,
            params={
                "line_user_hash": f"eq.{user_hash}",
                "select": "conversation_id,updated_at",
            },
        )
        res.raise_for_status()
    rows = res.json()
    return rows[0] if rows else None


async def save_user(user_hash: str, conversation_id: str | None) -> None:
    """会話IDと更新時刻を保存(行が無ければ作り、あれば上書き)。"""
    url, headers = _base()
    headers["Prefer"] = "resolution=merge-duplicates"
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            url,
            headers=headers,
            json={
                "line_user_hash": user_hash,
                "conversation_id": conversation_id,
                "updated_at": _now_iso(),
            },
        )
        res.raise_for_status()


async def touch_user(user_hash: str) -> None:
    """更新時刻だけを「今」にする(「前回の続き」で24時間の期限を延ばすため)。"""
    url, headers = _base()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.patch(
            url,
            headers=headers,
            params={"line_user_hash": f"eq.{user_hash}"},
            json={"updated_at": _now_iso()},
        )
        res.raise_for_status()


async def insert_chat_log(
    user_hash: str, question: str, answer: str, conversation_id: str | None
) -> None:
    """会話ログ(分析用)を chat_logs テーブルに1件追加する。"""
    url, headers = _base()
    url = url.replace("/line_users", "/chat_logs")
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            url,
            headers=headers,
            json={
                "line_user_hash": user_hash,
                "question": question,
                "answer": answer,
                "conversation_id": conversation_id,
            },
        )
        res.raise_for_status()


async def keepalive_read() -> int:
    """Supabaseが停止しないよう、テーブルを1行だけ軽く読む。"""
    url, headers = _base()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(url, headers=headers, params={"select": "line_user_hash", "limit": 1})
        res.raise_for_status()
    return len(res.json())
