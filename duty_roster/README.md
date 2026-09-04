# duty_roster — グループ当番表 (月間スケジュール) 自動作成ツール

循環器グループの「予定一覧 (1 枚目)」から「当番カレンダー (2 枚目)」を作るためのツール。
まず **元ファイルの解析と、同じカレンダーの再現** を実装した段階です (当番の自動割り当ては次段階)。

```
duty_roster/
├── duty_roster/            パッケージ本体
│   ├── model.py            データモデル (コマ / 当番表 / セル結合ルール)
│   ├── parse_plan.py       1 枚目 (予定一覧 PDF / xlsx) → plan.yaml
│   ├── plan_template.py    1 枚目形式の Excel 入力テンプレート生成 (月ごとにシート, 祝日表つき)
│   ├── recurring.py        各月共通の定例予定 (第 N 曜日 / 毎週 / 奇数月・偶数月) の展開
│   ├── skeleton.py         plan → 予定だけ埋めた roster 雛形 (予定文字列 → コマ変換ルール)
│   ├── extract_calendar.py 2 枚目 (カレンダー PDF) → コマ単位の色・文字 (検証・roster 起こし用)
│   ├── render_pdf.py       roster → PDF (PyMuPDF 直接描画, 元 PDF と同じ寸法)
│   ├── render_xlsx.py      roster → Excel (.xlsx) (LibreOffice があれば PDF 化も)
│   ├── compare.py          生成物と元 PDF のコマ単位比較
│   ├── check.py            集計・整合性チェック
│   └── cli.py              コマンドライン
├── data/recurring.yaml     各月共通の定例予定 (テンプレートに自動入力される)
├── data/2026-09/
│   ├── plan.yaml           1 枚目を読んだ結果
│   ├── roster_skeleton.yaml plan から自動生成した雛形 (予定のみ)
│   └── roster.yaml         2 枚目と同じ内容 (当番・追加予定を含む「正解」)
├── samples/                元の 2 つの PDF
├── output/2026-09/         生成した PDF / xlsx
├── docs/analysis.md        解析メモ (レイアウト, 色の意味, 予定→カレンダー対応, 当番の分布)
└── tests/                  往復テスト
```

## セットアップ

```bash
cd duty_roster
pip install -r requirements.txt
```

PDF 出力には日本語フォントが必要です。IPA ゴシック / Noto Sans CJK / MS ゴシックを自動で探し、
無ければ MuPDF 内蔵の CJK フォントを使います。`--font path/to/font.ttf` または環境変数 `DUTY_ROSTER_FONT` で指定もできます。

## 使い方

```bash
# 1. 予定一覧 (1 枚目) を読む → plan.yaml
python -m duty_roster parse-plan samples/Schedule_202609_plan.pdf --month 2026-09 -o data/2026-09/plan.yaml

# 2. 予定だけ埋めた雛形を作る (1st / 2nd は人が (将来は自動で) 埋める)
python -m duty_roster skeleton data/2026-09/plan.yaml -o data/2026-09/roster_skeleton.yaml

# 3. roster.yaml からカレンダーを出力 (PDF と xlsx)
python -m duty_roster render data/2026-09/roster.yaml -o output/2026-09/Schedule_2026-09

# 4. 元カレンダー PDF と突き合わせ (全コマの色と文字を比較)
python -m duty_roster verify output/2026-09/Schedule_2026-09.pdf samples/Sep_2026_1_calendar.pdf
python -m duty_roster verify data/2026-09/roster.yaml          samples/Sep_2026_1_calendar.pdf

# 5. 集計と整合性チェック (各コマに 1st が 1 人いるか等)
python -m duty_roster check data/2026-09/roster.yaml

# 予定一覧 (1 枚目) 形式の Excel 入力テンプレート (月ごとにシート, 土日祝は赤, 定例予定を自動入力, 2026-09 を記入例として同梱)
python -m duty_roster plan-template --start 2026-10 --end 2027-03 --recurring data/recurring.yaml --example data/2026-09/plan.yaml -o "output/予定一覧_2026-10_2027-03.xlsx"
#   記入後はそのまま読める:  python -m duty_roster parse-plan "output/予定一覧_2026-10_2027-03.xlsx" --month 2026-10 -o data/2026-10/plan.yaml

# (元カレンダー PDF から roster.yaml を起こす)
python -m duty_roster extract samples/Sep_2026_1_calendar.pdf --month 2026-09 -o data/2026-09/roster.yaml
```

テスト: `python -m pytest -q tests`

## roster.yaml の書き方

1 日 = 3 コマ (`8:30` = AM, `12:00` = PM, `17:00` = 夜) を `AM, PM, 夜` の順にカンマ区切りで書きます。

```yaml
month: 2026-09
members: [豊野, 仲本, 佐々木]
holidays: [21, 22, 23]        # 土日以外の休日
days:
  4:
    豊野: 休暇, 佐賀, 佐賀        # 予定 (紫). 同じ予定名が連続すると (日をまたいでも) 1 セルに結合
    仲本: 2nd, 由利, 2nd
    佐々木: 1st+一般外来当番, 1st+一般外来当番, 1st   # 当番ラベルの下に補足行
  7:
    豊野: 2nd, 外来/2nd, 小児科/1st   # 予定/当番 = 予定をしながら当番 (色は当番色, 文字は予定名)
  30:
    豊野: ×, ×, -                # × = バツ印, - = 空き (平日は白, 休日は水色)
```

| 書き方 | 意味 | 表示 |
|---|---|---|
| `1st` / `2nd` | 当番 | 黄 / 緑 |
| `外来` | 予定 | 紫, 文字は予定名 |
| `外来/2nd`, `NICU/1st` | 予定をしながら当番 | 当番色, 文字は予定名 |
| `1st+一般外来当番`, `1st+(19時～)` | 当番 + 補足行 | 当番色, 2 行 |
| `-` | 空き | 平日は白, 休日は水色 |
| `×` | バツ印付きの空き | 白 + × |

## 再現結果

* `render` で作った PDF は、元 PDF と **90 日分 × 3 名 × 3 コマ = 270 コマ すべてで色・文字が一致** します (`verify` で確認、テストにも含む)。
* xlsx は同じ結合・色・罫線で作成しています。LibreOffice で PDF 化した場合、9 日夜の補足 `(～19時)` が
  セル幅の都合で一部欠けて描画されることがあります (Excel で開く分には問題ありません)。

## 次段階 (未実装)

予定一覧 (plan.yaml) から 1st / 2nd を自動で割り当てる処理。`docs/analysis.md` の 2.5 節に、
実データから読み取れた制約 (各コマ 1st は 1 人、2nd は 0〜1 人、平日昼 1st は原則佐々木 など) をまとめています。
NICU / 小児科当直や学会出張など、予定一覧に無い「追加された内容」は別途入力が必要です。
