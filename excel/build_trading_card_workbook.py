# -*- coding: utf-8 -*-
"""トレカ事業 従業員管理表(Excel) 生成スクリプト.

日付ごとに「仕入れ店舗 / 仕入れ合計金額 / 支払方法 / 立替(○) / 交通費(移動区間・区間ごとの金額)」
を従業員2名分まとめて1シートで入力できる管理表を作成する。
共通経費(送料・その他経費)は別シートで管理し、集計シートで月次合計を算出する。
"""

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

FONT = "Meiryo"

# ---- 色・スタイル定義 -------------------------------------------------------
C_TITLE = "1F3864"        # 濃紺(タイトル)
C_HEADER = "2E5C8A"       # ヘッダー背景
C_HEADER2 = "4A7A3F"      # 共通経費ヘッダー背景
C_HEADER3 = "8A5A2E"      # 集計ヘッダー背景
C_INPUT = "FFF7DC"        # 入力セル(淡黄)
C_AUTO = "EDEDED"         # 自動計算セル(グレー)
C_SAMPLE = "E8F1FB"       # 記入例
C_BAND = "F7FAFD"         # 縞模様

THIN = Side(style="thin", color="B7C3CE")
MED = Side(style="medium", color="2E5C8A")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

FILL_INPUT = PatternFill("solid", fgColor=C_INPUT)
FILL_AUTO = PatternFill("solid", fgColor=C_AUTO)
FILL_SAMPLE = PatternFill("solid", fgColor=C_SAMPLE)

F_TITLE = Font(name=FONT, size=14, bold=True, color=C_TITLE)
F_NOTE = Font(name=FONT, size=9, color="555555")
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_BODY = Font(name=FONT, size=10)
F_INPUT = Font(name=FONT, size=10, color="0000FF")   # 手入力セルは青字
F_AUTO = Font(name=FONT, size=10, color="404040")    # 自動計算は黒/グレー
F_SAMPLE = Font(name=FONT, size=10, color="7F7F7F", italic=True)
F_TOTAL = Font(name=FONT, size=10, bold=True)

YEN = '#,##0;-#,##0;"-"'
DATE_FMT = "yyyy/mm/dd"

DATA_ROWS = 500           # 入力一覧の行数(行はいくらでも追加可)
FEE_ROWS = 200            # 共通経費の行数

EMP_A = "従業員A"
EMP_B = "従業員B"
PAY_METHODS = ["現金", "クレジットカード", "電子マネー", "QRコード決済", "銀行振込", "その他"]
FEE_KINDS = ["送料", "その他経費"]

wb = Workbook()

# ============================================================================
# 設定(マスタ)シート  ※先に作ってから他シートの入力規則で参照する
# ============================================================================
st = wb.active
st.title = "設定"
st["A1"] = "設定(マスタ)"
st["A1"].font = F_TITLE
st["A2"] = "従業員名・支払方法などの選択肢はここを書き換えると、各シートのプルダウンに反映されます。"
st["A2"].font = F_NOTE

st["B4"] = "従業員名"
st["D4"] = "支払方法"
st["F4"] = "経費区分"
st["H4"] = "立替"
for c in ("B4", "D4", "F4", "H4"):
    st[c].font = F_HEAD
    st[c].fill = PatternFill("solid", fgColor=C_HEADER)
    st[c].alignment = Alignment(horizontal="center", vertical="center")
    st[c].border = BORDER

for i, name in enumerate([EMP_A, EMP_B]):
    cell = st.cell(row=5 + i, column=2, value=name)
    cell.font = F_INPUT
    cell.fill = FILL_INPUT
    cell.border = BORDER
for i, name in enumerate(PAY_METHODS):
    cell = st.cell(row=5 + i, column=4, value=name)
    cell.font = F_INPUT
    cell.fill = FILL_INPUT
    cell.border = BORDER
for i, name in enumerate(FEE_KINDS):
    cell = st.cell(row=5 + i, column=6, value=name)
    cell.font = F_INPUT
    cell.fill = FILL_INPUT
    cell.border = BORDER
cell = st.cell(row=5, column=8, value="○")
cell.font = F_INPUT
cell.fill = FILL_INPUT
cell.border = BORDER
cell.alignment = Alignment(horizontal="center")

st["B8"] = "※従業員が3人以上になった場合は、B列に追記したうえで「集計」シートに行を追加してください。"
st["B8"].font = F_NOTE
for col, w in (("A", 3), ("B", 18), ("C", 3), ("D", 18), ("E", 3), ("F", 16), ("G", 3), ("H", 8)):
    st.column_dimensions[col].width = w

