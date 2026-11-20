"""
dify_client.py の役割:
  DifyのチャットAPIに質問を送り、回答を受け取ります。
  response_mode は blocking(回答が完成してから一括で受け取る方式)です。
"""
import httpx

from config import get_env

DIFY_URL = "https://api.dify.ai/v1/chat-messages"


class DifyError(Exception):
    """Difyとのやり取りで問題が起きたことを表す。"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


async def ask_dify(query: str, user_hash: str, conversation_id: str | None) -> tuple[str, str]:
    """
    Difyに質問する。
    戻り値: (回答テキスト, 会話ID)
    conversation_id が None のときは新しい会話になる。
    """
    api_key = get_env("DIFY_API_KEY")
    payload = {
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "user": user_hash,  # ハッシュ化したIDを使う
        "conversation_id": conversation_id or "",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                DIFY_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
    except httpx.HTTPError as e:
        raise DifyError(f"Difyに接続できません: {type(e).__name__}") from e

    if res.status_code != 200:
        raise DifyError(f"Difyがエラーを返しました: {res.status_code}", res.status_code)

    data = res.json()
    answer = data.get("answer", "")
    if not answer:
        raise DifyError("Difyの回答が空です")
    return answer, data.get("conversation_id", "")
