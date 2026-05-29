# 小児科コンテンツ自動生成システム（監修者登録版）

小児科領域の保護者向けコンテンツ（**記事・YouTube本編・YouTube Shorts**）を、
テーマ選定 → リサーチ → 台本 → 最終成果物 → **監修チェックリスト** まで
ワンコマンドで自動生成するPythonシステムです。

最終監修は **toto先生（小児科医）** が行う前提で、すべての成果物に
「**監修: toto先生（小児科医）**」が自動で挿入され、監修作業用のExcelパッケージまで自動生成されます。

> 本システムは情報提供を目的としたドラフトを生成するものです。
> 公開前には必ず医師（監修者）の確認を行ってください。

---

## 📦 これは何をするの？（ざっくり）

`python main.py --theme "乳児の便秘"` と打つだけで、`output/` フォルダに次が出ます。

| 成果物 | 場所 |
|---|---|
| 📝 記事（Markdown + HTML） | `output/articles/` |
| 🎬 YouTube本編スライド（16:9 PPTX） | `output/slides/` |
| 📱 YouTube Shortsスライド（9:16 PPTX） | `output/slides/` |
| 📋 **監修チェックリスト（Excel）** | `output/review/<テーマ>_<日付>/` |
| 📄 監修サマリー（Markdown） | 同上 |
| 🌐 監修ビューア（HTML） | 同上 |

---

## 🛠 初期セットアップ手順（はじめての方向け・全部書いてあります）

### ステップ0: Python のインストール

Python **3.11以上** が必要です。

