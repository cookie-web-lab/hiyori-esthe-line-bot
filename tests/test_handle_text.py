"""
handle_text(メッセージ1件の処理)の単体テスト。
Supabase・Dify・LINEは本物につながず、偽物(モック)に差し替えて動きだけを確認します。
使い方(プロジェクトのフォルダで):
    python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402
import config  # noqa: E402


class SupabaseReadFailureTest(unittest.IsolatedAsyncioTestCase):
    """line_users の読み込みに失敗しても、新しい会話としてDifyに質問し、LINEに返信する。"""

    def setUp(self):
        patches = {
            "get_user": patch.object(app, "get_user", AsyncMock(side_effect=RuntimeError("supabase down"))),
            "ask_dify": patch.object(app, "ask_dify", AsyncMock(return_value=("回答です", "new-conv"))),
            "reply_text": patch.object(app, "reply_text", AsyncMock()),
            "save_user": patch.object(app, "save_user", AsyncMock()),
            "touch_user": patch.object(app, "touch_user", AsyncMock()),
            "insert_chat_log": patch.object(app, "insert_chat_log", AsyncMock()),
        }
        self.m = {name: p.start() for name, p in patches.items()}
        self.addCleanup(patch.stopall)

    async def test_通常の質問は新しい会話としてDifyに送り返信する(self):
        with self.assertLogs("linebot", level="ERROR") as logs:
            await app.handle_text("token", "U123", "営業時間は?")
        self.assertTrue(any("line_users の読み込みに失敗" in m for m in logs.output))  # ログに出る
        args = self.m["ask_dify"].await_args.args
        self.assertEqual(args[0], "営業時間は?")
        self.assertIsNone(args[2])  # 会話IDなし = 新しい会話
        self.m["reply_text"].assert_awaited_once_with("token", "回答です")

    async def test_前回の続きで質問も新しい会話として返信する(self):
        with self.assertLogs("linebot", level="ERROR"):
            await app.handle_text("token", "U123", "前回の続きで料金は?")
        args = self.m["ask_dify"].await_args.args
        self.assertEqual(args[0], "料金は?")
        self.assertIsNone(args[2])
        self.m["reply_text"].assert_awaited_once_with("token", "回答です")

    async def test_前回の続きだけなら見つからない案内を返信する(self):
        with self.assertLogs("linebot", level="ERROR"):
            await app.handle_text("token", "U123", "前回の続き")
        self.m["ask_dify"].assert_not_awaited()
        self.m["reply_text"].assert_awaited_once_with("token", config.MSG_RESUME_NOT_FOUND)


class NormalFlowTest(unittest.IsolatedAsyncioTestCase):
    """読み込みが成功するときは、保存された会話IDで続ける(これまでどおり)。"""

    async def test_保存された会話IDで続ける(self):
        from datetime import datetime, timezone

        row = {"conversation_id": "saved-conv", "updated_at": datetime.now(timezone.utc).isoformat()}
        with patch.object(app, "get_user", AsyncMock(return_value=row)), \
             patch.object(app, "ask_dify", AsyncMock(return_value=("回答です", "saved-conv"))) as ask, \
             patch.object(app, "reply_text", AsyncMock()) as reply, \
             patch.object(app, "save_user", AsyncMock()), \
             patch.object(app, "insert_chat_log", AsyncMock()):
            await app.handle_text("token", "U123", "営業時間は?")
        self.assertEqual(ask.await_args.args[2], "saved-conv")
        reply.assert_awaited_once_with("token", "回答です")


if __name__ == "__main__":
    unittest.main()
