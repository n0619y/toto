# -*- coding: utf-8 -*-
"""トレカ事業 従業員管理表(Excel) 生成スクリプト.

レイアウト:
  月ごとに1シート(例「2026年08月」)を作成し、12か月分のシートを並べる。
  1枚のシートの中では、従業員ごとに独立した表を左右に並列配置する。
    ・左(A〜H列)  = 従業員A の表
    ・右(J〜Q列)  = 従業員B の表
  各表の項目: 日付 / 仕入れ店舗 / 仕入れ合計金額 / 支払方法 / 立替(○) /
              移動区間(出発) / 移動区間(到着) / 交通費
  移動区間が複数ある日は、表の途中に行を挿入して増やせる(小計は自動拡張)。
  シート下部に共通欄(送料・その他経費 内容/金額)と当月サマリーを置く。
  「年間集計」シートが12枚の月シートを横断集計する。
"""

from datetime import date

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

FONT = "Meiryo"

# ---- 配色 -------------------------------------------------------------------
C_TITLE = "1F3864"     # 濃紺
C_EMP_A = "2E5C8A"     # 従業員A 見出し(青)
C_EMP_B = "4A7A3F"     # 従業員B 見出し(緑)
C_FEE = "8A5A2E"       # 共通経費 見出し(茶)
C_SUM = "5B3A7A"       # サマリー 見出し(紫)
C_INPUT = "FFF7DC"     # 入力セル(淡黄)
C_AUTO = "EDEDED"      # 自動計算セル(グレー)
C_SAMPLE = "E8F1FB"    # 記入例
C_SUBA = "DCE6F1"      # 小計行(A)
C_SUBB = "E2EFDA"      # 小計行(B)
C_SUBF = "FDF0D5"      # 小計行(共通経費)
C_TOTAL = "FFF2CC"     # 当月総支出

THIN = Side(style="thin", color="B7C3CE")
MED = Side(style="medium", color="2E5C8A")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BORDER_HEAD = Border(left=THIN, right=THIN, top=MED, bottom=MED)
BORDER_BOLD = Border(left=MED, right=MED, top=MED, bottom=MED)

FILL_INPUT = PatternFill("solid", fgColor=C_INPUT)
FILL_AUTO = PatternFill("solid", fgColor=C_AUTO)
FILL_SAMPLE = PatternFill("solid", fgColor=C_SAMPLE)

F_TITLE = Font(name=FONT, size=14, bold=True, color=C_TITLE)
F_NOTE = Font(name=FONT, size=9, color="555555")
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_INPUT = Font(name=FONT, size=10, color="0000FF")     # 手入力は青字
F_AUTO = Font(name=FONT, size=10, color="404040")      # 自動計算
F_SAMPLE = Font(name=FONT, size=10, color="7F7F7F", italic=True)
F_SUB = Font(name=FONT, size=10, bold=True)
F_GRAND = Font(name=FONT, size=11, bold=True, color=C_TITLE)

YEN = '#,##0;-#,##0;"-"'
DATE_FMT = "yyyy/mm/dd"

# ---- 生成する期間 ------------------------------------------------------------
START_YEAR, START_MONTH_NO = 2026, 8
MONTHS = 12          # 何か月分のシートを作るか
N_ROWS = 40          # 従業員1人あたり1か月の入力行数
M_ROWS = 8           # 共通経費の入力行数

# ---- シート内の行位置 --------------------------------------------------------
R_TITLE = 1
R_NOTE1 = 2                          # 2〜5行目が凡例
R_EMP = 7                            # 従業員名見出し
R_HEAD = 8                           # 列ヘッダー
R_FIRST = 9                          # 入力開始
R_LAST = R_FIRST + N_ROWS - 1        # 入力終了 (=48)
R_SUB = R_LAST + 1                   # 小計 (=49)
R_SEC = R_SUB + 2                    # 「共通経費」「当月サマリー」見出し (=51)
R_SECHEAD = R_SEC + 1                # その列ヘッダー (=52)
R_FEE_FIRST = R_SECHEAD + 1          # 共通経費／サマリー 開始 (=53)
R_FEE_LAST = R_FEE_FIRST + M_ROWS - 1  # (=60)
R_FEE_SUB = R_FEE_LAST + 1           # 共通経費小計／当月総支出 (=61)