**Mac の場合**
1. ターミナル（`アプリケーション → ユーティリティ → ターミナル`）を開く
2. 次を打ってバージョンを確認: `python3 --version`
3. 表示されない／3.11未満なら [python.org](https://www.python.org/downloads/) からインストーラをダウンロードして実行

**Windows の場合**
1. [python.org](https://www.python.org/downloads/) からインストーラをダウンロード
2. インストール画面で **「Add Python to PATH」にチェック** を入れてから「Install Now」
3. `コマンドプロンプト`（スタートメニューで「cmd」と検索）を開き `python --version` で確認

> 以降、Macは `python3` / `pip3`、Windowsは `python` / `pip` と読み替えてください。

### ステップ1: このプロジェクトを入手して移動

```bash
git clone <このリポジトリのURL>
cd toto
```

### ステップ2: 必要なライブラリをインストール

```bash
pip install -r requirements.txt
```

> エラーが出る場合は `python -m pip install -r requirements.txt` を試してください。

### ステップ3: APIキーを設定（`.env` ファイル）

`.env.example` をコピーして `.env` を作り、キーを書き込みます。

```bash
# Mac/Linux
cp .env.example .env
# Windows
copy .env.example .env
```

`.env` をテキストエディタで開き、次を記入します。

#### 🔑 ANTHROPIC_API_KEY（必須）

文章生成に使うClaudeのキーです。

1. <https://console.anthropic.com/> にアクセスしてログイン（アカウントが無ければ作成）
2. 左メニューの **「API Keys」** → **「Create Key」**
3. 表示されたキー（`sk-ant-...`）をコピー
4. `.env` の `ANTHROPIC_API_KEY=` の右に貼り付け

#### 🔍 TAVILY_API_KEY（任意・推奨）

Web検索の品質を上げるキーです。**未設定でも動きます**（自動で簡易検索に切り替わります）が、
設定すると医学情報のリサーチ精度が上がります。

1. <https://app.tavily.com/> にアクセスして無料登録
2. ダッシュボードの **「API Keys」** からキー（`tvly-...`）をコピー
3. `.env` の `TAVILY_API_KEY=` の右に貼り付け

> `.env` は `.gitignore` で除外されており、GitHubには公開されません。安心して記入してください。

### ステップ4: 最初の実行

```bash
python main.py --theme "乳児の便秘"
```

完了すると、画面の最後に次のように表示されます。

```
========================================
✅ 全工程完了
記事:        output/articles/乳児の便秘_20260529.md
本編スライド: output/slides/乳児の便秘_20260529_main.pptx
Shorts:      output/slides/乳児の便秘_20260529_shorts.pptx
📋 監修パッケージ: output/review/乳児の便秘_20260529/review_checklist.xlsx
   → toto先生（小児科医）、このファイルを開いて監修をお願いします
========================================
```

---

## ▶️ いろいろな使い方

```bash
python main.py                          # フル自動（テーマも自動で選ぶ）
python main.py --interactive            # 各ステップで確認しながら進める
python main.py --theme "子供の発熱対応"   # テーマを指定して実行
python main.py --step 2 --theme "乳児の便秘"          # リサーチだけ実行
python main.py --step 3 --theme "乳児の便秘" --input output/research/乳児の便秘_20260529.md
python main.py --review-only "乳児の便秘"  # 監修パッケージだけ作り直す
```

---

## 🩺 監修ワークフロー（toto先生向け）

1. 上記コマンドでコンテンツを生成する
2. `output/review/<テーマ>_<日付>/review_checklist.xlsx` を **Excel（またはGoogleスプレッドシート）で開く**
3. シートを順にチェック:
   - **サマリー**: 全体像・出典の内訳・リスク判定をひと目で確認
   - **主張×出典**: 各主張に「OK / 要修正 / 削除」を記入（要修正は黄、削除は赤に自動着色）
   - **必須チェック項目**: 安全性・正確性の項目に ✓ を入れる
   - **成果物別レビュー**: 記事・本編・Shortsを見出し／スライド単位でチェック
   - **修正指示記入欄**: 直してほしい点を自由に記入
4. `review_summary.md` で自動チェック結果（商品名・緊急ワード・免責文・監修者表記の有無）を確認
5. `review_package.html` をブラウザで開くと、左にチェック項目・右に記事本文を並べて確認できます

> 修正指示を書いたExcelは、将来 `python main.py --revise <ファイル>` で反映する土台として保存されます。

---

## 📂 出力ファイル一覧

```
output/
├── themes/     YYYYMMDD.json           … テーマ候補と採点
├── research/   <テーマ>_<日付>.md       … リサーチ本文
│               <テーマ>_<日付>_citations.json … 出典データ
├── scripts/    <テーマ>_<日付>_article.md … 記事台本
│               <テーマ>_<日付>_youtube.md … 本編台本
│               <テーマ>_<日付>_shorts.md  … Shorts台本
├── articles/   <テーマ>_<日付>.md / .html … 完成記事
│               <テーマ>_<日付>_eyecatch_prompt.txt … アイキャッチ用プロンプト
├── slides/     <テーマ>_<日付>_main.pptx  … 本編16:9スライド
│               <テーマ>_<日付>_shorts.pptx … Shorts9:16スライド
└── review/<テーマ>_<日付>/
              review_checklist.xlsx       … 監修メインファイル
              review_summary.md            … 要約版
              review_package.html          … ブラウザ用ビューア
```

ログは `logs/YYYYMMDD.log` に保存されます。

---

## 🔧 監修者情報の変更方法

`config/settings.yaml` の `reviewer` セクションを書き換えるだけです。
全成果物（記事・スライド・Excel・HTML）に自動で反映されます。

```yaml
reviewer:
  name: "toto先生"
  title: "小児科医"
  display: "監修: toto先生（小児科医）"
```

チェック項目を増やしたいときは `config/review_checklist.yaml` を編集してください。
（Excelの「必須チェック項目」シートに自動反映されます）

---

## ❓ トラブルシューティング

**1. `ANTHROPIC_API_KEY が設定されていません` と出る**
→ `.env` ファイルが作成され、`ANTHROPIC_API_KEY=sk-ant-...` に**実際のキー**が入っているか確認してください。
　`.env.example` のままのサンプル値（`sk-ant-xxxx...`）だと無効です。

**2. `ModuleNotFoundError`（◯◯が見つからない）と出る**
→ ライブラリのインストールが未完了です。`pip install -r requirements.txt` を再実行してください。
　複数のPythonが入っている場合は `python -m pip install -r requirements.txt` を試してください。

**3. 検索やトレンド取得で警告が出る／結果が少ない**
→ Tavilyキーが未設定だと簡易検索になります。`.env` に `TAVILY_API_KEY` を設定すると改善します。
　また `pytrends` はGoogle側のレート制限で一時的に失敗することがありますが、システムは自動で
　フォールバックして処理を続けるので問題ありません。詳しくは `logs/` のログを確認してください。

---

## ⚖️ 安全・倫理について（システムに組み込み済み）

- 全医学情報に出典URLを付与し、`citation_tracker` で構造化保持
- 「診断・処方はしない」「受診を促す文言を必ず入れる」をシステムプロンプトで強制
- 緊急症状は冒頭に救急受診の警告
- 商品名・薬剤商品名は使わず一般名のみ（Excelで自動検出）
- 個人情報・症例画像は扱わない
- 全成果物に「監修: toto先生（小児科医）」を自動挿入
- 文末に免責文「本コンテンツは一般的情報提供です。診断・治療は必ず医療機関にご相談ください」
