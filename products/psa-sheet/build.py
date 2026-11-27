#!/usr/bin/env python3
"""PSA鑑定 収支管理シート (dist/psa-shushi-kanri.xlsx) を生成する。

    python3 products/psa-sheet/build.py

- 必要なもの: openpyxl (pip install openpyxl)
- 何度実行しても同じバイト列のファイルができる(作成日時と zip 内の時刻を固定している)。
- Excel と Googleスプレッドシートの両方にある関数だけを使う
  (IF / AND / OR / IFERROR / SUM / SUMIFS / COUNTIFS / COUNT / COUNTA / ROUND / ROUNDDOWN / MAX / DATE)。
- 1枚あたり費用の式は pokeca/core.py の per_card_costs と同じ。
"""

from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
OUT = HERE / "dist" / "psa-shushi-kanri.xlsx"

VERSION = "1.0.0"
RELEASE = "v1.0"                  # 販売ページ・FAQ・zip 名と揃える表記(make_zip.py も参照)
FIXED_TIME = dt.datetime(2026, 1, 1, 0, 0, 0)  # 再現性のための固定日時

# ---- シート名 --------------------------------------------------------------
S_GUIDE, S_CFG, S_LEDGER, S_ORDER, S_MONTH, S_SIM = (
    "使い方", "設定", "在庫台帳", "注文別集計", "月次集計", "シミュレーター")

LEDGER_ROWS = 500                 # 数式とプルダウンを入れる行数
LEDGER_FIRST, LEDGER_LAST = 2, 1 + LEDGER_ROWS
ORDER_ROWS = 30

STATUSES = ["在庫", "鑑定中", "返却済", "売却済"]
GRADES = ["未鑑定", "PSA10", "PSA9", "PSA8以下"]

# ---- 設定シート: (名前付き範囲, 項目, 初期値, 単位, 説明) ------------------
CFG_FIRST_ROW = 5
SETTINGS = [
    ("cfg_fx", "為替", 155, "円/ドル", "鑑定料などドル建ての費用を円に直すレート"),
    ("cfg_psa_fee_usd", "鑑定料", 79.99, "USD/枚", "PSAに払う1枚あたりの鑑定料"),
    ("cfg_ship_out_jpy", "往路送料", 7700, "円/箱", "日本から米国へ送る1箱ぶんの送料"),
    ("cfg_ship_back_usd", "復路送料", 69.99, "USD/箱", "米国から返送される1箱ぶんの送料"),
    ("cfg_cards_per_box", "1箱の枚数", 20, "枚", "1回の発送に入れる枚数(送料・関税をこの枚数で割る)"),
    ("cfg_us_duty_usd", "米国関税", 30, "USD/箱", "米国側でかかる関税など(1箱あたり)。かからなければ 0"),
    ("cfg_import_tax_pct", "輸入時の税率", 10, "%", "返送品の輸入時にかかる税の率。(鑑定料+復路送料)に掛ける"),
    ("cfg_misc_jpy", "諸経費", 150, "円/枚", "スリーブ・梱包材など1枚あたりの雑費"),
    ("cfg_sell_fee_pct", "販売手数料率", 0, "%", "売却額に対する手数料率(フリマ等)。店頭買取なら 0"),
]
CFG_ROW = {name: CFG_FIRST_ROW + i for i, (name, *_ ) in enumerate(SETTINGS)}
COST_FIRST_ROW = 18               # 1枚あたり費用の内訳
COST_TOTAL_ROW = COST_FIRST_ROW + 6
CFG_CHECK_ROW = 15

# ---- 在庫台帳の列 ----------------------------------------------------------
# (見出し, 幅, 種類)  種類: in=入力 / f=数式
LEDGER_COLS = [
    ("管理番号", 11, "in"), ("状態", 9, "in"), ("カード名", 26, "in"), ("番号", 11, "in"),
    ("仕入日", 12, "in"), ("仕入先", 16, "in"), ("仕入値", 11, "in"), ("PSA注文番号", 14, "in"),
    ("認定番号", 13, "in"), ("グレード", 10, "in"), ("鑑定費用", 11, "f"), ("原価合計", 11, "f"),
    ("売却日", 12, "in"), ("売却先", 16, "in"), ("売却額", 11, "in"), ("販売手数料", 11, "f"),
    ("利益", 11, "f"), ("利益率", 9, "f"),
]
COL = {h: get_column_letter(i + 1) for i, (h, _, _) in enumerate(LEDGER_COLS)}

# サンプルデータ(すべて架空)
D = dt.date
SAMPLES = [
    # 管理番号, 状態, カード名, 番号, 仕入日, 仕入先, 仕入値, 注文番号, 認定番号, グレード, 売却日, 売却先, 売却額
    ("S-001", "在庫", "サンプルカードA", "001/100", D(2026, 1, 10), "サンプル店A", 3000, None, None, "未鑑定", None, None, None),
    ("S-002", "鑑定中", "サンプルカードB", "002/100", D(2026, 1, 10), "サンプル店A", 5000, "SAMPLE-001", None, "未鑑定", None, None, None),
    ("S-003", "返却済", "サンプルカードC", "003/100", D(2026, 1, 12), "サンプル店B", 4000, "SAMPLE-001", "00000003", "PSA9", None, None, None),
    ("S-004", "売却済", "サンプルカードD", "004/100", D(2026, 1, 12), "サンプル店B", 8000, "SAMPLE-001", "00000004", "PSA10", D(2026, 3, 15), "サンプル売却先A", 45000),
    ("S-005", "売却済", "サンプルカードE", "005/100", D(2026, 1, 15), "サンプル店A", 6000, "SAMPLE-001", "00000005", "PSA9", D(2026, 4, 10), "サンプル売却先B", 18000),
]
SAMPLE_YEAR = 2026