# 従業員A: A〜H列 / 区切り: I列 / 従業員B: J〜Q列
A_COL0 = 1
B_COL0 = 10
COLS = [
    ("日付", 11),
    ("仕入れ店舗", 20),
    ("仕入れ合計金額（円）", 16),
    ("支払方法", 14),
    ("立替\n(○)", 6),
    ("移動区間\n(出発)", 14),
    ("移動区間\n(到着)", 14),
    ("交通費（円）", 12),
]
C_DATE, C_SHOP, C_AMT, C_PAY, C_ADV, C_FROM, C_TO, C_FARE = range(8)
LAST_COL = B_COL0 + len(COLS) - 1    # Q列

PAY_METHODS = ["現金", "クレジットカード", "電子マネー", "QRコード決済", "銀行振込", "その他"]
FEE_KINDS = ["送料", "その他経費"]

EMP_REF = ["設定!$B$5", "設定!$B$6"]


def month_list(year, month, count):
    out = []
    for _ in range(count):
        out.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def box(ws, r1, c1, r2, c2, border=BORDER, fill=None, font=None, align=None):
    """矩形範囲に罫線・塗り・フォントをまとめて適用する(結合セル対応)。"""
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = border
            if fill is not None:
                cell.fill = fill
            if font is not None:
                cell.font = font
            if align is not None:
                cell.alignment = align


CENTER = Alignment(horizontal="center", vertical="center")
CENTER_WRAP = Alignment(horizontal="center", vertical="center", wrap_text=True)

wb = Workbook()
wb.remove(wb.active)

MONTH_SHEETS = []

