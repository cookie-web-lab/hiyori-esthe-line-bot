"""
test_supabase.py の役割:
  ローカルで「Supabaseに接続でき、line_users テーブルを読み書きできるか」を確認します。
  使い方(プロジェクトのフォルダで):
    python scripts/test_supabase.py
  テスト用の1行を書き込み、読み取り、最後に削除します。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import supabase_client as sb  # noqa: E402


async def main():
    test_hash = "test_connection_check"
    try:
        print(f"読み込み: OK (行数 {await sb.keepalive_read()})")
        await sb.save_user(test_hash, "dummy-conversation-id")
        row = await sb.get_user(test_hash)
        print(f"書き込み・取得: {'OK' if row else 'NG'}")
        url, headers = sb._base()
        async with httpx.AsyncClient(timeout=10) as client:
            await client.delete(url, headers=headers, params={"line_user_hash": f"eq.{test_hash}"})
        print("テスト行の削除: OK")

        # chat_logs テーブルの確認(書き込み → 削除)
        await sb.insert_chat_log(test_hash, "テスト質問", "テスト回答", "dummy-conversation-id")
        async with httpx.AsyncClient(timeout=10) as client:
            logs_url = url.replace("/line_users", "/chat_logs")
            res = await client.get(
                logs_url, headers=headers, params={"line_user_hash": f"eq.{test_hash}", "select": "id"}
            )
            res.raise_for_status()
            print(f"chat_logs 書き込み・取得: {'OK' if res.json() else 'NG'}")
            await client.delete(logs_url, headers=headers, params={"line_user_hash": f"eq.{test_hash}"})
        print("chat_logs テスト行の削除: OK")
    except Exception as e:
        print(f"NG: {type(e).__name__}: {e}")
        sys.exit(1)


asyncio.run(main())
