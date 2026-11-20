"""
test_dify.py の役割:
  ローカルで「Difyに質問して回答が返ってくるか」を確認します。
  使い方(プロジェクトのフォルダで):
    python scripts/test_dify.py
    python scripts/test_dify.py "施術の所要時間を教えて"
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dify_client import DifyError, ask_dify  # noqa: E402
from line_client import hash_user_id  # noqa: E402


async def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "営業時間を教えてください"
    print(f"質問: {question}")
    try:
        answer, conv_id = await ask_dify(question, hash_user_id("test-user"), None)
    except (DifyError, RuntimeError) as e:
        print(f"NG: {e}")
        sys.exit(1)
    print(f"OK 回答:\n{answer}\n会話ID: {conv_id}")


asyncio.run(main())
