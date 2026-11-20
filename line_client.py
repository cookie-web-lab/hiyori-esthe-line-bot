"""
line_client.py の役割:
  LINEとのやり取りを担当します。
  1. 署名の検証 … 届いたリクエストが本当にLINEからのものか確認する
  2. 返信       … reply API で返事を送る(push API は使いません)
"""
import base64
import hashlib
import hmac

import httpx

from config import LINE_MAX_TEXT_LENGTH, get_env

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


def verify_signature(body: bytes, signature: str) -> bool:
    """x-line-signature を、チャネルシークレットで検証する。"""
    secret = get_env("LINE_CHANNEL_SECRET").encode()
    digest = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    # compare_digest は、時間差から答えを推測されないための比較方法
    return hmac.compare_digest(expected, signature or "")


def hash_user_id(line_user_id: str) -> str:
    """LINEのユーザーIDをSHA-256でハッシュ化する(元のIDは保存・送信しない)。"""
    return hashlib.sha256(line_user_id.encode("utf-8")).hexdigest()


async def reply_text(reply_token: str, text: str) -> None:
    """reply API で返信する。長すぎる場合は5000文字で切る。"""
    token = get_env("LINE_CHANNEL_ACCESS_TOKEN")
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            LINE_REPLY_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": text[:LINE_MAX_TEXT_LENGTH]}],
            },
        )
        res.raise_for_status()
