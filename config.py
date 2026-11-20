"""
config.py の役割:
  鍵(パスワードのようなもの)を「環境変数」から読み込む場所です。
  鍵そのものはコードに書きません(GitHubに公開されると危険なため)。
  - ローカル:  .env ファイルに書く(テスト用スクリプトが自動で読み込みます)
  - Vercel:   管理画面の Environment Variables に登録する
"""
import os

# 会話を「続き」として扱う時間(24時間)
CONVERSATION_TTL_HOURS = 24

# LINEの1メッセージの文字数上限
LINE_MAX_TEXT_LENGTH = 5000

# ユーザーに返す固定メッセージ
MSG_NON_TEXT = "文字でご質問ください"
MSG_DIFY_ERROR = "ただいま混み合っています。少し時間をおいて送ってください"
MSG_RESUME = "前回のご相談の続きからお答えします。ご質問をどうぞ"
MSG_RESUME_NOT_FOUND = "前回のご相談が見つかりませんでした。新しいご相談として承ります。ご質問をどうぞ"
MSG_RESUME_WITH_TOPIC = "前回は「{topic}」についてご相談いただいていました。続きのご質問をどうぞ。"
MSG_RESTART = "新しいご相談として承ります。ご質問をどうぞ"

# ユーザーが送る特別なコマンド
CMD_RESUME = "前回の続き"
CMD_RESTART = "最初から"

# 「前回は「〇〇」について…」に出す質問の最大文字数(超えたら「…」で省略)
RESUME_TOPIC_MAX_LENGTH = 30


def get_env(name: str) -> str:
    """環境変数を読む。未設定なら分かりやすいエラーにする。"""
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません")
    return value