EMP_A_REF = "設定!$B$5"
EMP_B_REF = "設定!$B$6"

# ============================================================================
# 入力一覧シート(従業員2名を同一シートで一覧管理)
# ============================================================================
ws = wb.create_sheet("入力一覧")
HEAD_ROW = 5
FIRST = HEAD_ROW + 1
LAST = HEAD_ROW + DATA_ROWS

ws["A1"] = "トレカ事業　従業員 仕入れ・交通費 管理表"
ws["A1"].font = F_TITLE
ws["A2"] = (
    "【凡例】黄色セル＝手入力(青字) / グレーセル＝自動計算(触らないでください)"
)
ws["A2"].font = F_NOTE
ws["A3"] = (
    "【入力ルール】1行＝1件。同じ日に移動区間が複数ある場合は行を増やし、"
    "同じ日付・従業員を入力して「移動区間(出発/到着)」と「交通費」だけを記入してください"
    "(仕入れ金額はその日の1行目にのみ入力し、二重計上を防ぎます)。"
)
ws["A3"].font = F_NOTE
ws["A4"] = (
    "【立替】従業員が自腹で立て替えた行に「○」を入力してください。"
    "その行の仕入れ合計金額＋交通費が「集計」シートの立替精算額に加算されます。"
)
ws["A4"].font = F_NOTE

headers = [
    ("日付", 12),
    ("従業員", 12),
    ("仕入れ店舗", 22),
    ("仕入れ合計金額（円）", 18),
    ("支払方法", 16),
    ("立替\n(○)", 7),
    ("移動区間\n(出発)", 16),
    ("移動区間\n(到着)", 16),
    ("交通費（円）", 12),
    ("備考", 26),
    ("年月\n(自動)", 10),
]
for i, (title, width) in enumerate(headers, start=1):
    c = ws.cell(row=HEAD_ROW, column=i, value=title)
    c.font = F_HEAD
    c.fill = PatternFill("solid", fgColor=C_HEADER)
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)
    ws.column_dimensions[get_column_letter(i)].width = width
ws.row_dimensions[HEAD_ROW].height = 34

ws["D5"].comment = Comment(
    "その日・その店舗の仕入れ合計金額を税込で入力します。\n"
    "同じ日に複数の移動区間を追記する行では、空欄のままにしてください。", "管理表")
ws["K5"].comment = Comment(
    "A列の日付から自動で「yyyy/mm」を作成し、集計シートの月次集計に使用します。\n"
    "行を挿入した場合は、この列の数式を下の行からコピーしてください。", "管理表")

# --- 記入例(3行) ------------------------------------------------------------
samples = [
    ("2026/08/01", EMP_A, "カードショップ〇〇 秋葉原店", 45000, "現金", "○", "自宅", "秋葉原", 480, "記入例：削除してご利用ください"),
    ("2026/08/01", EMP_A, "", None, "", "○", "秋葉原", "中野", 200, "記入例：同じ日の2区間目は行を増やして入力"),
    ("2026/08/02", EMP_B, "リサイクルショップ△△ 大宮店", 128000, "クレジットカード", "", "自宅", "大宮", 640, "記入例：会社カード払いのため立替なし"),
]
for r, row in enumerate(samples, start=FIRST):
    for c, val in enumerate(row, start=1):
        cell = ws.cell(row=r, column=c, value=val)
        cell.font = F_SAMPLE
        cell.fill = FILL_SAMPLE
        cell.border = BORDER
    ws.cell(row=r, column=1).number_format = DATE_FMT
    ws.cell(row=r, column=4).number_format = YEN
    ws.cell(row=r, column=9).number_format = YEN
    ws.cell(row=r, column=6).alignment = Alignment(horizontal="center")

# 記入例の日付を日付型に(文字列で入れると集計できないため)
from datetime import date
for r, d in zip(range(FIRST, FIRST + 3), [date(2026, 8, 1), date(2026, 8, 1), date(2026, 8, 2)]):
    ws.cell(row=r, column=1, value=d).number_format = DATE_FMT
    ws.cell(row=r, column=1).font = F_SAMPLE
    ws.cell(row=r, column=1).fill = FILL_SAMPLE
    ws.cell(row=r, column=1).border = BORDER