# ---- 見た目 ----------------------------------------------------------------
FILL_IN = PatternFill("solid", fgColor="FFF2CC")      # 入力セル = 薄い黄色
FILL_F = PatternFill("solid", fgColor="EDEDED")       # 数式セル = 薄い灰色(触らない)
FILL_HEAD = PatternFill("solid", fgColor="305496")
FILL_HEAD_F = PatternFill("solid", fgColor="595959")
FILL_NOTE = PatternFill("solid", fgColor="FCE4D6")
FONT_HEAD = Font(bold=True, color="FFFFFF")
FONT_TITLE = Font(bold=True, size=14)
FONT_B = Font(bold=True)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
UNLOCK = Protection(locked=False)
FMT_YEN = '#,##0;[Red]-#,##0'
FMT_PCT = '0.0%;[Red]-0.0%'
FMT_DATE = 'yyyy/mm/dd'
WRAP = Alignment(wrap_text=True, vertical="top")


def head(ws, row, col, text, formula=False):
    c = ws.cell(row=row, column=col, value=text)
    c.font, c.fill, c.border = FONT_HEAD, (FILL_HEAD_F if formula else FILL_HEAD), BORDER
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    return c


def inp(ws, ref, value=None, fmt=None):
    c = ws[ref]
    if value is not None:
        c.value = value
    c.fill, c.border, c.protection = FILL_IN, BORDER, UNLOCK
    if fmt:
        c.number_format = fmt
    return c


def calc(ws, ref, formula, fmt=None):
    c = ws[ref]
    c.value, c.fill, c.border = formula, FILL_F, BORDER
    if fmt:
        c.number_format = fmt
    return c


def protect(ws):
    """パスワードなしの保護。入力セル(ロック解除済み)以外をうっかり書き換えないため。"""
    p = ws.protection
    p.sheet = True
    p.formatColumns = False   # 列幅の変更は許可
    p.formatRows = False
    p.formatCells = False


def L(col_name: str) -> str:
    """在庫台帳の列全体への参照。行を足しても集計から漏れないよう列全体を指す。"""
    c = COL[col_name]
    return f"{S_LEDGER}!${c}:${c}"


