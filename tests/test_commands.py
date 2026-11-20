"""
合言葉(「前回の続き」「最初から」)の判定ロジックの単体テストです。
使い方(プロジェクトのフォルダで):
    python -m unittest discover -s tests -v
外部サービス(LINE・Dify・Supabase)には接続しません。鍵も不要です。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import is_restart, pick_last_topic, shorten, split_resume  # noqa: E402

# 合言葉のあとに付けても「合言葉だけ」と同じ扱いになる言葉
FILLERS = [
    "", "お願い", "お願いします", "からお願い", "からお願いします", "でお願い",
    "にして", "にしてください", "から", "で", "。", "!", "！", "、お願いします",
    "からお願いします。", "でお願いします!", " お願い", "ください",
]


class ResumeTest(unittest.TestCase):
    def test_合言葉だけ_またはお願いの言葉だけなら空文字(self):
        for f in FILLERS:
            with self.subTest(text="前回の続き" + f):
                self.assertEqual(split_resume("前回の続き" + f), "")

    def test_後ろに質問があれば質問部分を返す(self):
        cases = {
            "前回の続きで料金は?": "料金は?",
            "前回の続き、料金は?": "料金は?",
            "前回の続き 料金は教えて": "料金は教えて",
            "前回の続きですか": "ですか",  # 「で」+「す」は質問の一部
            "前回の続きできますか": "できますか",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(split_resume(text), expected)

    def test_前回の続きで始まらなければNone(self):
        for text in ["営業時間は?", "最初から", "続き", "あの前回の続き"]:
            with self.subTest(text=text):
                self.assertIsNone(split_resume(text))


class RestartTest(unittest.TestCase):
    def test_合言葉_またはお願いの言葉だけならTrue(self):
        for f in FILLERS:
            with self.subTest(text="最初から" + f):
                self.assertTrue(is_restart("最初から" + f))

    def test_ほかの文章が続けばFalse(self):
        for text in ["最初から教えて", "最初から料金は?", "営業時間は?", "前回の続き", "お願い"]:
            with self.subTest(text=text):
                self.assertFalse(is_restart(text))


class PickLastTopicTest(unittest.TestCase):
    def test_合言葉やスタンプは飛ばす(self):
        qs = ["前回の続きからお願い", "[sticker]", "最初からお願い", "営業時間は?"]
        self.assertEqual(pick_last_topic(qs), "営業時間は?")

    def test_前回の続きで始まる質問は後ろの文章を使う(self):
        self.assertEqual(pick_last_topic(["前回の続きで料金は?", "営業時間は?"]), "料金は?")

    def test_通常の質問が無ければNone(self):
        self.assertIsNone(pick_last_topic(["前回の続き", "[sticker]", "最初からお願いします"]))


class ShortenTest(unittest.TestCase):
    def test_30文字以内はそのまま_超えたら省略(self):
        self.assertEqual(shorten("あ" * 30, 30), "あ" * 30)
        self.assertEqual(shorten("あ" * 31, 30), "あ" * 30 + "…")


if __name__ == "__main__":
    unittest.main()