# ============================================================================
# 月シート(1か月＝1シート)
# ============================================================================
for year, month in month_list(START_YEAR, START_MONTH_NO, MONTHS):
    name = f"{year}年{month:02d}月"
    ws = wb.create_sheet(name)
    MONTH_SHEETS.append(name)
    ws.sheet_view.showGridLines = False

    ws.cell(row=R_TITLE, column=1,
            value=f"{year}年{month}月　トレカ事業　従業員 仕入れ・交通費 管理表").font = F_TITLE
    notes = [
        "【凡例】黄色セル＝手入力（青字） ／ グレー・色付きセル＝自動計算（編集しないでください）",
        "【構成】左（A〜H列）が従業員A、右（J〜Q列）が従業員Bの独立した表です。月ごとにシートが分かれています。",
        ("【交通費】1行に1区間を入力します。同じ日に移動区間が複数ある場合は行を増やし、日付を再入力して"
         "区間と交通費だけを記入してください（仕入れ金額はその日の1行目のみ）。行が足りないときは表の途中"
         "（最終行の1つ上まで）で行を挿入すると、小計の範囲も自動で広がります。"),
        ("【立替】従業員が自分で支払った行に「○」を入力してください。その行の仕入れ合計金額＋交通費が"
         "「立替精算額（返金額）」に集計されます。"),
    ]
    for i, text in enumerate(notes):
        ws.cell(row=R_NOTE1 + i, column=1, value=text).font = F_NOTE

    for i, (_, width) in enumerate(COLS):
        ws.column_dimensions[get_column_letter(A_COL0 + i)].width = width
        ws.column_dimensions[get_column_letter(B_COL0 + i)].width = width
    ws.column_dimensions[get_column_letter(B_COL0 - 1)].width = 2   # I列(区切り)

    dv_pay = DataValidation(type="list", formula1="=設定!$D$5:$D$10", allow_blank=True,
                            showDropDown=False, promptTitle="支払方法",
                            prompt="現金／クレジットカード等を選択してください。")
    dv_adv = DataValidation(type="list", formula1='"○"', allow_blank=True,
                            showDropDown=False, promptTitle="立替",
                            prompt="従業員が立て替えた行のみ ○ を入力してください。")
    dv_kind = DataValidation(type="list", formula1="=設定!$F$5:$F$6", allow_blank=True,
                             showDropDown=False, promptTitle="経費区分",
                             prompt="送料／その他経費 を選択してください。")
    for dv in (dv_pay, dv_adv, dv_kind):
        ws.add_data_validation(dv)

    # --- 従業員ごとの独立した表(左右に並列) ---------------------------------
    for e, (col0, color, sub_fill) in enumerate(
            ((A_COL0, C_EMP_A, C_SUBA), (B_COL0, C_EMP_B, C_SUBB))):
        c_end = col0 + len(COLS) - 1

        ws.merge_cells(start_row=R_EMP, start_column=col0, end_row=R_EMP, end_column=c_end)
        box(ws, R_EMP, col0, R_EMP, c_end, border=BORDER_HEAD,
            fill=PatternFill("solid", fgColor=color), font=F_HEAD, align=CENTER)
        ws.cell(row=R_EMP, column=col0, value=f"={EMP_REF[e]}")

        for i, (title, _) in enumerate(COLS):
            c = ws.cell(row=R_HEAD, column=col0 + i, value=title)
            c.font = F_HEAD
            c.fill = PatternFill("solid", fgColor=color)
            c.alignment = CENTER_WRAP
            c.border = BORDER_HEAD
        ws.row_dimensions[R_HEAD].height = 32

        box(ws, R_FIRST, col0, R_LAST, c_end, fill=FILL_INPUT, font=F_INPUT)
        for r in range(R_FIRST, R_LAST + 1):
            ws.cell(row=r, column=col0 + C_DATE).number_format = DATE_FMT
            ws.cell(row=r, column=col0 + C_AMT).number_format = YEN
            ws.cell(row=r, column=col0 + C_FARE).number_format = YEN
            ws.cell(row=r, column=col0 + C_ADV).alignment = Alignment(horizontal="center")

        pay_col = get_column_letter(col0 + C_PAY)
        adv_col = get_column_letter(col0 + C_ADV)
        dv_pay.add(f"{pay_col}{R_FIRST}:{pay_col}{R_LAST}")
        dv_adv.add(f"{adv_col}{R_FIRST}:{adv_col}{R_LAST}")

        box(ws, R_SUB, col0, R_SUB, c_end, border=BORDER_HEAD,
            fill=PatternFill("solid", fgColor=sub_fill), font=F_SUB)
        ws.merge_cells(start_row=R_SUB, start_column=col0, end_row=R_SUB, end_column=col0 + 1)
        ws.cell(row=R_SUB, column=col0, value="小計").alignment = CENTER
        amt = get_column_letter(col0 + C_AMT)
        fare = get_column_letter(col0 + C_FARE)
        c = ws.cell(row=R_SUB, column=col0 + C_AMT, value=f"=SUM({amt}{R_FIRST}:{amt}{R_LAST})")
        c.number_format = YEN
        c = ws.cell(row=R_SUB, column=col0 + C_FARE, value=f"=SUM({fare}{R_FIRST}:{fare}{R_LAST})")
        c.number_format = YEN

    # --- 共通経費(送料・その他経費) -----------------------------------------
    ws.merge_cells(start_row=R_SEC, start_column=1, end_row=R_SEC, end_column=8)
    box(ws, R_SEC, 1, R_SEC, 8, border=BORDER_HEAD,
        fill=PatternFill("solid", fgColor=C_FEE), font=F_HEAD, align=CENTER)
    ws.cell(row=R_SEC, column=1,
            value="共通経費（送料・その他経費）　※従業員個人に紐づかない経費")

    for title, c1, c2 in (("日付", 1, 1), ("区分", 2, 2), ("内容", 3, 6), ("金額（円）", 7, 8)):
        if c1 != c2:
            ws.merge_cells(start_row=R_SECHEAD, start_column=c1, end_row=R_SECHEAD, end_column=c2)
        box(ws, R_SECHEAD, c1, R_SECHEAD, c2, border=BORDER_HEAD,
            fill=PatternFill("solid", fgColor=C_FEE), font=F_HEAD, align=CENTER)
        ws.cell(row=R_SECHEAD, column=c1, value=title)

    for r in range(R_FEE_FIRST, R_FEE_LAST + 1):
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
        ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=8)
        box(ws, r, 1, r, 8, fill=FILL_INPUT, font=F_INPUT)
        ws.cell(row=r, column=1).number_format = DATE_FMT
        ws.cell(row=r, column=7).number_format = YEN
    dv_kind.add(f"B{R_FEE_FIRST}:B{R_FEE_LAST}")

    ws.merge_cells(start_row=R_FEE_SUB, start_column=1, end_row=R_FEE_SUB, end_column=6)
    ws.merge_cells(start_row=R_FEE_SUB, start_column=7, end_row=R_FEE_SUB, end_column=8)
    box(ws, R_FEE_SUB, 1, R_FEE_SUB, 8, border=BORDER_HEAD,
        fill=PatternFill("solid", fgColor=C_SUBF), font=F_SUB)
    ws.cell(row=R_FEE_SUB, column=1, value="共通経費 小計").alignment = CENTER
    c = ws.cell(row=R_FEE_SUB, column=7, value=f"=SUM(G{R_FEE_FIRST}:G{R_FEE_LAST})")
    c.number_format = YEN

    # --- 当月サマリー(右側 J〜M列) ------------------------------------------
    ws.merge_cells(start_row=R_SEC, start_column=B_COL0, end_row=R_SEC, end_column=B_COL0 + 3)
    box(ws, R_SEC, B_COL0, R_SEC, B_COL0 + 3, border=BORDER_HEAD,
        fill=PatternFill("solid", fgColor=C_SUM), font=F_HEAD, align=CENTER)
    ws.cell(row=R_SEC, column=B_COL0, value="当月サマリー")

    ws.merge_cells(start_row=R_SECHEAD, start_column=B_COL0,
                   end_row=R_SECHEAD, end_column=B_COL0 + 2)
    box(ws, R_SECHEAD, B_COL0, R_SECHEAD, B_COL0 + 3, border=BORDER_HEAD,
        fill=PatternFill("solid", fgColor=C_SUM), font=F_HEAD, align=CENTER)
    ws.cell(row=R_SECHEAD, column=B_COL0, value="項目")
    ws.cell(row=R_SECHEAD, column=B_COL0 + 3, value="金額（円）")

    def col_range(col0, idx):
        col = get_column_letter(col0 + idx)
        return f"{col}{R_FIRST}:{col}{R_LAST}"

    def adv_formula(col0):
        adv = col_range(col0, C_ADV)
        return (f'=SUMIF({adv},"○",{col_range(col0, C_AMT)})'
                f'+SUMIF({adv},"○",{col_range(col0, C_FARE)})')

    fee_kind_rng = f"B{R_FEE_FIRST}:B{R_FEE_LAST}"
    fee_amt_rng = f"G{R_FEE_FIRST}:G{R_FEE_LAST}"
    summary = [
        (f'={EMP_REF[0]}&" 仕入れ合計"', f"={get_column_letter(A_COL0 + C_AMT)}{R_SUB}"),
        (f'={EMP_REF[0]}&" 交通費合計"', f"={get_column_letter(A_COL0 + C_FARE)}{R_SUB}"),
        (f'={EMP_REF[0]}&" 立替精算額（返金額）"', adv_formula(A_COL0)),
        (f'={EMP_REF[1]}&" 仕入れ合計"', f"={get_column_letter(B_COL0 + C_AMT)}{R_SUB}"),
        (f'={EMP_REF[1]}&" 交通費合計"', f"={get_column_letter(B_COL0 + C_FARE)}{R_SUB}"),
        (f'={EMP_REF[1]}&" 立替精算額（返金額）"', adv_formula(B_COL0)),
        ('="共通経費　送料"', f'=SUMIF({fee_kind_rng},"送料",{fee_amt_rng})'),
        ('="共通経費　その他経費"', f'=SUMIF({fee_kind_rng},"その他経費",{fee_amt_rng})'),
    ]
    for i, (label, formula) in enumerate(summary):
        r = R_FEE_FIRST + i
        ws.merge_cells(start_row=r, start_column=B_COL0, end_row=r, end_column=B_COL0 + 2)
        box(ws, r, B_COL0, r, B_COL0 + 3, fill=FILL_AUTO, font=F_AUTO)
        ws.cell(row=r, column=B_COL0, value=label).alignment = Alignment(
            vertical="center", indent=1)
        c = ws.cell(row=r, column=B_COL0 + 3, value=formula)
        c.number_format = YEN

    ws.merge_cells(start_row=R_FEE_SUB, start_column=B_COL0,
                   end_row=R_FEE_SUB, end_column=B_COL0 + 2)
    box(ws, R_FEE_SUB, B_COL0, R_FEE_SUB, B_COL0 + 3, border=BORDER_BOLD,
        fill=PatternFill("solid", fgColor=C_TOTAL), font=F_GRAND)
    ws.cell(row=R_FEE_SUB, column=B_COL0, value="当月 総支出").alignment = CENTER
    mcol = get_column_letter(B_COL0 + 3)
    r0 = R_FEE_FIRST
    c = ws.cell(row=R_FEE_SUB, column=B_COL0 + 3,
                value=f"={mcol}{r0}+{mcol}{r0+1}+{mcol}{r0+3}+{mcol}{r0+4}+G{R_FEE_SUB}")
    c.number_format = YEN

    ws.freeze_panes = f"A{R_FIRST}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{R_EMP}:{R_HEAD}"

