# エステサロン LINE × Dify 中継サーバー

LINEで届いた問い合わせをDifyのチャットボットに渡し、回答をLINEへ返す中継サーバーです(Python / FastAPI / Vercel)。

## 1. 全体の仕組み

```
LINEユーザー → LINE → [Vercel上の中継サーバー] → Dify(回答を作る)
                              │
                              └→ Supabase(会話IDを記録)
LINEユーザー ← LINE ← 中継サーバーが reply API で返信
```

- 署名(`x-line-signature`)を検証し、LINE以外からのアクセスは拒否します。
- 返信は reply API のみです(push API は使いません。無料プランの通数制限対策)。
- テキスト以外(スタンプ・画像)には「文字でご質問ください」と返します。
- Difyでエラーが出たら「ただいま混み合っています。少し時間をおいて送ってください」と返します。
- LINEのユーザーIDは SHA-256 でハッシュ化し、Supabaseの保存とDifyの `user` にはハッシュ値だけを使います。

### 会話の続き方

| ユーザーの操作 | 動き |
|---|---|
| 普通の質問(前回から24時間以内) | 前の会話の続きとして回答 |
| 普通の質問(24時間より後) | 新しい会話として回答 |
| 「前回の続き」と送る | 24時間を過ぎていても、`line_users` に保存された最後の会話IDで続ける。「前回のご相談の続きからお答えします。ご質問をどうぞ」と返信 |
| 「最初から」と送る | 24時間以内でも新しい会話にする。「新しいご相談として承ります。ご質問をどうぞ」と返信 |

保存された会話が無いときに「前回の続き」と送ると、新しい相談として案内します。

### ファイルの役割

| ファイル | 役割 |
|---|---|
| `app.py` | 本体。`/callback`(LINE受信)と `/api/keepalive`(Cron用) |
| `line_client.py` | 署名検証、ID のハッシュ化、reply API |
| `dify_client.py` | Difyへの質問 |
| `supabase_client.py` | `line_users` テーブルの読み書き |
| `config.py` | 環境変数の読み込みと固定メッセージ |
| `vercel.json` | Cron Jobsの設定(1日1回) |
| `scripts/test_dify.py` | Difyの動作確認 |
| `scripts/test_supabase.py` | Supabaseの接続確認 |

## 2. Supabaseのテーブル作成

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

## 3. ローカルでの動作確認

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env.example をコピーして .env を作り、値を入れる(.envは既にある場合は不要)
python scripts/test_dify.py        # Difyから回答が返るか
python scripts/test_supabase.py    # Supabaseに接続できるか
```

## 4. Vercelへのデプロイ

1. GitHubにこのプロジェクトをアップロードします(次のステップ)。
2. [Vercel](https://vercel.com) で **Add New → Project** からそのリポジトリを選び、Importします。
3. **Environment Variables** に6つ登録します: `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` / `DIFY_API_KEY` / `SUPABASE_URL` / `SUPABASE_SECRET_KEY` / `CRON_SECRET`
   - `CRON_SECRET` は16文字以上のランダムな文字列にします(例: `openssl rand -hex 24`)。Vercelはこの値をCron実行時に自動で `Authorization: Bearer ...` として付けます。
4. **Deploy** を押します。完成したURL(例: `https://xxxx.vercel.app`)を控えます。
5. 環境変数を後から変えたときは、再デプロイが必要です。

## 5. Cron Jobsの確認方法

- Vercelのプロジェクト → **Settings → Cron Jobs** に `/api/keepalive`(毎日 0:00 UTC)が表示されていれば登録済みです。
- 同じ画面の **Run** ボタンで今すぐ実行できます。
- **Logs** で `/api/keepalive` が `200` なら成功、`401` なら `CRON_SECRET` の設定ミスです。
- Hobbyプランは1日1回までのため、`vercel.json` は `0 0 * * *` にしています(時刻は実行時間帯内でずれることがあります)。

## 6. LINE側の設定

[LINE Developers](https://developers.line.biz/) → 対象のMessaging APIチャネルで設定します。

1. **Messaging API設定 → Webhook URL** に `https://(あなたのVercelのURL)/callback` を入力し、**検証** で成功を確認します。
2. **Webhookの利用** をオンにします。
3. **Webhookの再送** は**オフ**にします(オンだと同じメッセージが二重処理されることがあります)。
4. **応答メッセージ**(LINE公式アカウントマネージャー側の自動応答)はオフにします。
5. チャネルシークレット(チャネル基本設定)と、チャネルアクセストークン(長期)を発行して環境変数に登録します。
