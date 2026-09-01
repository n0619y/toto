# 小児先天性心疾患ガイドライン集 ＋ 全文検索アプリ

日本（JCS／日本小児循環器学会ほか）・米国（AHA／ACC／ASE／PACES ほか）・欧州（ESC／AEPC／EACTS／DGPK ほか）が公開している、
小児先天性心疾患の **解剖・病態・診断・内科的／外科的治療・カテーテル治療・合併症・術後管理・外来診療（移行期医療・学校/スポーツ・妊娠）** に関する
ガイドライン／学会ステートメントを1か所に集め、**一括ダウンロード** と **全文検索** ができるようにしたものです。

**収録数: 219 件**（日本 64 / 米国 70 / 欧州 85）— 台帳: [`catalog/guidelines.json`](catalog/guidelines.json) ／ 一覧ページ: [`index.html`](index.html) ／ CSV: [`catalog/guidelines.csv`](catalog/guidelines.csv)

| カテゴリ | 件数 |
|---|---|
| 不整脈 | 26 |
| 心不全 | 24 |
| 診断・画像 | 21 |
| 外科治療 | 20 |
| 総合/ACHD | 18 |
| 学校・スポーツ | 16 |
| カテーテル治療 | 14 |
| 肺高血圧 | 11 |
| 遺伝・発達 | 11 |
| 川崎病 | 10 |
| 感染性心内膜炎 | 10 |
| 術後管理・遠隔期 | 10 |
| その他 | 9 |
| 胎児 | 8 |
| 薬物療法 | 6 |
| 妊娠・出産 | 5 |

主な発行団体: 日本循環器学会(JCS)・日本小児循環器学会(JSPCCS)・日本胎児心臓病学会・JPIC・日本川崎病学会 ／ AHA・ACC・ASE・PACES/HRS・AAP・ISHLT・SCAI・SCMR ／ ESC・EACVI・EHRA・AEPC・EACTS・EPPVDN・ISUOG・DGPK(ドイツ, AWMF S2k 疾患別シリーズ)・NICE・HAS

---

## 📦 一括ダウンロード

### 方法A: GitHub Release から ZIP を落とす（いちばん簡単）

GitHub Actions がカタログ内の全PDFを自動取得し、Release `guidelines-latest` に添付します。

| 内容 | 固定URL |
|---|---|
| 全PDF ZIP | <https://github.com/n0619y/toto/releases/download/guidelines-latest/chd-guidelines-pdf.zip> |
| 全文検索DB（`guidelines.db`） | <https://github.com/n0619y/toto/releases/download/guidelines-latest/guidelines.db> |
| 取得できなかったPDF一覧 | <https://github.com/n0619y/toto/releases/download/guidelines-latest/download_report.md> |

Release ページ: <https://github.com/n0619y/toto/releases/tag/guidelines-latest>

- 初回は GitHub の **Actions → "Build CHD guideline bundle" → Run workflow** で生成されます（`catalog/guidelines.json` を更新して push しても自動実行）。
- 学術出版社サイトの一部（AHA Journals / JACC / Oxford Academic など）は自動取得を拒否することがあります。
  取得できなかったものは `download_report.md` に **ブラウザで開くURLと保存ファイル名** がまとまるので、手動で `guidelines/pdf/` に保存してください。

### 方法B: 自分のPCで取得する

```bash
python guidelines/download_guidelines.py            # 全件（標準ライブラリのみ・追加インストール不要）
python guidelines/download_guidelines.py --region JP  # 日本のみ
python guidelines/download_guidelines.py --retry-failed
```

`guidelines/pdf/` に `JP_2018_jcs2018-chd-dx-drug.pdf` のような名前で保存され、
`guidelines/pdf/_download_report.md` に成功／失敗の一覧が出ます。
wget 派の方は `wget -i guidelines/catalog/urls.txt -P guidelines/pdf` でも可です。

### リンク一覧ページ

`guidelines/index.html` をブラウザで開くと、全ガイドラインのリンク（PDF／紹介ページ／DOI）を地域・カテゴリ別に一覧できます。
Excel で見たい場合は `guidelines/catalog/guidelines.csv` を開いてください。

---

## 🔍 全文検索アプリ

PDF本文をページ単位で SQLite（FTS5）に取り込み、ブラウザから検索します。Flask などの追加サーバーは不要です。

```bash
pip install pymupdf                       # PDFテキスト抽出（初回のみ）
python guidelines/download_guidelines.py  # PDF取得（または Release の ZIP を guidelines/pdf/ に展開）
python guidelines/build_index.py          # 全文検索DB作成（差分更新。--rebuild で作り直し）
python guidelines/app.py --open           # http://127.0.0.1:8765 で起動
```

Release の `guidelines.db` をダウンロードして `guidelines/guidelines.db` に置けば、`build_index.py` を飛ばしてすぐ検索できます
（PDFの該当ページを開く機能を使うには ZIP のPDFも `guidelines/pdf/` に展開してください）。

### できること

- **全文検索**: 日本語・英語どちらも部分一致。複数語は AND、`"引用符"` で完全一致フレーズ
  （例: `ファロー四徴症 肺動脈弁置換`, `Fontan anticoagulation`, `"Class IIa" coarctation`）
- **絞り込み**: 地域（日/米/欧）・カテゴリ・発行団体・言語・発行年
- **ガイドライン別ヒット数** のチップでドキュメントを切り替え
- **該当ページをPDFで開く**（`#page=N` 付きリンク）／ページ全文をその場で表示
- **ガイドライン一覧**: 収録・未取得の状況、配布元・DOIリンク
- **Claude Q&A（任意）**: 質問文から関連ページを検索し、出典番号・ページ付きで回答
  （リポジトリ直下の `.env` に `ANTHROPIC_API_KEY` が必要。モデルは `config/settings.yaml` の `claude.model`、または環境変数 `GUIDELINE_QA_MODEL` で指定）

### 仕組み

```
guidelines/
├── catalog/guidelines.json   … ガイドライン台帳（ここに追加すると全部に反映）
├── catalog/urls.txt / .csv   … make_catalog.py が生成
├── index.html                … リンク一覧ページ（make_catalog.py が生成）
├── download_guidelines.py    … 一括ダウンローダ
├── build_index.py            … PDF → guidelines.db（FTS5, trigram）
├── app.py                    … 検索サーバー（標準ライブラリのみ）
├── static/index.html         … 検索UI
└── pdf/                      … PDF保存先（git管理外）
```

台帳に1件追加するには `catalog/guidelines.json` に次の形式で追記し、`python guidelines/make_catalog.py` を実行します。

```json
{
  "id": "esc2020-achd",
  "title_ja": "2020 ESC 成人先天性心疾患管理ガイドライン",
  "title_en": "2020 ESC Guidelines for the management of adult congenital heart disease",
  "organization": "ESC", "year": 2020, "region": "EU", "category": "総合/ACHD", "language": "en",
  "url": "https://.../pdf", "landing_url": "https://...", "doi": "10.1093/eurheartj/ehaa554"
}
```

---

## ⚖️ 利用上の注意

- 各PDFの著作権は発行団体・出版社に帰属します。本フォルダは公開URLへの **リンク集＋個人利用のための取得・検索ツール** であり、PDF自体はリポジトリに含めていません。
- ガイドラインは改訂されます。台帳の `year` と配布元の最新版を必ず確認してください。
- Claude Q&A の回答は検索でヒットしたページのみを根拠にした要約です。診療判断の前に原文を確認してください。
