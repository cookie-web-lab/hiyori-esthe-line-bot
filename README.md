# hiyori-esthe-line-bot

架空のエステサロン「private esthe salon hiyori」への問い合わせに、**LINE上でAIが24時間答える**ボットです。
LINEで届いた質問をDifyのチャットボットに渡し、回答をLINEへ返す中継サーバー(Python / FastAPI / Vercel)を作りました。

> **課題1で作った Dify のチャットボット([hiyori-esthe-chatbot](https://github.com/cookie-web-lab/hiyori-esthe-chatbot))を、LINEにつなげたものです。**
> 回答の中身(ナレッジ・プロンプト)は課題1のボットで、このリポジトリは「LINEとDifyをつなぐ部分」を担当します。

## 使った技術

| 技術 | 使い道 |
|---|---|
| LINE Messaging API | ユーザーとのやり取り(メッセージの受信と reply API での返信)、リッチメニュー |
| Dify | 質問への回答づくり(課題1のチャットボットをAPIで利用) |
| FastAPI(Python) | LINEからのWebhookを受け取る中継サーバー |
| Vercel | サーバーの公開、Cron Jobs(定期実行) |
| Supabase(PostgreSQL) | 会話IDの保存、会話ログの保存 |

## 全体の仕組み

```
LINEユーザー → LINE → [Vercel上の中継サーバー] → Dify(回答を作る)
                              │
                              └→ Supabase(会話ID・会話ログを記録)
LINEユーザー ← LINE ← 中継サーバーが reply API で返信
```

## 工夫した点

### 会話の続き(24時間で自動リセット + 合言葉)
- Vercelは実行のたびにメモリが消えるため、Difyの会話IDを Supabase の `line_users` に保存しています。
- 前回のやり取りから**24時間以内**なら前の会話の続きとして回答し、過ぎたら**自動で新しい会話**にします。
- 合言葉で、ユーザー自身が会話を切り替えられます(下の表)。「お願い」「からお願いします」など、自然な言い方も合言葉として認識します。

| ユーザーの操作 | 動き |
|---|---|
| 普通の質問(前回から24時間以内) | 前の会話の続きとして回答 |
| 普通の質問(24時間より後) | 新しい会話として回答 |
| 「前回の続き」(「前回の続きからお願い」なども同じ) | 24時間を過ぎていても、保存された最後の会話IDで続ける。「前回は「(最後の質問)」についてご相談いただいていました。続きのご質問をどうぞ。」と返信(質問が長いときは30文字で省略) |
| 「前回の続きで料金は?」 | 「前回の続き」より後ろの「料金は?」を、前回の会話IDでDifyに質問する |
| 「最初から」(「最初からお願い」なども同じ) | 24時間以内でも新しい会話にする。「新しいご相談として承ります。ご質問をどうぞ」と返信 |

保存された会話が無いときに「前回の続き」と送ると、新しい相談として案内します。

### ユーザーIDのハッシュ化
LINEのユーザーIDは SHA-256 でハッシュ化し、Supabaseへの保存とDifyの `user` にはハッシュ値だけを使います。元のIDはどこにも保存・送信しないので、データが漏れても誰のものか分かりにくくなります。

### 会話ログの保存(あとで分析するため)
返信のたびに、質問・回答・会話IDを Supabase の `chat_logs` に1件ずつ保存します。「よくある質問は何か」「答えられなかった質問は何か」を、あとでナレッジの改善に使えます。ログの保存に失敗しても、LINEへの返信には影響しません。

### Supabaseの停止対策(Vercel Cronで1日1回アクセス)
Supabaseの無料プランは、一定期間アクセスがないと停止します。Vercel Cron Jobs で `/api/keepalive` を1日1回呼び、テーブルを1行読むようにしました。このURLは `CRON_SECRET` による認証付きで、鍵のない人が呼ぶと `401` を返します(デプロイ後に、鍵ありで `200`、鍵なしで `401` になることを確認済み)。

### エラー時もLINEに返信する設計
- Difyがエラーのときは、無言にせず「ただいま混み合っています。少し時間をおいて送ってください」と返します。
- Dify側で保存済みの会話が消えていた場合(404)は、新しい会話で自動的にやり直します。
- スタンプ・画像には「文字でご質問ください」と返します。
- 1件の処理が失敗しても、LINEには必ず `200` を返します(LINEの再送による二重処理を防ぐため)。
- 返信は reply API のみで、push API は使いません(無料プランの通数制限への対策)。
- 署名(`x-line-signature`)を検証し、LINE以外からのアクセスは拒否します。

### Web版と同じ6つのカテゴリを、LINEのリッチメニューにした
課題1のWeb版にある6つのカテゴリボタンを、LINEのリッチメニューとして用意しました。トーク画面の下に常に表示されるので、文字入力が苦手な人でもタップだけで質問を始められます。

1. 料金・支払い
2. お悩み別おすすめメニュー
3. 施術内容
4. 痛み・肌への影響
5. 予約・アクセス
6. 初めてのご来店

## 動作確認で見つかった問題と、その直し方

実際にLINEで試して見つけた問題を、1つずつ直しました。

| 見つかった問題 | 直し方 |
|---|---|
| 「前回の続き」とだけ返ってきて、何の続きなのか分からない | `chat_logs` から最後の質問を取り出し、「前回は「〇〇」についてご相談いただいていました」と返すようにした。合言葉やスタンプは飛ばして、最後の**普通の質問**を使う |
| 「前回の続きで料金は?」のように質問を続けて書いても、続きの質問として扱われなかった | 「前回の続き」で始まる文は、後ろの文章だけを質問にして、前回の会話IDでDifyに送るようにした |
| **合言葉の判定が厳しすぎた。** 「最初からお願い」は合言葉と認識されずDifyに送られ、「前回の続きからお願い」は「からお願い」が質問としてDifyに送られて変な回答になった | 完全一致の判定をやめた。合言葉の後ろに「お願い」「からお願いします」「にしてください」「で」「。」などの**お願いの言葉だけ**が付いているときは、合言葉だけのときと同じ動きにした。ほかの文章が続くときは、今までどおり質問としてDifyに送る。ただし「前回の続きですか」のような普通の言葉を壊さないよう、「で」の直後が「す」「き」のときは質問の一部として残す |
| **Difyのプロンプトのルール同士がぶつかった。** すでに悩みを伝えているのに、聞き返してしまった | プロンプトのルール同士が矛盾していたのが原因。ルールの**優先順位を整理**した |

合言葉の判定ロジックには単体テストを書いています(外部サービスに接続しないため、鍵なしで実行できます)。

```bash
python -m unittest discover -s tests -v
```

## 今後の改善予定

- 会話ログ(`chat_logs`)を分析して、**よくある質問**と**答えられなかった質問**を把握し、ナレッジやプロンプトを改善する。

## ファイルの役割

| ファイル | 役割 |
|---|---|
| `app.py` | 本体。`/callback`(LINE受信)と `/api/keepalive`(Cron用)、合言葉の判定 |
| `line_client.py` | 署名検証、IDのハッシュ化、reply API |
| `dify_client.py` | Difyへの質問 |
| `supabase_client.py` | `line_users`(会話ID)と `chat_logs`(会話ログ)の読み書き |
| `config.py` | 環境変数の読み込みと固定メッセージ |
| `vercel.json` | Cron Jobsの設定(1日1回) |
| `scripts/test_dify.py` | Difyの動作確認 |
| `scripts/test_supabase.py` | Supabaseの接続確認 |
| `tests/test_commands.py` | 合言葉の判定の単体テスト |

---

以下は、同じ構成を自分で作るときのセットアップ手順です。

## セットアップ 1. Supabaseのテーブル作成

Supabaseのダッシュボード → **SQL Editor** で次を実行します。

```sql
create table public.line_users (
  line_user_hash  text primary key,          -- LINEユーザーIDのSHA-256
  conversation_id text,                      -- Difyの会話ID(「最初から」で空になる)
  updated_at      timestamptz not null default now()
);

-- 会話ログ(分析用):返信のたびに1件ずつ保存される
create table public.chat_logs (
  id              bigint generated always as identity primary key,  -- 自動連番
  created_at      timestamptz not null default now(),               -- 作成日時
  line_user_hash  text not null,                                    -- ハッシュ化したユーザーID
  question        text,                                             -- ユーザーの質問
  answer          text,                                             -- ボットの回答
  conversation_id text                                              -- Difyの会話ID
);

-- 両方のテーブルでRLSを有効にする。ポリシーは作らない
-- (=外部の公開キーからは一切読み書きできない。サーバーのsecretキーはRLSを無視して使える)
alter table public.line_users enable row level security;
alter table public.chat_logs  enable row level security;
```

`chat_logs` の保存に失敗しても、LINEへの返信には影響しません(エラーはVercelのログに残ります)。
「前回の続き」「最初から」などの合言葉や、スタンプへの返信(質問欄は `[sticker]` のように記録)も保存されます。

**Project Settings → API Keys** から次を控えます。
- Project URL → `SUPABASE_URL`
- Secret key(`sb_secret_` で始まる) → `SUPABASE_SECRET_KEY`

## セットアップ 2. ローカルでの動作確認

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env.example をコピーして .env を作り、値を入れる(.envは既にある場合は不要)
python scripts/test_dify.py        # Difyから回答が返るか
python scripts/test_supabase.py    # Supabaseに接続できるか
```

## セットアップ 3. Vercelへのデプロイ

1. GitHubにこのプロジェクトをアップロードします(次のステップ)。
2. [Vercel](https://vercel.com) で **Add New → Project** からそのリポジトリを選び、Importします。
3. **Environment Variables** に6つ登録します: `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` / `DIFY_API_KEY` / `SUPABASE_URL` / `SUPABASE_SECRET_KEY` / `CRON_SECRET`
   - `CRON_SECRET` は16文字以上のランダムな文字列にします(例: `openssl rand -hex 24`)。Vercelはこの値をCron実行時に自動で `Authorization: Bearer ...` として付けます。
4. **Deploy** を押します。完成したURL(例: `https://xxxx.vercel.app`)を控えます。
5. 環境変数を後から変えたときは、再デプロイが必要です。

## セットアップ 4. Cron Jobsの確認方法

- Vercelのプロジェクト → **Settings → Cron Jobs** に `/api/keepalive`(毎日 0:00 UTC)が表示されていれば登録済みです。
- 同じ画面の **Run** ボタンで今すぐ実行できます。
- **Logs** で `/api/keepalive` が `200` なら成功、`401` なら `CRON_SECRET` の設定ミスです。
- Hobbyプランは1日1回までのため、`vercel.json` は `0 0 * * *` にしています(時刻は実行時間帯内でずれることがあります)。

## セットアップ 5. LINE側の設定

[LINE Developers](https://developers.line.biz/) → 対象のMessaging APIチャネルで設定します。

1. **Messaging API設定 → Webhook URL** に `https://(あなたのVercelのURL)/callback` を入力し、**検証** で成功を確認します。
2. **Webhookの利用** をオンにします。
3. **Webhookの再送** は**オフ**にします(オンだと同じメッセージが二重処理されることがあります)。
4. **応答メッセージ**(LINE公式アカウントマネージャー側の自動応答)はオフにします。
5. チャネルシークレット(チャネル基本設定)と、チャネルアクセストークン(長期)を発行して環境変数に登録します。