# ============================================================================
# 年間集計シート
# ============================================================================
sm = wb.create_sheet("年間集計")
sm.sheet_view.showGridLines = False
sm["A1"] = f"年間集計（{MONTH_SHEETS[0]}〜{MONTH_SHEETS[-1]}）"
sm["A1"].font = F_TITLE
sm["A2"] = "各月シートの「当月サマリー」をそのまま参照しています（このシートに入力欄はありません）。"
sm["A2"].font = F_NOTE

head = ["月シート", "A 仕入れ", "A 交通費", "A 立替精算額", "B 仕入れ", "B 交通費",
        "B 立替精算額", "共通 送料", "共通 その他経費", "当月 総支出"]
HR = 4
for i, t in enumerate(head, start=1):
    c = sm.cell(row=HR, column=i, value=t)
    c.font = F_HEAD
    c.fill = PatternFill("solid", fgColor=C_SUM)
    c.alignment = CENTER_WRAP
    c.border = BORDER_HEAD
sm.row_dimensions[HR].height = 32
sm.cell(row=HR, column=2).comment = Comment(
    "見出しの A / B は「設定」シートの従業員名に対応します（A＝上、B＝下）。", "管理表")

MCOL = get_column_letter(B_COL0 + 3)   # M列(サマリー金額)
for i, name in enumerate(MONTH_SHEETS):
    r = HR + 1 + i
    ref = f"'{name}'!"
    sm.cell(row=r, column=1, value=name)
    for j in range(8):
        sm.cell(row=r, column=2 + j, value=f"={ref}{MCOL}{R_FEE_FIRST + j}")
    sm.cell(row=r, column=10, value=f"={ref}{MCOL}{R_FEE_SUB}")
    box(sm, r, 1, r, 10, fill=FILL_AUTO, font=F_AUTO)
    for c in range(2, 11):
        sm.cell(row=r, column=c).number_format = YEN
    sm.cell(row=r, column=1).alignment = CENTER

