# ポケカ話題まとめ（pokeca-trends）

国内・海外の **X / Threads / Instagram / Reddit** からポケモンカード（ポケカ）の話題を毎日自動で集め、

1. **話題ごとにまとめて要約**（海外の話題も日本語で）
2. **コメント欄の反応を判定**（好意的 / 否定的 / 中立 の割合、代表的な意見、総合判定「好意的・否定的・賛否両論・中立」）
3. **トピックランキング**（いいね・コメント・拡散・投稿数・複数SNSでの広がりからスコア化。NEW / 急上昇 / 順位変動 / 連続日数つき）
4. **カードショップ買取表からの相場分析**（最高買取・中央値・前日/7日/30日比、急騰・急落ランキング、店舗間の価格差、相場指数、AIの相場コメント、話題と関連カードの紐づけ）

を行い、静的サイト（`docs/`）として出力します。GitHub Actions で毎日自動更新し、GitHub Pages でそのまま公開できます。

## まず試す（APIキー不要）

```bash
cd pokeca-trends
pip install -r requirements.txt
python main.py demo --offline     # 架空のサンプルデータでサイト一式を生成
open ../docs/index.html           # Windows は start ..\docs\index.html
```

`--offline` を外し `ANTHROPIC_API_KEY` を設定すると、デモデータでもClaudeによる要約・感情分析になります。

## 本番運用

```bash
cp .env.example .env    # 各APIキーを記入（使う媒体だけでOK。未設定の媒体は自動でスキップ）
python main.py run      # 収集 → 話題化・要約 → 反応分析 → ランキング → 相場分析 → サイト生成
```

個別実行: `cycle`（自動投稿込みの1サイクル） / `compose`（投稿文だけ生成） / `feedback`（反応の回収と学習だけ） / `collect`（`--only x reddit` で媒体限定） / `analyze` / `market` / `build`、日付指定は `--date 2026-11-14`。

### 毎日の自動実行（GitHub Actions）

`.github/workflows/pokeca-daily.yml` が毎日 22:17 JST に `python main.py run` を実行し、`docs/` と蓄積DB（`data/pokeca.db`）をコミットします。

1. リポジトリの Settings → Secrets and variables → Actions に `.env.example` と同じ名前でキーを登録
2. Settings → Pages で「Deploy from a branch」→ ブランチと `/docs` を選択
3. Actions タブから `pokeca-daily` を手動実行して動作確認

## 各SNSのデータ取得について（重要）

すべて**公式API**で取得します（スクレイピングは各SNSの規約違反になるため行いません）。

| 媒体 | 必要なもの | 取れるもの・制約 |
|---|---|---|
| Reddit | script アプリの Client ID/Secret | 投稿・スコア・コメント本文。無料枠あり（レート制限・商用利用は別途規約） |
| X | Developer Portal の Bearer Token | 投稿・いいね/RT/返信数・返信本文。**検索APIは有料プラン**。月間取得上限に注意（`config/settings.yaml` の件数で調整） |
| Threads | `threads_keyword_search` 権限のアクセストークン | 投稿・返信本文。他人の投稿のいいね数は取得不可 → 返信数で評価 |
| Instagram | ビジネス/クリエイターアカウント + Graph API | ハッシュタグ投稿のキャプション・いいね/コメント数。**他人の投稿のコメント本文は取得不可**、ハッシュタグは7日で30種まで |

サイトには投稿の抜粋（160字まで）と元投稿へのリンクのみを載せ、投稿者名は表示しません。

## 自動投稿（学習しながら1日3回投稿）

`python main.py cycle` が1サイクルです。GitHub Actions で **1日3回（7:41 / 12:13 / 19:47 JST）** 自動実行します。

```
収集 → 話題化・要約 → 自分の過去投稿の反応を回収 → 成績計算・学習 → バズ投稿の型を分析 → 投稿文を生成 → 審査 → 投稿 → サイト更新
```