# --- 入力行 ------------------------------------------------------------------
for r in range(FIRST, LAST + 1):
    is_sample = r < FIRST + len(samples)
    for c in range(1, 11):
        cell = ws.cell(row=r, column=c)
        cell.border = BORDER
        if not is_sample:
            cell.font = F_INPUT
            cell.fill = FILL_INPUT
        if c == 1:
            cell.number_format = DATE_FMT
        elif c in (4, 9):
            cell.number_format = YEN
        elif c == 6:
            cell.alignment = Alignment(horizontal="center")
    k = ws.cell(row=r, column=11, value=f'=IF($A{r}="","",TEXT($A{r},"yyyy/mm"))')
    k.font = F_AUTO
    k.fill = FILL_AUTO
    k.border = BORDER
    k.alignment = Alignment(horizontal="center")

# --- 合計行(表の最上部にサマリを置き、常に見えるようにする) -------------------
ws["C4"] = ""
tot_row = HEAD_ROW - 1  # 使わない(合計は集計シートに集約)

# --- 入力規則(プルダウン) ----------------------------------------------------
dv_emp = DataValidation(type="list", formula1="=設定!$B$5:$B$6", allow_blank=True,
                        showDropDown=False, promptTitle="従業員",
                        prompt="プルダウンから従業員を選択してください。")
dv_pay = DataValidation(type="list", formula1="=設定!$D$5:$D$10", allow_blank=True,
                        showDropDown=False, promptTitle="支払方法",
                        prompt="現金/クレジットカード等を選択してください。")
dv_adv = DataValidation(type="list", formula1='"○"', allow_blank=True,
                        showDropDown=False, promptTitle="立替",
                        prompt="従業員が立て替えた場合のみ ○ を入力してください。")
for dv in (dv_emp, dv_pay, dv_adv):
    ws.add_data_validation(dv)
dv_emp.add(f"B{FIRST}:B{LAST}")
dv_pay.add(f"E{FIRST}:E{LAST}")
dv_adv.add(f"F{FIRST}:F{LAST}")

ws.freeze_panes = f"A{FIRST}"
ws.auto_filter.ref = f"A{HEAD_ROW}:K{LAST}"
ws.sheet_view.showGridLines = False

# ============================================================================
# 共通経費シート(送料・その他経費)
# ============================================================================
fs = wb.create_sheet("共通経費")
F_HEAD_ROW = 5
F_FIRST = F_HEAD_ROW + 1
F_LAST = F_HEAD_ROW + FEE_ROWS

fs["A1"] = "共通経費（送料・その他経費）"
fs["A1"].font = F_TITLE
fs["A2"] = "【凡例】黄色セル＝手入力(青字) / グレーセル＝自動計算"
fs["A2"].font = F_NOTE
fs["A3"] = "従業員個人に紐づかない共通の経費を入力します。区分は「送料」「その他経費」から選択してください。"
fs["A3"].font = F_NOTE
fs["A4"] = "その他経費は「内容」に必ず用途(例：スリーブ購入、駐車場代)を記入してください。"
fs["A4"].font = F_NOTE

fee_headers = [("日付", 12), ("区分", 14), ("内容", 40), ("金額（円）", 14), ("備考", 24), ("年月\n(自動)", 10)]
for i, (title, width) in enumerate(fee_headers, start=1):
    c = fs.cell(row=F_HEAD_ROW, column=i, value=title)
    c.font = F_HEAD
    c.fill = PatternFill("solid", fgColor=C_HEADER2)
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)
    fs.column_dimensions[get_column_letter(i)].width = width
fs.row_dimensions[F_HEAD_ROW].height = 34

fee_samples = [
    (date(2026, 8, 3), "送料", "メルカリ発送（ゆうパケットプラス）×5件", 2600, "記入例：削除してご利用ください"),
    (date(2026, 8, 5), "その他経費", "スリーブ・ローダー購入", 3480, "記入例"),
]
for r, row in enumerate(fee_samples, start=F_FIRST):
    for c, val in enumerate(row, start=1):
        cell = fs.cell(row=r, column=c, value=val)
        cell.font = F_SAMPLE
        cell.fill = FILL_SAMPLE
        cell.border = BORDER
    fs.cell(row=r, column=1).number_format = DATE_FMT
    fs.cell(row=r, column=4).number_format = YEN

for r in range(F_FIRST, F_LAST + 1):
    is_sample = r < F_FIRST + len(fee_samples)
    for c in range(1, 6):
        cell = fs.cell(row=r, column=c)
        cell.border = BORDER
        if not is_sample:
            cell.font = F_INPUT
            cell.fill = FILL_INPUT
        if c == 1:
            cell.number_format = DATE_FMT
        elif c == 4:
            cell.number_format = YEN
    k = fs.cell(row=r, column=6, value=f'=IF($A{r}="","",TEXT($A{r},"yyyy/mm"))')
    k.font = F_AUTO
    k.fill = FILL_AUTO
    k.border = BORDER
    k.alignment = Alignment(horizontal="center")