TR = HR + 1 + MONTHS
sm.cell(row=TR, column=1, value="年間合計").alignment = CENTER
for c in range(2, 11):
    col = get_column_letter(c)
    cell = sm.cell(row=TR, column=c, value=f"=SUM({col}{HR + 1}:{col}{TR - 1})")
    cell.number_format = YEN
box(sm, TR, 1, TR, 10, border=BORDER_BOLD,
    fill=PatternFill("solid", fgColor=C_TOTAL), font=F_GRAND)

sm.cell(row=TR + 2, column=1,
        value="※「立替精算額（返金額）」＝立替欄に○が付いた行の 仕入れ合計金額＋交通費。従業員へ返金する金額です。").font = F_NOTE
sm.cell(row=TR + 3, column=1,
        value="※「当月 総支出」＝両名の 仕入れ＋交通費 ＋ 共通経費（送料・その他経費）。支払方法や立替の有無は問いません。").font = F_NOTE

sm.column_dimensions["A"].width = 14
for c in range(2, 11):
    sm.column_dimensions[get_column_letter(c)].width = 15
sm.freeze_panes = "B5"

# ============================================================================
# 設定(マスタ)シート
# ============================================================================
st = wb.create_sheet("設定")
st.sheet_view.showGridLines = False
st["A1"] = "設定(マスタ)"
st["A1"].font = F_TITLE
st["A2"] = "ここを書き換えると、各月シートの見出しやプルダウンに反映されます。"
st["A2"].font = F_NOTE

for coord, label in (("B4", "従業員名"), ("D4", "支払方法"), ("F4", "経費区分"), ("H4", "立替")):
    st[coord] = label
    st[coord].font = F_HEAD
    st[coord].fill = PatternFill("solid", fgColor=C_EMP_A)
    st[coord].alignment = CENTER
    st[coord].border = BORDER_HEAD


def put_list(col, values):
    for i, v in enumerate(values):
        cell = st.cell(row=5 + i, column=col, value=v)
        cell.font = F_INPUT
        cell.fill = FILL_INPUT
        cell.border = BORDER


put_list(2, ["従業員A", "従業員B"])
put_list(4, PAY_METHODS)
put_list(6, FEE_KINDS)
put_list(8, ["○"])
st["H5"].alignment = Alignment(horizontal="center")
st["B5"].comment = Comment(
    "各月シートの左側の表（A〜H列）の見出しになります。", "管理表")
st["B6"].comment = Comment(
    "各月シートの右側の表（J〜Q列）の見出しになります。", "管理表")