# ============================================================================
def build_guide(wb):
    ws = wb.active
    ws.title = S_GUIDE
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 96

    r = 1
    ws.cell(row=r, column=2, value="PSA鑑定 収支管理シート").font = FONT_TITLE
    r += 1
    ws.cell(row=r, column=2, value=f"バージョン {VERSION} / Excel・Googleスプレッドシート対応")
    r += 2

    def section(title):
        nonlocal r
        c = ws.cell(row=r, column=2, value=title)
        c.font, c.fill = FONT_HEAD, FILL_HEAD
        ws.cell(row=r, column=3).fill = FILL_HEAD
        r += 1

    def line(label, text, fill=None):
        nonlocal r
        a = ws.cell(row=r, column=2, value=label)
        a.font, a.alignment = FONT_B, WRAP
        b = ws.cell(row=r, column=3, value=text)
        b.alignment = WRAP
        if fill:
            a.fill = fill
            if not label:
                b.fill = fill
        ws.row_dimensions[r].height = 16 * (1 + len(text) // 58 + text.count("\n"))
        r += 1

    section("はじめに開いたら")
    line("Excel の場合", "画面上部に「保護ビュー」の黄色い帯が出たら「編集を有効にする」を押してください。押すまで数式の結果は表示されません。")
    line("Googleスプレッドシートの場合", "Googleスプレッドシートで空のファイルを開き、「ファイル」→「インポート」→「アップロード」でこの xlsx を選び、「新しいスプレッドシートを作成する」で取り込みます。")
    r += 1

    section("使い方(3ステップ)")
    line("ステップ1 設定", "「設定」シートの黄色いセルを、ご自身の実際の為替・鑑定料・送料などに書き換えます。初期値は一例です。")
    line("ステップ2 台帳に記録", "「在庫台帳」に 1行=カード1枚 で記録します。仕入れたら状態を「在庫」、PSAに出したら「鑑定中」とPSA注文番号、返ってきたら「返却済」とグレード、売れたら「売却済」と売却日・売却額を入れます。サンプルの5行は消してから使ってください(黄色いセルだけを選んで Delete)。")
    line("ステップ3 集計を見る", "「注文別集計」にPSA注文番号を入れると注文ごとの収支が、「月次集計」に年を入れると月ごとの売上・利益と自分のPSA10率が出ます。仕入れ前の判断には「シミュレーター」を使います。")
    r += 1

    section("色の意味")
    line("薄い黄色", "入力するセルです。ここだけを書き換えます。", FILL_IN)
    line("薄い灰色", "数式のセルです。触らないでください(自動で計算されます)。", FILL_F)
    r += 1

    section("各シートの役割")
    line(S_CFG, "為替・鑑定料・送料・税率などの前提。ここから「1枚あたりの鑑定費用」が計算され、全シートで使われます。")
    line(S_LEDGER, "カード1枚ごとの記録。鑑定費用・原価合計・販売手数料・利益・利益率は自動計算です。500行ぶん用意しています。")
    line(S_ORDER, "PSA注文番号ごとの枚数・仕入合計・鑑定費用合計・売却合計・利益。30注文ぶん。")
    line(S_MONTH, "指定した年の、売却月ごとの売上・原価・利益・枚数。あわせてグレード別の枚数と割合(PSA10率)。")
    line(S_SIM, "仕入れ前の判断用。仕入れ値と、グレードごとの売値・確率から、期待利益・損益分岐の仕入れ値・仕入れ上限を出します。仕入れ上限は、目標利益率の2つの定義(売却額に対して / 仕入れ値に対して)それぞれで表示します。")
    r += 1

    section("計算のルール")
    line("鑑定費用", "1枚あたり = 鑑定料×為替 + 往路送料÷枚数 + 復路送料×為替÷枚数 + (鑑定料×為替 + 復路送料×為替÷枚数)×税率 + 米国関税×為替÷枚数 + 諸経費(1円未満は四捨五入)。内訳は「設定」シートの下段に表示されます。")
    line("鑑定費用が0になる行", "状態が「在庫」で、かつグレードが「未鑑定」(または空欄)の行は、まだ鑑定に出していないとみなして 0 円です。それ以外の行には1枚あたりの鑑定費用が入ります。")
    line("原価合計", "仕入値 + 鑑定費用。")
    line("販売手数料", "売却額 × 販売手数料率(「設定」シート)。1円未満は四捨五入。")
    line("利益", "売却額 − 販売手数料 − 原価合計。状態が「売却済」で売却額が入っている行だけ表示されます。")
    line("利益率", "利益 ÷ 売却額。在庫台帳・月次集計・シミュレーターの期待利益率は、すべて「売却額に対する割合」です。")
    line("目標利益率の2つの定義", "シミュレーターは仕入れ上限を2通り出します。(1) 売却額に対する利益率 = 利益 ÷ 売却額(在庫台帳・月次集計と同じ定義)。(2) 仕入れ値に対する利益率 = 利益 ÷ 仕入れ値(無料Webツール「PSA鑑定 仕入れ上限 逆算」と同じ定義)。")
    line("", "同じ目標 20% でも、(1) は「売却額の 20% を利益として残す」、(2) は「仕入れ値の 20% を利益として乗せる」という意味です。(1) のほうが条件が厳しいので、仕入れ上限は (1) のほうが低く出ます(初期値の例: (1) 14,100円 / (2) 17,900円)。")
    line("", "どちらが正しいということはありません。使う定義を1つ決めて、いつも同じ行を見てください。シミュレーターの「判定」は (1) の行で判定します。")
    line("月次集計", "状態が「売却済」で、売却日が指定した年月に入る行を集計します。売却日が空欄の行は月次に入りません(月次集計シートのチェック欄に件数が出ます)。")
    r += 1

    section("壊さないためのコツ")
    line("してよいこと", "黄色いセルへの入力・上書き・Delete、行の並べ替え、フィルタ、列幅の変更。")
    line("避けること", "黄色いセルの「切り取り→貼り付け」やドラッグでの移動(数式の参照先がずれます。移すときはコピーして貼り付け、元を Delete)。灰色のセルへの入力。シート名の変更。列の挿入・削除。")
    line("日付の入れ方", "仕入日・売却日は 2026/3/15 の形で入力します。「3月15日ごろ」のような文字は月次集計に入りません。")
    line("番号の入れ方", "管理番号・番号・PSA注文番号・認定番号は文字列として扱います(先頭の0や「001/100」がそのまま残ります)。注文別集計には台帳と同じ表記で注文番号を入れてください。")
    line("500行を超えたら", "在庫台帳の最後の行(501行目)全体をコピーして下の行に貼り付け、黄色いセルを Delete してから使います。集計は列全体を見ているので、そのまま反映されます。")
    line("設定を変えたとき", "「設定」の値を変えると、過去の行を含む全行の鑑定費用が新しい値で計算し直されます。過去の注文の金額を固定したいときは、その行の鑑定費用セルに実際の金額を直接入力してください(その行だけ数式が消えますが、他の計算はそのまま動きます)。")
    line("鑑定済みで買ったカード", "グレードを入れると鑑定費用が自動で入ります。鑑定済みの状態で仕入れたカードは、鑑定費用セルに 0 を直接入力してください。")
    line("エラーが出たら", "#DIV/0! や #VALUE! が出たら、まず「設定」シートのチェック欄を見てください。数式を消してしまった場合は、同じ列の上下の行からコピーするか、購入時のファイルを使い直してください。")
    line("シートの保護", "「設定」「注文別集計」「月次集計」「シミュレーター」は、数式を誤って消さないよう保護しています(パスワードなし)。Excel では「校閲」→「シート保護の解除」で外せます。")
    r += 1

    section("免責")
    line("", "このファイルは収支を記録・試算するための道具です。計算結果の正確さや、利益が出ることを保証するものではありません。", FILL_NOTE)
    line("", "税務(所得の区分・確定申告・消費税など)と関税・輸入時の税の扱いは、取引の内容や時期によって変わります。必ずご自身で、税理士・税務署・税関などの専門家や公的機関に確認してください。「設定」シートの税率・関税の初期値は一例で、実際の税額を示すものではありません。", FILL_NOTE)
    line("", "鑑定料・送料・為替も変わります。初期値は一例です。必ずご自身の実際の金額に書き換えてください。", FILL_NOTE)
    line("", "本ファイルは PSA(Professional Sports Authenticator)社とは関係のない、非公式の個人向けツールです。", FILL_NOTE)
    r += 1

    section("バージョン・よくある質問")
    line(f"バージョン {RELEASE}", "よくある質問は同梱の FAQ(「よくある質問_FAQ.txt」)を参照してください。")


# ============================================================================
def build_settings(wb):
    ws = wb.create_sheet(S_CFG)
    ws.sheet_view.showGridLines = False
    for col, w in zip("ABCD", (26, 14, 10, 62)):
        ws.column_dimensions[col].width = w

    ws["A1"].value, ws["A1"].font = "設定", FONT_TITLE
    ws["A2"].value = "※ 初期値は一例です。必ずご自身の実際の為替・料金・税率に書き換えてください(黄色いセルだけ)。"
    ws["A2"].font = Font(bold=True, color="C00000")

    for i, t in enumerate(["項目", "値", "単位", "説明"], start=1):
        head(ws, CFG_FIRST_ROW - 1, i, t)
    for name, label, value, unit, note in SETTINGS:
        r = CFG_ROW[name]
        ws.cell(row=r, column=1, value=label).border = BORDER
        inp(ws, f"B{r}", value, "0" if name == "cfg_cards_per_box" else "#,##0.00")
        ws.cell(row=r, column=3, value=unit).border = BORDER
        ws.cell(row=r, column=4, value=note).border = BORDER
        wb.defined_names[name] = DefinedName(name, attr_text=f"{S_CFG}!$B${r}")

    first, last = CFG_FIRST_ROW, CFG_FIRST_ROW + len(SETTINGS) - 1
    nbox = CFG_ROW["cfg_cards_per_box"]
    dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=False,
                        showErrorMessage=True, errorTitle="入力エラー", error="0以上の数値を入力してください。")
    dv_box = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="1", allow_blank=False,
                            showErrorMessage=True, errorTitle="入力エラー", error="1以上の整数を入力してください。")
    ws.add_data_validation(dv)
    ws.add_data_validation(dv_box)
    for r in range(first, last + 1):
        (dv_box if r == nbox else dv).add(f"B{r}")

    ws.cell(row=CFG_CHECK_ROW, column=1, value="設定チェック").font = FONT_B
    calc(ws, f"B{CFG_CHECK_ROW}",
         f'=IF(COUNT($B${first}:$B${last})<{len(SETTINGS)},"要確認",IF(cfg_cards_per_box<1,"要確認","OK"))')
    ws.cell(row=CFG_CHECK_ROW, column=4,
            value="「要確認」のときは、上の9項目に空欄・文字が無いか、1箱の枚数が1以上かを確認してください。")

    # ---- 1枚あたり費用の内訳 (pokeca/core.py per_card_costs と同じ式) ----
    r0 = COST_FIRST_ROW
    ws.cell(row=r0 - 2, column=1, value="1枚あたりの鑑定費用(自動計算)").font = FONT_B
    for i, t in enumerate(["内訳", "円/枚", "", "式"], start=1):
        head(ws, r0 - 1, i, t, formula=True)
    rows = [
        ("鑑定料", "=cfg_psa_fee_usd*cfg_fx", "鑑定料 × 為替"),
        ("往路送料", "=cfg_ship_out_jpy/cfg_cards_per_box", "往路送料 ÷ 1箱の枚数"),
        ("復路送料", "=cfg_ship_back_usd*cfg_fx/cfg_cards_per_box", "復路送料 × 為替 ÷ 1箱の枚数"),
        ("輸入時の税", f"=(B{r0}+B{r0 + 2})*cfg_import_tax_pct/100", "(鑑定料 + 復路送料) × 税率"),
        ("米国関税", "=cfg_us_duty_usd*cfg_fx/cfg_cards_per_box", "米国関税 × 為替 ÷ 1箱の枚数"),
        ("諸経費", "=cfg_misc_jpy", "諸経費"),
    ]
    for i, (label, formula, note) in enumerate(rows):
        r = r0 + i
        ws.cell(row=r, column=1, value=label).border = BORDER
        calc(ws, f"B{r}", formula, "#,##0.00")
        ws.cell(row=r, column=4, value=note).border = BORDER
    rt = COST_TOTAL_ROW
    ws.cell(row=rt, column=1, value="合計(1枚あたり・円)").font = FONT_B
    ws.cell(row=rt, column=1).border = BORDER
    calc(ws, f"B{rt}", f"=ROUND(SUM(B{r0}:B{rt - 1}),0)", "#,##0").font = FONT_B
    ws.cell(row=rt, column=4, value="上の6項目の合計を1円単位に四捨五入。在庫台帳・シミュレーターはこの値を使います。").border = BORDER
    wb.defined_names["cfg_cost_per_card"] = DefinedName("cfg_cost_per_card", attr_text=f"{S_CFG}!$B${rt}")

    ws.cell(row=rt + 2, column=1,
            value="※ 税率・関税の初期値は一例で、実際の税額を示すものではありません。税務・関税の扱いは各自で専門家に確認してください。")
    protect(ws)