dv_kind = DataValidation(type="list", formula1="=設定!$F$5:$F$6", allow_blank=True,
                         showDropDown=False, promptTitle="区分",
                         prompt="送料／その他経費 を選択してください。")
fs.add_data_validation(dv_kind)
dv_kind.add(f"B{F_FIRST}:B{F_LAST}")

fs.freeze_panes = f"A{F_FIRST}"
fs.auto_filter.ref = f"A{F_HEAD_ROW}:F{F_LAST}"
fs.sheet_view.showGridLines = False

# ============================================================================
# 集計シート(月次)
# ============================================================================
sm = wb.create_sheet("集計")
sm["A1"] = "月次集計"
sm["A1"].font = F_TITLE
sm["A2"] = "下の「対象年月」を書き換えると、全ての金額が自動で切り替わります（例：2026/08）。"
sm["A2"].font = F_NOTE

sm["A4"] = "対象年月"
sm["A4"].font = F_TOTAL
sm["B4"] = "2026/08"
sm["B4"].font = F_INPUT
sm["B4"].fill = FILL_INPUT
sm["B4"].border = BORDER
sm["B4"].alignment = Alignment(horizontal="center")
sm["B4"].comment = Comment(
    "yyyy/mm 形式の文字列で入力してください（例：2026/08）。\n"
    "入力一覧・共通経費シートのK列/F列「年月」と突き合わせて集計します。", "管理表")
sm["C4"] = "← yyyy/mm 形式で入力"
sm["C4"].font = F_NOTE

# --- 従業員別 ---------------------------------------------------------------
emp_head = ["従業員", "仕入れ合計金額", "交通費合計", "うち立替精算額", "本人負担合計"]
HR = 6
for i, t in enumerate(emp_head, start=1):
    c = sm.cell(row=HR, column=i, value=t)
    c.font = F_HEAD
    c.fill = PatternFill("solid", fgColor=C_HEADER3)
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)
sm.row_dimensions[HR].height = 30

IN = "入力一覧"
for i, ref in enumerate([EMP_A_REF, EMP_B_REF]):
    r = HR + 1 + i
    sm.cell(row=r, column=1, value=f"={ref}").font = F_AUTO
    sm.cell(row=r, column=2,
            value=f'=SUMIFS({IN}!$D${FIRST}:$D${LAST},{IN}!$K${FIRST}:$K${LAST},$B$4,'
                  f'{IN}!$B${FIRST}:$B${LAST},$A{r})')
    sm.cell(row=r, column=3,
            value=f'=SUMIFS({IN}!$I${FIRST}:$I${LAST},{IN}!$K${FIRST}:$K${LAST},$B$4,'
                  f'{IN}!$B${FIRST}:$B${LAST},$A{r})')
    sm.cell(row=r, column=4,
            value=f'=SUMIFS({IN}!$D${FIRST}:$D${LAST},{IN}!$K${FIRST}:$K${LAST},$B$4,'
                  f'{IN}!$B${FIRST}:$B${LAST},$A{r},{IN}!$F${FIRST}:$F${LAST},"○")'
                  f'+SUMIFS({IN}!$I${FIRST}:$I${LAST},{IN}!$K${FIRST}:$K${LAST},$B$4,'
                  f'{IN}!$B${FIRST}:$B${LAST},$A{r},{IN}!$F${FIRST}:$F${LAST},"○")')
    sm.cell(row=r, column=5, value=f"=$B{r}+$C{r}")
    for c in range(1, 6):
        cell = sm.cell(row=r, column=c)
        cell.border = BORDER
        if c >= 2:
            cell.font = F_AUTO
            cell.number_format = YEN
        cell.fill = FILL_AUTO

TR = HR + 3
sm.cell(row=TR, column=1, value="従業員 合計").font = F_TOTAL
for c in range(2, 6):
    col = get_column_letter(c)
    cell = sm.cell(row=TR, column=c, value=f"=SUM({col}{HR+1}:{col}{HR+2})")
    cell.font = F_TOTAL
    cell.number_format = YEN
for c in range(1, 6):
    cell = sm.cell(row=TR, column=c)
    cell.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)
    cell.fill = PatternFill("solid", fgColor="FDF0D5")

sm.cell(row=TR + 1, column=1,
        value="※「うち立替精算額」＝立替欄に○が付いた行の仕入れ合計金額＋交通費（従業員へ返金する金額）").font = F_NOTE
