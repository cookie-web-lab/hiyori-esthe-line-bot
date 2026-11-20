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


def _fresh_row():
    from datetime import datetime, timezone

    return {"conversation_id": "saved-conv", "updated_at": datetime.now(timezone.utc).isoformat()}


class SupabaseWriteFailureTest(unittest.IsolatedAsyncioTestCase):
    """読み込みは成功しても、そのあとの保存・取得が失敗するケース。どこで失敗しても返信は必ず行う。"""

    def _patch(self, **overrides):
        base = {
            "get_user": AsyncMock(return_value=_fresh_row()),
            "ask_dify": AsyncMock(return_value=("回答です", "saved-conv")),
            "reply_text": AsyncMock(),
            "save_user": AsyncMock(),
            "touch_user": AsyncMock(),
            "get_recent_questions": AsyncMock(return_value=["営業時間は?"]),
            "insert_chat_log": AsyncMock(),
        }
        base.update(overrides)
        for name, mock in base.items():
            patch.object(app, name, mock).start()
        self.addCleanup(patch.stopall)
        return base

    async def test_回答後の会話ID保存に失敗しても回答を返信する(self):
        m = self._patch(save_user=AsyncMock(side_effect=RuntimeError("db down")))
        with self.assertLogs("linebot", level="ERROR"):
            await app.handle_text("token", "U123", "営業時間は?")
        m["reply_text"].assert_awaited_once_with("token", "回答です")

    async def test_前回の続き_更新に失敗しても返信する(self):
        m = self._patch(touch_user=AsyncMock(side_effect=RuntimeError("db down")))
        with self.assertLogs("linebot", level="ERROR"):
            await app.handle_text("token", "U123", "前回の続き")
        m["reply_text"].assert_awaited_once_with(
            "token", config.MSG_RESUME_WITH_TOPIC.format(topic="営業時間は?")
        )

    async def test_前回の続き_最後の質問の取得に失敗したら固定メッセージで返信する(self):
        m = self._patch(get_recent_questions=AsyncMock(side_effect=RuntimeError("db down")))
        with self.assertLogs("linebot", level="ERROR"):
            await app.handle_text("token", "U123", "前回の続き")
        m["reply_text"].assert_awaited_once_with("token", config.MSG_RESUME)

    async def test_最初から_保存に成功すれば新しい相談の案内(self):
        m = self._patch()
        await app.handle_text("token", "U123", "最初からお願い")
        m["reply_text"].assert_awaited_once_with("token", config.MSG_RESTART)

    async def test_最初から_会話IDを消せなくても返信する(self):
        # 消せていないのに「新しい相談」と案内しないよう、再送をお願いする文面を返す
        m = self._patch(save_user=AsyncMock(side_effect=RuntimeError("db down")))
        with self.assertLogs("linebot", level="ERROR"):
            await app.handle_text("token", "U123", "最初から")
        m["reply_text"].assert_awaited_once_with("token", config.MSG_DIFY_ERROR)

    async def test_Supabaseが全部落ちていても返信する(self):
        down = lambda: AsyncMock(side_effect=RuntimeError("db down"))  # noqa: E731
        for text, expected in [
            ("営業時間は?", "回答です"),
            ("前回の続きで料金は?", "回答です"),
            ("前回の続き", config.MSG_RESUME_NOT_FOUND),
            ("最初からお願い", config.MSG_DIFY_ERROR),
        ]:
            with self.subTest(text=text):
                m = self._patch(
                    get_user=down(), save_user=down(), touch_user=down(),
                    get_recent_questions=down(), insert_chat_log=down(),
                )
                with self.assertLogs("linebot", level="ERROR"):
                    await app.handle_text("token", "U123", text)
                m["reply_text"].assert_awaited_once_with("token", expected)
                patch.stopall()


class NormalFlowTest(unittest.IsolatedAsyncioTestCase):
    """読み込みが成功するときは、保存された会話IDで続ける(これまでどおり)。"""

    async def test_保存された会話IDで続ける(self):
        with patch.object(app, "get_user", AsyncMock(return_value=_fresh_row())), \
             patch.object(app, "ask_dify", AsyncMock(return_value=("回答です", "saved-conv"))) as ask, \
             patch.object(app, "reply_text", AsyncMock()) as reply, \
             patch.object(app, "save_user", AsyncMock()), \
             patch.object(app, "insert_chat_log", AsyncMock()):
            await app.handle_text("token", "U123", "営業時間は?")
        self.assertEqual(ask.await_args.args[2], "saved-conv")
        reply.assert_awaited_once_with("token", "回答です")


if __name__ == "__main__":
    unittest.main()