# ============================================================================
def ledger_formulas(r: int) -> dict[str, str]:
    c = {h: f"${col}{r}" for h, col in COL.items()}
    blank = f'COUNTA($A{r}:$J{r})=0'   # 入力列(A〜J)が全部空なら未入力行
    return {
        "鑑定費用": f'=IF({blank},"",IF(AND(OR({c["状態"]}="",{c["状態"]}="在庫"),'
                    f'OR({c["グレード"]}="",{c["グレード"]}="未鑑定")),0,cfg_cost_per_card))',
        "原価合計": f'=IF({c["鑑定費用"]}="","",{c["仕入値"]}+{c["鑑定費用"]})',
        "販売手数料": f'=IF(OR({c["鑑定費用"]}="",{c["売却額"]}=""),"",ROUND({c["売却額"]}*cfg_sell_fee_pct/100,0))',
        "利益": f'=IF(AND({c["状態"]}="売却済",{c["販売手数料"]}<>""),{c["売却額"]}-{c["販売手数料"]}-{c["原価合計"]},"")',
        "利益率": f'=IF({c["利益"]}="","",IF({c["売却額"]}=0,"",{c["利益"]}/{c["売却額"]}))',
    }


def build_ledger(wb):
    ws = wb.create_sheet(S_LEDGER)
    for i, (h, w, kind) in enumerate(LEDGER_COLS, start=1):
        head(ws, 1, i, h, formula=(kind == "f"))
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 22

    fmts = {"仕入日": FMT_DATE, "売却日": FMT_DATE, "仕入値": FMT_YEN, "売却額": FMT_YEN,
            "鑑定費用": FMT_YEN, "原価合計": FMT_YEN, "販売手数料": FMT_YEN, "利益": FMT_YEN, "利益率": FMT_PCT,
            "管理番号": "@", "番号": "@", "PSA注文番号": "@", "認定番号": "@"}
    sample_keys = ["管理番号", "状態", "カード名", "番号", "仕入日", "仕入先", "仕入値",
                   "PSA注文番号", "認定番号", "グレード", "売却日", "売却先", "売却額"]

    for r in range(LEDGER_FIRST, LEDGER_LAST + 1):
        f = ledger_formulas(r)
        for h, _, kind in LEDGER_COLS:
            ref = f"{COL[h]}{r}"
            if kind == "f":
                calc(ws, ref, f[h], fmts.get(h))
            else:
                inp(ws, ref, None, fmts.get(h))
    for i, row in enumerate(SAMPLES):
        for h, v in zip(sample_keys, row):
            if v is not None:
                ws[f"{COL[h]}{LEDGER_FIRST + i}"].value = v

    rng = lambda h: f"{COL[h]}{LEDGER_FIRST}:{COL[h]}{LEDGER_LAST}"
    dv_status = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True,
                               showErrorMessage=True, errorTitle="入力エラー", error="リストから選んでください。")
    dv_grade = DataValidation(type="list", formula1='"' + ",".join(GRADES) + '"', allow_blank=True,
                              showErrorMessage=True, errorTitle="入力エラー", error="リストから選んでください。")
    dv_money = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                              showErrorMessage=True, errorTitle="入力エラー", error="0以上の数値(円)を入力してください。")
    dv_date = DataValidation(type="date", operator="greaterThanOrEqual", formula1="36526", allow_blank=True,
                             showErrorMessage=True, errorTitle="入力エラー",
                             error="日付を 2026/3/15 の形で入力してください。")
    for dv in (dv_status, dv_grade, dv_money, dv_date):
        ws.add_data_validation(dv)
    dv_status.add(rng("状態"))
    dv_grade.add(rng("グレード"))
    dv_money.add(rng("仕入値"))
    dv_money.add(rng("売却額"))
    dv_date.add(rng("仕入日"))
    dv_date.add(rng("売却日"))

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(LEDGER_COLS))}{LEDGER_LAST}"
    # 並べ替え・フィルタ・行削除を妨げないよう、このシートは保護しない。