st["A12"] = "対象期間"
st["A12"].font = F_SUB
st["B12"] = f"{MONTH_SHEETS[0]} 〜 {MONTH_SHEETS[-1]}（月シート {MONTHS} 枚）"
st["B12"].font = F_AUTO
st["A13"] = "※従業員名を変更すると、各月シートと年間集計の見出しも自動で変わります。"
st["A13"].font = F_NOTE
st["A14"] = ("※期間を延長したいときは、最後の月シートを右クリック→「移動またはコピー」でコピーし、"
             "シート名を翌月に変更してください（数式はそのシート内で完結しています）。")
st["A14"].font = F_NOTE
st["A15"] = "※月シートを増やした場合は、「年間集計」シートにも行を追加して同じ形で参照してください。"
st["A15"].font = F_NOTE
st["A16"] = "※従業員が3人以上になる場合は表の追加が必要です（このスクリプトを修正してください）。"
st["A16"].font = F_NOTE

for col, w in (("A", 12), ("B", 40), ("C", 6), ("D", 18), ("E", 3), ("F", 16), ("G", 3), ("H", 8)):
    st.column_dimensions[col].width = w

# ============================================================================
# 記入例(先頭の月シートのみ)
# ============================================================================
first = wb[MONTH_SHEETS[0]]
samples_a = [
    (date(2026, 8, 1), "カードショップ〇〇 秋葉原店", 45000, "現金", "○", "自宅", "秋葉原", 480),
    (date(2026, 8, 1), None, None, None, "○", "秋葉原", "中野", 200),
]
samples_b = [
    (date(2026, 8, 2), "リサイクルショップ△△ 大宮店", 128000, "クレジットカード", None,
     "自宅", "大宮", 640),
]
for col0, rows in ((A_COL0, samples_a), (B_COL0, samples_b)):
    for i, row in enumerate(rows):
        r = R_FIRST + i
        for j, val in enumerate(row):
            cell = first.cell(row=r, column=col0 + j, value=val)
            cell.font = F_SAMPLE
            cell.fill = FILL_SAMPLE
        first.cell(row=r, column=col0 + C_DATE).number_format = DATE_FMT
        first.cell(row=r, column=col0 + C_AMT).number_format = YEN
        first.cell(row=r, column=col0 + C_FARE).number_format = YEN
        first.cell(row=r, column=col0 + C_ADV).alignment = Alignment(horizontal="center")

fee_samples = [
    (date(2026, 8, 3), "送料", "メルカリ発送（ゆうパケットプラス）×5件", 2600),
    (date(2026, 8, 5), "その他経費", "スリーブ・ローダー購入", 3480),
]
for i, (d, kind, memo, amount) in enumerate(fee_samples):
    r = R_FEE_FIRST + i
    box(first, r, 1, r, 8, fill=FILL_SAMPLE, font=F_SAMPLE)
    for c, val in ((1, d), (2, kind), (3, memo), (7, amount)):
        first.cell(row=r, column=c, value=val)
    first.cell(row=r, column=1).number_format = DATE_FMT
    first.cell(row=r, column=7).number_format = YEN

first.cell(row=R_SUB + 1, column=1,
           value="↑ 上の色付きの行は記入例です。ご利用前に内容を削除してください。").font = F_NOTE

# ---- フォントを全セルに適用 --------------------------------------------------
for sheet in wb.worksheets:
    for row in sheet.iter_rows():
        for cell in row:
            f = cell.font
            if f.name != FONT:
                cell.font = Font(name=FONT, size=f.size or 10, bold=f.bold,
                                 italic=f.italic, color=f.color)

wb.active = 0
OUT = "/home/user/toto/excel/トレカ事業_従業員管理表.xlsx"
wb.save(OUT)
print("saved:", OUT, "| sheets:", len(wb.sheetnames))


def fix_fonts_in_styles(path=OUT, font=FONT):
    """recalc.py(LibreOffice)で再計算した後に実行する後処理.

    LibreOffice は Meiryo を持たない環境で styles.xml のフォント名を代替フォントに
    書き換えてしまう。数式のキャッシュ値を壊さないよう xl/styles.xml だけを直接置換する。
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
                # 既定フォント(Calibri)も置換し、空白セルに入力しても書体が揃うようにする
                replaced += text.count('val="Calibri"')
                text = text.replace('val="Calibri"', f'val="{font}"')
                data = text.encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, path)
    return replaced