sm.cell(row=TR + 2, column=1,
        value="※「本人負担合計」＝仕入れ合計金額＋交通費（支払方法を問わない、その従業員が動かした金額）").font = F_NOTE

# --- 共通経費 ---------------------------------------------------------------
CR = TR + 4
sm.cell(row=CR, column=1, value="共通経費").font = F_HEAD
sm.cell(row=CR, column=2, value="金額").font = F_HEAD
for c in (1, 2):
    cell = sm.cell(row=CR, column=c)
    cell.fill = PatternFill("solid", fgColor=C_HEADER2)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)

FS = "共通経費"
common = [
    ("送料", f'=SUMIFS({FS}!$D${F_FIRST}:$D${F_LAST},{FS}!$F${F_FIRST}:$F${F_LAST},$B$4,'
             f'{FS}!$B${F_FIRST}:$B${F_LAST},"送料")'),
    ("その他経費", f'=SUMIFS({FS}!$D${F_FIRST}:$D${F_LAST},{FS}!$F${F_FIRST}:$F${F_LAST},$B$4,'
                   f'{FS}!$B${F_FIRST}:$B${F_LAST},"その他経費")'),
]
for i, (label, formula) in enumerate(common):
    r = CR + 1 + i
    sm.cell(row=r, column=1, value=label).font = F_BODY
    cell = sm.cell(row=r, column=2, value=formula)
    cell.font = F_AUTO
    cell.number_format = YEN
    for c in (1, 2):
        sm.cell(row=r, column=c).border = BORDER
        sm.cell(row=r, column=c).fill = FILL_AUTO

CT = CR + 3
sm.cell(row=CT, column=1, value="共通経費 合計").font = F_TOTAL
cell = sm.cell(row=CT, column=2, value=f"=SUM(B{CR+1}:B{CR+2})")
cell.font = F_TOTAL
cell.number_format = YEN
for c in (1, 2):
    sm.cell(row=CT, column=c).border = Border(left=THIN, right=THIN, top=MED, bottom=MED)
    sm.cell(row=CT, column=c).fill = PatternFill("solid", fgColor="E7F1E3")

# --- 総合計 -----------------------------------------------------------------
GR = CT + 2
sm.cell(row=GR, column=1, value="当月 総支出").font = Font(name=FONT, size=11, bold=True, color=C_TITLE)
cell = sm.cell(row=GR, column=2, value=f"=E{TR}+B{CT}")
cell.font = Font(name=FONT, size=11, bold=True, color=C_TITLE)
cell.number_format = YEN
for c in (1, 2):
    sm.cell(row=GR, column=c).border = Border(left=MED, right=MED, top=MED, bottom=MED)
    sm.cell(row=GR, column=c).fill = PatternFill("solid", fgColor="DCE6F1")
sm.cell(row=GR + 1, column=1, value="※ 従業員合計（仕入れ＋交通費）＋ 共通経費合計").font = F_NOTE

for col, w in (("A", 30), ("B", 18), ("C", 16), ("D", 18), ("E", 18)):
    sm.column_dimensions[col].width = w
sm.sheet_view.showGridLines = False

# ---- 既定フォントを全セルに適用（未設定セル対策）----------------------------
for sheet in wb.worksheets:
    for row in sheet.iter_rows():
        for cell in row:
            if cell.font is None or cell.font.name != FONT:
                f = cell.font
                cell.font = Font(name=FONT, size=f.size or 10, bold=f.bold, italic=f.italic,
                                 color=f.color)

wb.active = wb.sheetnames.index("入力一覧")
OUT = "/home/user/toto/excel/トレカ事業_従業員管理表.xlsx"
wb.save(OUT)
print("saved:", OUT)


def fix_fonts_in_styles(path=OUT, font=FONT):
    """recalc.py(LibreOffice)で再計算した後に実行する後処理.

    LibreOffice は日本語フォント Meiryo を持たない環境で styles.xml のフォント名を
    代替フォント(WenQuanYi Zen Hei 等)に書き換えてしまう。
    数式のキャッシュ値を壊さないよう、xl/styles.xml だけを直接置換して戻す。
    """
    import os
    import zipfile

    tmp = path + ".tmp"
    replaced = 0
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/styles.xml":
                text = data.decode("utf-8")
                for alt in ("WenQuanYi Zen Hei", "Liberation Sans", "DejaVu Sans"):
                    replaced += text.count(alt)
                    text = text.replace(alt, font)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, path)
    return replaced