# ============================================================================
def build_orders(wb):
    ws = wb.create_sheet(S_ORDER)
    ws["A1"].value, ws["A1"].font = "注文別集計", FONT_TITLE
    ws["A2"].value = "黄色いセルにPSA注文番号を入れると、在庫台帳の同じ注文番号の行を集計します(台帳と同じ表記で入力)。"
    cols = [
        ("PSA注文番号", 16, None),
        ("枚数", 8, f'COUNTIFS({L("PSA注文番号")},$A{{r}})'),
        ("仕入合計", 12, f'SUMIFS({L("仕入値")},{L("PSA注文番号")},$A{{r}})'),
        ("鑑定費用合計", 13, f'SUMIFS({L("鑑定費用")},{L("PSA注文番号")},$A{{r}})'),
        ("原価合計", 12, f'SUMIFS({L("原価合計")},{L("PSA注文番号")},$A{{r}})'),
        ("売却済枚数", 11, f'COUNTIFS({L("PSA注文番号")},$A{{r}},{L("状態")},"売却済")'),
        ("売却合計", 12, f'SUMIFS({L("売却額")},{L("PSA注文番号")},$A{{r}},{L("状態")},"売却済")'),
        ("販売手数料", 12, f'SUMIFS({L("販売手数料")},{L("PSA注文番号")},$A{{r}},{L("状態")},"売却済")'),
        ("利益(売却済ぶん)", 15, f'SUMIFS({L("利益")},{L("PSA注文番号")},$A{{r}})'),
        ("未売却の原価", 13, f'SUMIFS({L("原価合計")},{L("PSA注文番号")},$A{{r}},{L("状態")},"<>売却済")'),
        ("PSA10枚数", 11, f'COUNTIFS({L("PSA注文番号")},$A{{r}},{L("グレード")},"PSA10")'),
    ]
    hr = 4
    first, last = hr + 1, hr + ORDER_ROWS
    for i, (h, w, f) in enumerate(cols, start=1):
        head(ws, hr, i, h, formula=f is not None)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[hr].height = 22
    count_cols = {"枚数", "売却済枚数", "PSA10枚数"}
    for r in range(first, last + 1):
        inp(ws, f"A{r}", None, "@")
        for i, (h, _, f) in enumerate(cols[1:], start=2):
            calc(ws, f"{get_column_letter(i)}{r}", f'=IF($A{r}="","",{f.format(r=r)})',
                 "#,##0" if h in count_cols else FMT_YEN)
    ws[f"A{first}"].value = "SAMPLE-001"

    tr = last + 1
    c = ws.cell(row=tr, column=1, value="合計")
    c.font, c.border = FONT_B, BORDER
    for i, (h, _, _) in enumerate(cols[1:], start=2):
        col = get_column_letter(i)
        calc(ws, f"{col}{tr}", f"=SUM({col}{first}:{col}{last})",
             "#,##0" if h in count_cols else FMT_YEN).font = FONT_B
    ws.cell(row=tr + 2, column=1,
            value="※ 利益は売却済の行だけの合計です。まだ売れていないカードの原価は「未売却の原価」に出ます。")
    ws.cell(row=tr + 3, column=1,
            value="※ 同じ注文番号を2行に入れると合計行が二重になります。1注文は1行にしてください。")
    ws.freeze_panes = f"B{first}"
    protect(ws)
    return first, last