| 仕組み | 内容 |
|---|---|
| バズ投稿の“型”の学習 | 反応の大きい投稿と小さい投稿を比べ、構成・冒頭の掴み・長さ・絵文字/タグの傾向を抽象化（文言はコピーしない） |
| 投稿の型（6種類） | 速報 / 問いかけ / 箇条書きまとめ / 相場数字 / 海外の反応 / コミュニティの声。**UCBバンディット**で成績の良い型を多く、未知の型もときどき試す |
| 反応のフィードバック | 投稿6時間後から いいね・返信・拡散・表示回数・返信の感情 を取得。表示1000回あたりの反応率を24時間時点にそろえ、同じ媒体内の順位(0〜1)を成績にする。**否定的な返信が多い投稿は減点**（炎上で伸びたものを成功と学ばない） |
| プレイブック | 成績上位/下位の投稿を Claude が比べ「続けること・避けること」をまとめ、次の投稿生成に渡す |
| 安全装置 | ①資料（サイトの要約・相場データ）にある事実だけで書く ②別の Claude が事実・規約を審査 ③機械チェック: 元投稿との連続一致18字以上や重なり率で盗用を排除、架空の体験談・断定的な相場予測・売買推奨・メンション・拡散要求を禁止、文字数（X は重み付き280） ④同じ話題は24時間空ける ⑤1日の投稿上限 |

### 有効にする手順

1. **まず下書きで確認**: `autopost.enabled: false`（既定）のまま数日動かし、サイトの「自動投稿」ページで生成された下書きを確認
2. X: Developer Portal でアプリ権限を **Read and write** にし、`X_API_KEY` `X_API_SECRET` `X_ACCESS_TOKEN` `X_ACCESS_SECRET` を登録。
   プロフィール設定で **「自動化されたアカウント」ラベル**を付ける（Xの自動化ルール）
3. Threads: `threads_content_publish` `threads_manage_insights` `threads_read_replies` 権限のトークンを `THREADS_ACCESS_TOKEN` に
4. `config/settings.yaml` の `autopost.enabled: true` にしてコミット

投稿数は `posts_per_cycle`（既定: 1サイクル各媒体1件）と `max_posts_per_day`（既定4）で調整します。
X の投稿APIはプランごとに月間の投稿数上限があるので、`3回/日 × 媒体数` が収まるか確認してください。

### 対象外にしているもの
- **Reddit**: bot による投稿を禁止しているサブレディットが多く、アカウント停止のリスクが高いため収集のみ
- **Instagram**: テキストだけの投稿ができない（画像が必須）ため収集のみ
- 他人の投稿への自動返信・自動メンション・自動いいね・自動フォロー（各SNSのスパム規約に触れやすいため実装しない）

## 買取表の設定

`config/shops.yaml` にショップを追加します（例はファイル内コメント参照）。

- `html_table`: Webページの表をCSSセレクタで読む
- `image`: 買取表の**画像をClaudeの画像認識で表に書き起こす**（X等で画像配布しているショップ向け）
- `csv`: CSVのURL/ファイル
- 手動: `data/buylists/<ショップ名>_<YYYY-MM-DD>.csv` を置くと自動取込（書式は `sample.csv.example`）

取得前に robots.txt を自動確認し、アクセス間隔を空けます。**各ショップの利用規約を必ず確認**し、許可されていない取得は行わないでください。
カード名の表記ゆれ（全角半角、【SAR】表記、型番の0埋めなど）は自動で正規化し、同じカードとしてまとめます。

## 設定（`config/settings.yaml`）

- 収集キーワード（国内/海外）、サブレディット、ハッシュタグ
- ランキングの重み（いいね・コメント・拡散・投稿数・複数SNSボーナス）
- Claude のモデルと思考の深さ（既定 `claude-opus-5-5`。コメント分析を安くしたい場合は `light_model` を変更）

## 構成

```
pokeca-trends/
  main.py                    CLI
  config/settings.yaml       全体設定 / shops.yaml 買取表の取得元
  pokeca/collectors/         x_twitter.py threads.py instagram.py reddit.py
  pokeca/analysis/           topics.py（話題化・要約） sentiment.py（反応判定） ranking.py offline.py（APIキー無し用）
  pokeca/market/             buylist.py（取得） normalize.py（名寄せ） analytics.py（相場分析）
  pokeca/autopost/           style.py（バズの型） composer.py（生成・審査） guard.py（盗用・禁止表現） bandit.py（型の選択）
                             publisher.py（X/Threads投稿・反応取得） feedback.py（成績・プレイブック） cycle.py
  pokeca/site/               builder.py + templates/（静的サイト生成）
  pokeca/demo.py             架空のデモデータ
docs/                        生成されたサイト（GitHub Pages 公開用）
```

Claude 連携のポイント: 出力はPydanticスキーマで固定した構造化出力、長い入力に備えてストリーミング受信、安全分類器による拒否時は server-side fallback で別モデルが自動で続行します。
