# くらしの計算機（広告で収益化する小さなツール集）

登録不要・ブラウザ内だけで動く計算ツール23個の静的サイトです。サーバー費用はほぼゼロで、
問い合わせ対応も発生しない構成にしています。

**トレカ・PSA鑑定**（5個）: PSA鑑定 損益シミュレーター（`psa-profit`）/ 仕入れ上限 逆算（`psa-max-buy`）/
鑑定料の円換算（`grading-fee`）/ トレカ売買の利益率計算（`card-roi`）/
フリマと買取の手取り比較（`furima-vs-kaitori`）

**くらし・仕事**（18個）: 和暦変換 / 年齢計算 / 入学・卒業年 / 日数計算 / 文字数カウント / 割り勘 / 消費税 /
割引・ポイント還元 / 単位変換 / 全角半角 / パスワード生成 / 割合計算（`percent`）/ 時間の足し算・引き算（`time-calc`）/
時給・月給・年収 換算（`hourly-wage`）/ 乱数・抽選（`random`）/ 2・8・10・16進 変換（`base-convert`）/
ひらがな⇔カタカナ（`kana`）/ アスペクト比（`aspect`）

PSA鑑定の費用の式は `pokeca/core.py`（`per_card_costs`・`recommend`）と同じです。画面の初期値（鑑定料・送料・関税など）は
一例で、料金が変わっても計算式は変わらないため、利用者が自分で数字を書き換える前提にしています。
「フリマと買取の手取り比較」の式と端数処理（1円未満切り捨て）は `products/kaitori-kit/tejori.py` の売り手の視点と同じです。
手数料率・送料・買取率の初期値は一例で、実在のサービス名・店名は出していません。

扱わないと決めているもの: 規格値の正しさを保証できないもの（スリーブのサイズ表など）、医療系（BMIなど）、
金融商品の計算（ローン返済など）。

## ページ構成

| パス | 内容 |
|---|---|
| `/` | ツール一覧。「トレカ・PSA鑑定」の下に、解説記事3本と商品紹介ページへのリンクがある |
| `/<slug>/` | 各ツール（23個）。トレカ向けの5ツールだけ、下部に関連する解説記事と商品紹介ページへのリンクが出る |
| `/guide/` | 解説記事の一覧 |
| `/guide/grading-cost/` | 解説: 鑑定に出すときの1枚あたり費用の数え方 |
| `/guide/break-even/` | 解説: 損益分岐の仕入れ値と、グレードが下振れしたときの損益の見方 |
| `/guide/records/` | 解説: 鑑定転売の記録の付け方 |
| `/sheet/` | 売り切りのデジタル商品「PSA鑑定 収支管理シート」（`products/psa-sheet/`）の紹介ページ |
| `/privacy/` | プライバシーポリシー・運営者情報 |
| `/404.html` | 存在しないURL用のページ（トップと全ツールへのリンクつき）。検索には載せない（noindex、sitemap にも入れない） |

トップと 404 以外の各ページには、上部にパンくず（トップ › 解説記事 › 記事名 など）が出ます。

### 検索・SNS 向けの情報（`build.py` の `page` が全ページに出す）

- `<head>`: `description`（ページごとに別の文。空や重複があるとビルドが止まる）、`canonical`、OGP（`og:title` / `og:description` / `og:type` / `og:url` / `og:site_name`）、
  `twitter:card`、`theme-color`（ライト/ダーク。色は `src/style.css` の `--bg` から取る）、favicon（`public/favicon.svg` をビルド時に生成）。
  `canonical` と `og:url` は `site.json` の `url` から作ります。
- `og:image` は、`site.json` に `og_image` を足したときだけ出ます。値は `https://` のURLか、`src/` に置いた画像のファイル名（ビルド時に `public/` へコピー）。
- 構造化データ（JSON-LD）: トップに `WebSite`、各ツールに `WebApplication`（無料であることだけ）、解説記事に `Article`、トップ以外に `BreadcrumbList`。
  評価（`aggregateRating`）・公開日・著者など、確かめられない値は入れていません。

無料のトレカ向けツール → 解説記事 → 商品紹介ページ → 外部の販売サイト、という流れです。このサイトでは販売・決済をせず、
購入者とのやりとりも発生しない前提です（紹介ページに「サポートなし」「返金は販売サイトの規定」と明記）。