# ============================================================================
MONTH_YEAR_CELL = "$B$3"
MONTH_FIRST = 6


def build_monthly(wb):
    ws = wb.create_sheet(S_MONTH)
    ws.sheet_view.showGridLines = False
    for col, w in zip("ABCDEFG", (22, 13, 13, 13, 13, 9, 10)):
        ws.column_dimensions[col].width = w
    ws["A1"].value, ws["A1"].font = "月次集計", FONT_TITLE
    ws["A2"].value = "年を入れると、その年に売却した(状態=売却済・売却日あり)カードを月ごとに集計します。"
    ws["A3"].value, ws["A3"].font = "集計する年(西暦)", FONT_B
    inp(ws, "B3", SAMPLE_YEAR, "0")
    dv = DataValidation(type="whole", operator="between", formula1="2000", formula2="2100", allow_blank=False,
                        showErrorMessage=True, errorTitle="入力エラー", error="西暦を4桁で入力してください(例: 2026)。")
    ws.add_data_validation(dv)
    dv.add("B3")

    hr = MONTH_FIRST - 1
    for i, t in enumerate(["売却月", "売上", "原価", "販売手数料", "利益", "枚数", "利益率"], start=1):
        head(ws, hr, i, t, formula=True)
    sold = f'{L("状態")},"売却済"'
    for m in range(1, 13):
        r = MONTH_FIRST + m - 1
        c = ws.cell(row=r, column=1, value=m)
        c.number_format, c.border, c.alignment = '0"月"', BORDER, Alignment(horizontal="center")
        period = (f'{L("売却日")},">="&DATE({MONTH_YEAR_CELL},$A{r},1),'
                  f'{L("売却日")},"<"&DATE({MONTH_YEAR_CELL},$A{r}+1,1)')
        calc(ws, f"B{r}", f'=SUMIFS({L("売却額")},{sold},{period})', FMT_YEN)
        calc(ws, f"C{r}", f'=SUMIFS({L("原価合計")},{sold},{period})', FMT_YEN)
        calc(ws, f"D{r}", f'=SUMIFS({L("販売手数料")},{sold},{period})', FMT_YEN)
        calc(ws, f"E{r}", f'=SUMIFS({L("利益")},{sold},{period})', FMT_YEN)
        calc(ws, f"F{r}", f'=COUNTIFS({sold},{period})', "#,##0")
        calc(ws, f"G{r}", f'=IF(B{r}=0,"",E{r}/B{r})', FMT_PCT)
    first, last = MONTH_FIRST, MONTH_FIRST + 11
    tr = last + 1
    c = ws.cell(row=tr, column=1, value="年間合計")
    c.font, c.border, c.alignment = FONT_B, BORDER, Alignment(horizontal="center")
    for col in "BCDEF":
        calc(ws, f"{col}{tr}", f"=SUM({col}{first}:{col}{last})", "#,##0" if col == "F" else FMT_YEN).font = FONT_B
    calc(ws, f"G{tr}", f'=IF(B{tr}=0,"",E{tr}/B{tr})', FMT_PCT).font = FONT_B

    # ---- チェック欄 ----
    cr = tr + 2
    ws.cell(row=cr, column=1, value="チェック").font = FONT_B
    ws.cell(row=cr + 1, column=1, value="売却日が無い売却済の行")
    calc(ws, f"B{cr + 1}", f'=COUNTIFS({sold})-COUNTIFS({sold},{L("売却日")},">0")', "#,##0")
    ws.cell(row=cr + 1, column=3, value="← 0 でなければ、在庫台帳で売却日が空欄か、日付ではなく文字になっている行があります(月次に入りません)。")
    ws.cell(row=cr + 2, column=1, value="売却額が無い売却済の行")
    calc(ws, f"B{cr + 2}", f'=COUNTIFS({sold})-COUNTIFS({sold},{L("売却額")},">=0")', "#,##0")
    ws.cell(row=cr + 2, column=3, value="← 0 でなければ、売却済なのに売却額が空欄の行があります(利益が計算されません)。")

    # ---- グレード別 ----
    gr = cr + 5
    ws.cell(row=gr, column=1, value="グレード別の枚数と割合(在庫台帳の全期間)").font = FONT_B
    for i, t in enumerate(["グレード", "枚数", "割合"], start=1):
        head(ws, gr + 1, i, t, formula=True)
    g_first = gr + 2
    graded = ["PSA10", "PSA9", "PSA8以下"]
    g_total = g_first + len(graded)
    for i, g in enumerate(graded):
        r = g_first + i
        ws.cell(row=r, column=1, value=g).border = BORDER
        calc(ws, f"B{r}", f'=COUNTIFS({L("グレード")},$A{r})', "#,##0")
        calc(ws, f"C{r}", f'=IF($B${g_total}=0,"",B{r}/$B${g_total})', "0.0%")
    c = ws.cell(row=g_total, column=1, value="鑑定結果が出た枚数")
    c.font, c.border = FONT_B, BORDER
    calc(ws, f"B{g_total}", f"=SUM(B{g_first}:B{g_total - 1})", "#,##0").font = FONT_B
    calc(ws, f"C{g_total}", f'=IF(B{g_total}=0,"",1)', "0.0%")
    ws.cell(row=g_total + 1, column=1, value="未鑑定(参考)").border = BORDER
    calc(ws, f"B{g_total + 1}", f'=COUNTIFS({L("グレード")},"未鑑定")', "#,##0")
    ws.cell(row=g_total + 3, column=1,
            value="※ 割合は「鑑定結果が出た枚数」に対するものです。PSA10 の行の割合が、あなたのPSA10率です。")
    ws.cell(row=g_total + 4, column=1,
            value="※ 枚数が少ないうちは率が大きくぶれます。シミュレーターに入れる確率の参考にするときは注意してください。")
    protect(ws)
    return {"first": first, "total": tr, "check": cr + 1, "g_first": g_first, "g_total": g_total}


# ============================================================================
SIM = {"buy": "B4", "p10": "B8", "p9": "B9", "low": "B10", "q10": "C8", "q9": "C9", "qlow": "C10",
       "target": "B13", "cost": "B17", "esale": "B18", "efee": "B19", "eprofit": "B20", "erate": "B21",
       "breakeven": "B22",
       # 仕入れ上限は目標利益率の定義ごとに1行。B列 = 100円単位に切り下げ、C列 = 切り下げ前(1円未満切り捨て)
       "maxbuy": "B23", "maxbuy_exact": "C23",              # 売却額に対する利益率(月次集計と同じ定義)
       "maxbuy_onbuy": "B24", "maxbuy_onbuy_exact": "C24",  # 仕入れ値に対する利益率(無料ツール・core.py recommend と同じ定義)
       "verdict": "B25", "g10": "B28", "g9": "B29", "glow": "B30"}


def build_sim(wb):
    ws = wb.create_sheet(S_SIM)
    ws.sheet_view.showGridLines = False
    for col, w in zip("ABCD", (38, 16, 16, 70)):
        ws.column_dimensions[col].width = w
    s = SIM
    ws["A1"].value, ws["A1"].font = "シミュレーター(仕入れ前の判断用)", FONT_TITLE
    ws["A2"].value = "黄色いセルを入れると、1枚を仕入れて鑑定に出したときの期待値が出ます。入力済みの数字は一例です。"

    ws["A4"].value = "仕入れ値(円)"
    inp(ws, s["buy"], 8000, FMT_YEN)

    for i, t in enumerate(["鑑定結果", "売値(円)", "確率(%)"], start=1):
        head(ws, 7, i, t)
    ws["A8"].value, ws["A9"].value, ws["A10"].value = "PSA10 だった場合", "PSA9 だった場合", "それ以下だった場合"
    inp(ws, s["p10"], 60000, FMT_YEN)
    inp(ws, s["p9"], 15000, FMT_YEN)
    inp(ws, s["low"], 5000, FMT_YEN)
    inp(ws, s["q10"], 50, "0.0")
    inp(ws, s["q9"], 40, "0.0")
    calc(ws, s["qlow"], f"=100-{s['q10']}-{s['q9']}", "0.0")
    ws["D10"].value = "← 「それ以下」の確率は 100 − PSA10 − PSA9 で自動計算(合計が必ず100%になるように)"
    ws["A11"].value = "確率のチェック"
    calc(ws, "B11", f'=IF(COUNT({s["q10"]}:{s["q9"]})<2,"確率を入力",IF({s["qlow"]}<0,"合計が100%超",'
                    f'IF(OR({s["q10"]}<0,{s["q9"]}<0),"マイナス不可","OK")))')

    ws["A13"].value = "目標利益率(%)"
    inp(ws, s["target"], 20, "0.0")
    ws["D13"].value = "← 下の「仕入れ上限」の2行で使います(売却額に対する利益率 / 仕入れ値に対する利益率 の2通り)"

    dv_money = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=False,
                              showErrorMessage=True, errorTitle="入力エラー", error="0以上の数値を入力してください。")
    dv_pct = DataValidation(type="decimal", operator="between", formula1="0", formula2="100", allow_blank=False,
                            showErrorMessage=True, errorTitle="入力エラー", error="0〜100の数値(%)を入力してください。")
    ws.add_data_validation(dv_money)
    ws.add_data_validation(dv_pct)
    for k in ("buy", "p10", "p9", "low"):
        dv_money.add(s[k])
    for k in ("q10", "q9", "target"):
        dv_pct.add(s[k])

    head(ws, 16, 1, "結果", formula=True)
    head(ws, 16, 2, "円", formula=True)
    head(ws, 16, 3, "切り下げ前(円)", formula=True)
    esale_expr = f"({s['p10']}*{s['q10']}+{s['p9']}*{s['q9']}+{s['low']}*{s['qlow']})/100"
    rows = [
        ("cost", "1枚あたりの鑑定費用", "=cfg_cost_per_card", FMT_YEN, "「設定」シートの合計"),
        ("esale", "期待売値", f"={esale_expr}", FMT_YEN, "売値 × 確率 の合計"),
        ("efee", "期待販売手数料", f"={s['esale']}*cfg_sell_fee_pct/100", FMT_YEN, "期待売値 × 販売手数料率(「設定」シート)"),
        ("eprofit", "期待利益", f"={s['esale']}-{s['efee']}-{s['cost']}-{s['buy']}", FMT_YEN,
         "期待売値 − 販売手数料 − 鑑定費用 − 仕入れ値"),
        ("erate", "期待利益率", f'=IF({s["esale"]}=0,"",{s["eprofit"]}/{s["esale"]})', FMT_PCT, "期待利益 ÷ 期待売値"),
        ("breakeven", "損益分岐の仕入れ値", f"={s['esale']}-{s['efee']}-{s['cost']}", FMT_YEN,
         "この値より安く仕入れれば期待利益がプラス(マイナス表示なら、いくらで仕入れても期待値は赤字)"),
        ("maxbuy_exact", None,
         f"=ROUNDDOWN({s['esale']}*(1-cfg_sell_fee_pct/100-{s['target']}/100)-{s['cost']},0)", FMT_YEN, None),
        ("maxbuy", "仕入れ上限(売却額に対する利益率)", f"=MAX(0,ROUNDDOWN({s['maxbuy_exact']},-2))", FMT_YEN,
         "利益 ÷ 売却額 が目標以上になる上限。在庫台帳・月次集計の利益率と同じ定義。"
         "式: 期待売値 ×(1 − 手数料率 − 目標)− 鑑定費用"),
        ("maxbuy_onbuy_exact", None, f"=ROUNDDOWN({s['breakeven']}/(1+{s['target']}/100),0)", FMT_YEN, None),
        ("maxbuy_onbuy", "仕入れ上限(仕入れ値に対する利益率)", f"=MAX(0,ROUNDDOWN({s['maxbuy_onbuy_exact']},-2))", FMT_YEN,
         "利益 ÷ 仕入れ値 が目標以上になる上限。無料ツール「PSA鑑定 仕入れ上限 逆算」と同じ定義。"
         "式: 損益分岐の仕入れ値 ÷(1 + 目標)"),
        ("verdict", "判定",
         f'=IF(B11<>"OK","確率を確認",IF({s["buy"]}<={s["maxbuy"]},"目標内",'
         f'IF({s["buy"]}<={s["breakeven"]},"黒字見込み(目標未満)","期待値は赤字")))', None,
         "仕入れ値を「仕入れ上限(売却額に対する利益率)」・損益分岐と比べた結果"),
    ]
    for key, label, formula, fmt, note in rows:
        r = int(s[key][1:])
        calc(ws, s[key], formula, fmt)
        if label is None:          # C列(切り下げ前)。見出しと説明は同じ行のB列側で付ける
            continue
        ws.cell(row=r, column=1, value=label).border = BORDER
        ws.cell(row=r, column=4, value="← " + note)
    for k in ("eprofit", "maxbuy", "maxbuy_onbuy", "verdict"):
        ws[s[k]].font = FONT_B
    ws[s["verdict"]].alignment = Alignment(horizontal="right")

    head(ws, 27, 1, "結果ごとの利益", formula=True)
    head(ws, 27, 2, "円", formula=True)
    for key, label, price in (("g10", "PSA10 だった場合の利益", "p10"), ("g9", "PSA9 だった場合の利益", "p9"),
                              ("glow", "それ以下だった場合の利益", "low")):
        r = int(s[key][1:])
        ws.cell(row=r, column=1, value=label).border = BORDER
        calc(ws, s[key], f"={s[price]}-ROUND({s[price]}*cfg_sell_fee_pct/100,0)-{s['cost']}-{s['buy']}", FMT_YEN)
    ws["D28"].value = "← 売値 − 販売手数料 − 鑑定費用 − 仕入れ値"

    ws["A33"].value = "※ 期待値は「同じ条件で何枚も繰り返したときの平均」です。1枚ごとの結果は上の「結果ごとの利益」のどれかになります。"
    ws["A34"].value = "※ 確率と売値はご自身の見立てです。このシートは将来の相場や鑑定結果を予測するものではありません。"
    ws["A35"].value = ("※ 仕入れ上限は、B列が100円単位に切り下げた値(マイナスなら 0)、C列が切り下げ前の値(1円未満切り捨て)です。"
                       "2行の違いは目標利益率の定義だけで、「売却額に対する利益率」の行のほうが低く出ます。")
    protect(ws)


# ============================================================================
def build_workbook() -> Workbook:
    wb = Workbook()
    build_guide(wb)
    build_settings(wb)
    build_ledger(wb)
    build_orders(wb)
    build_monthly(wb)
    build_sim(wb)
    wb.calculation.fullCalcOnLoad = True      # 開いたときに必ず再計算させる
    p = wb.properties
    p.creator = p.lastModifiedBy = "psa-sheet build.py"
    p.title = "PSA鑑定 収支管理シート"
    p.created = p.modified = FIXED_TIME
    return wb


def save_deterministic(wb: Workbook, path: Path) -> None:
    """zip 内のタイムスタンプを固定して保存する(再実行で同じバイト列にするため)。"""
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(buf) as src, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            data = src.read(item.filename)
            if item.filename == "docProps/core.xml":
                # openpyxl は保存時に更新日時を現在時刻で上書きするので、固定値に戻す
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                              rb"\g<1>" + FIXED_TIME.strftime("%Y-%m-%dT%H:%M:%SZ").encode() + rb"\g<2>", data)
            dst.writestr(info, data)


def main() -> None:
    save_deterministic(build_workbook(), OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