解説記事は「計算の考え方」だけを書いています。料金・関税・税率の実際の額や制度は確認していないため書いていません。
記事内の計算例は `build.py` の `DEF`（ツールの初期値）と `EX`（仮の売値）から計算しているので、初期値を変えると記事の数字も変わります。
記事の本文は `build.py` の `GUIDES`、ツールごとに出す記事は `TOOL_GUIDES`、紹介ページの本文は `sheet_body` にあります。

### 商品紹介ページの設定（`site.json`）

| 項目 | 使い方 |
|---|---|
| `product_url` | 販売ページのURL（`https://...`）。**空のあいだは購入ボタンを出さず「販売準備中」と表示**する。販売を始めたら入れて `python build.py` |
| `product_price` | 価格の表示文字列（例: `"980円（税込）"`）。書いたとおりに表示する。空なら価格を表示しない |
| `product_verified` | 実機で動作確認した環境（例: `"Excel（バージョン）/ Googleスプレッドシート（確認日）"`）。空のあいだは「Excel と Googleスプレッドシートの実機では未確認」と表示する。**確認していない環境は書かない** |

商品画像は、ビルド時に `products/psa-sheet/dist/images/*.png` があれば、幅1200pxに縮小した WebP（品質90）にして `public/sheet/` に出力し、表示します（ファイル名順、1枚目が先頭）。
元の PNG は変更しません。縮小には Pillow を使い、Pillow が無い環境では警告を出して縮小せずに PNG のままコピーします。
無ければ画像なしのページになります。紹介ページの文章（同梱物・対応環境・注意書き・FAQ抜粋）は `products/psa-sheet/` の
`listing.md`・`README.md`・`FAQ.md`・`make_zip.py` に合わせて手で書いたもので、自動では同期しません。商品側を変えたら `sheet_body` と `SHEET_FAQ` も直してください。

## 公開の手順（本人のアカウントが必要な部分）

チェックリストです。`python build.py --check` が、`site.json` のうち公開前に直すべき項目を一覧にします
（警告を表示するだけで、エラーでは止まりません。`python build.py` の最後にも件数が出ます）。

- [ ] **ドメインを決める**（任意だが広告審査には独自ドメインが必要）。
- [ ] `site.json` の `url` を公開URL（`https://` から、末尾の `/` なし）に書き換える。初期値の `https://example.com` のままだと、
      canonical・og:url・sitemap.xml・robots.txt がすべて example.com を指します。
- [ ] `site.json` の `operator` を運営者名（ペンネーム可）に書き換える。
- [ ] `site.json` の `contact` に連絡先を入れる（プライバシーポリシーのページに表示されます）。
- [ ] （任意）SNS で共有されたときの画像を用意し、`site.json` に `og_image` を足す。
- [ ] `python build.py` を実行し、`python build.py --check` の［要対応］が 0 件になったことを確かめる。
- [ ] **Cloudflare Pages** などの静的ホスティングにこのリポジトリを接続し、
      公開ディレクトリを `products/tools-site/public` に設定する（ビルドコマンドは不要）。
      存在しないURLで `404.html` が返ることを確かめる（Cloudflare Pages はドメイン直下の `404.html` を自動で使います。ほかのホスティングでは設定が要ることがあります）。
- [ ] Google Search Console にサイトを登録し、`/sitemap.xml` を送信する。
- [ ] **Google アドセンス**に申請する。承認されたら `site.json` の `adsense_client` に
      `ca-pub-...` を入れて `python build.py` → 全ページに広告枠が入る。

`--check` の［任意］は、空のままでも公開できる項目です（広告ID、`og_image`、商品の販売URL・動作確認の環境）。

審査には数日〜数週間かかり、落ちることもあります。検索からの流入が増えるまで数か月は収益ゼロの想定です。

## 開発

```bash
node src/test.mjs     # 計算ロジックのテスト
python build.py       # public/ を再生成
python build.py --check   # 公開前に直すべき項目の一覧（生成はしない）
```

ツールを増やすときは `src/lib.js`（計算）・`src/test.mjs`（手計算した期待値のテスト）・`src/app.js`（画面）に足し、
`build.py` の `CARD_TOOLS`（トップの「トレカ・PSA鑑定」）か `LIFE_TOOLS`（「くらし・仕事」）に1件足します。
トレカ向けツールを足したときは、下部に出す解説記事を `TOOL_GUIDES` にも足します。
