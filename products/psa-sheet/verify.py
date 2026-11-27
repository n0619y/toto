#!/usr/bin/env python3
"""dist/psa-shushi-kanri.xlsx の検証。

    python3 products/psa-sheet/verify.py

やること
  1. 静的点検 (openpyxl): 使っている関数が許可リスト内か、参照先のシート・名前付き範囲が
     存在するか、#REF! などが数式に混じっていないか、500行ぶん同じ数式・プルダウンが入っているか。
  2. 手計算との突き合わせ: サンプル5行の期待値(下の HAND_* 定数。電卓で出した値を直書き)を、
     このファイル内の Python モデル(シートの数式とは別実装)と、pokeca/core.py の per_card_costs と比べる。
  3. LibreOffice があれば、xlsx を実際に再計算して全セルの値を Python モデルと比べ、
     エラー値(#REF! #NAME? #VALUE! #DIV/0! #N/A, Err:5xx)が1つも無いことを確かめる。
     出荷状態のファイルに加えて、設定を変え、境界ケースの行を足した「負荷シナリオ」でも同じことをする。

確かめられないこと
  - Microsoft Excel と Googleスプレッドシートでの実際の表示・再計算(この環境には無い)。
    LibreOffice で通ることは、その2つで通ることの保証ではない。
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.formula import Tokenizer
from openpyxl.formula.translate import Translator

HERE = Path(__file__).resolve().parent
XLSX = HERE / "dist" / "psa-shushi-kanri.xlsx"
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402  (シートの位置定数だけを借りる。計算式は借りない)

ALLOWED_FUNCS = {"IF", "AND", "OR", "SUM", "SUMIFS", "COUNTIFS", "COUNT", "COUNTA",
                 "ROUND", "ROUNDDOWN", "MAX", "DATE"}
ERROR_VALUES = {"#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#N/A", "#NUM!", "#NULL!"}
ERROR_MARKERS = ("#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#N/A", "#NUM!", "#NULL!", "Err:")

# ---- 手計算の期待値(初期設定 155 / 79.99 / 7700 / 69.99 / 20 / 30 / 10 / 150 / 0) ----
#   鑑定料      79.99 × 155                 = 12,398.45
#   往路送料    7,700 ÷ 20                  =    385
#   復路送料    69.99 × 155 ÷ 20            =    542.4225
#   輸入時の税  (12,398.45 + 542.4225) × 10% =  1,294.08725
#   米国関税    30 × 155 ÷ 20               =    232.5
#   諸経費                                  =    150
#   合計 15,002.45975 → 四捨五入して 15,002 円/枚
HAND_COST = 15002
HAND_LEDGER = {  # 行: (鑑定費用, 原価合計, 販売手数料, 利益)
    2: (0, 3000, None, None),            # 在庫・未鑑定        → 鑑定費用 0
    3: (15002, 20002, None, None),       # 鑑定中              → 5,000 + 15,002
    4: (15002, 19002, None, None),       # 返却済 PSA9         → 4,000 + 15,002
    5: (15002, 23002, 0, 21998),         # 売却済 45,000 − 0 − 23,002
    6: (15002, 21002, 0, -3002),         # 売却済 18,000 − 0 − 21,002
}
HAND_MONTH = {3: (45000, 23002, 0, 21998, 1), 4: (18000, 21002, 0, -3002, 1)}  # 月: 売上, 原価, 手数料, 利益, 枚数
HAND_YEAR = (63000, 44004, 0, 18996, 2)
HAND_ORDER = {"枚数": 4, "仕入合計": 23000, "鑑定費用合計": 60008, "原価合計": 83008, "売却済枚数": 2,
              "売却合計": 63000, "販売手数料": 0, "利益": 18996, "未売却の原価": 39004, "PSA10枚数": 1}
HAND_GRADES = {"PSA10": 1, "PSA9": 2, "PSA8以下": 0}
# シミュレーター初期値: 仕入 8,000 / 60,000×50% + 15,000×40% + 5,000×10% = 36,500
HAND_SIM = {"esale": 36500, "efee": 0, "eprofit": 13498, "breakeven": 21498, "maxbuy": 14100,
            "g10": 36998, "g9": -8002, "glow": -18002}

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def check(name: str, problems: list[str], extra: str = "") -> None:
    if problems:
        record("NG", name, f"{len(problems)}件: " + " / ".join(problems[:5]))
    else:
        record("OK", name, extra)


def rhu(x: float) -> int:
    """Excel の ROUND(x,0) と同じ四捨五入(Python の round は偶数丸めなので使わない)。"""
    return int(Decimal(repr(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def close(a, b) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))
    return a == b


# ============================================================================
# Python モデル(シートの数式とは独立に書いた再実装)
# ============================================================================
def read_inputs(wb) -> dict:
    """数式ではない入力値だけを読む。"""
    cfg = {name: wb[B.S_CFG][f"B{row}"].value for name, row in B.CFG_ROW.items()}
    ws = wb[B.S_LEDGER]
    heads = [h for h, _, kind in B.LEDGER_COLS if kind == "in"]
    rows = {}
    for r in range(B.LEDGER_FIRST, ws.max_row + 1):
        vals = {h: ws[f"{B.COL[h]}{r}"].value for h in heads}
        rows[r] = {h: (v.date() if isinstance(v, dt.datetime) else v) for h, v in vals.items()}
    orders = {r: wb[B.S_ORDER][f"A{r}"].value for r in range(5, 5 + B.ORDER_ROWS)}
    sim = {k: wb[B.S_SIM][B.SIM[k]].value for k in ("buy", "p10", "p9", "low", "q10", "q9", "target")}
    return {"cfg": cfg, "rows": rows, "orders": orders, "year": wb[B.S_MONTH]["B3"].value, "sim": sim}


def model_cost_parts(cfg: dict) -> dict:
    fx, n = cfg["cfg_fx"], cfg["cfg_cards_per_box"]
    grading = cfg["cfg_psa_fee_usd"] * fx
    ship_back = cfg["cfg_ship_back_usd"] * fx / n
    return {"grading": grading, "ship_out": cfg["cfg_ship_out_jpy"] / n, "ship_back": ship_back,
            "import_tax": (grading + ship_back) * cfg["cfg_import_tax_pct"] / 100,
            "us_duty": cfg["cfg_us_duty_usd"] * fx / n, "misc": cfg["cfg_misc_jpy"]}


def model(inp: dict) -> dict:
    cfg = inp["cfg"]
    cost = rhu(sum(model_cost_parts(cfg).values()))
    fee_pct = cfg["cfg_sell_fee_pct"]
    in_heads = [h for h, _, kind in B.LEDGER_COLS if kind == "in"][:10]   # A〜J
    led = {}
    for r, v in inp["rows"].items():
        if all(v[h] in (None, "") for h in in_heads):
            led[r] = dict.fromkeys(("鑑定費用", "原価合計", "販売手数料", "利益", "利益率"))
            continue
        raw = (v["状態"] in (None, "在庫")) and (v["グレード"] in (None, "未鑑定"))
        k = 0 if raw else cost
        total = (v["仕入値"] or 0) + k
        fee = None if v["売却額"] is None else rhu(v["売却額"] * fee_pct / 100)
        profit = v["売却額"] - fee - total if (v["状態"] == "売却済" and fee is not None) else None
        rate = profit / v["売却額"] if (profit is not None and v["売却額"] != 0) else None
        led[r] = {"鑑定費用": k, "原価合計": total, "販売手数料": fee, "利益": profit, "利益率": rate}

    rows = [dict(inp["rows"][r], **led[r]) for r in inp["rows"]]
    num = lambda x: x if isinstance(x, (int, float)) else 0
    sold = [x for x in rows if x["状態"] == "売却済"]

    orders = {}
    for r, no in inp["orders"].items():
        if no in (None, ""):
            orders[r] = None
            continue
        mine = [x for x in rows if x["PSA注文番号"] == no]
        ms = [x for x in mine if x["状態"] == "売却済"]
        orders[r] = {"枚数": len(mine), "仕入合計": sum(num(x["仕入値"]) for x in mine),
                     "鑑定費用合計": sum(num(x["鑑定費用"]) for x in mine),
                     "原価合計": sum(num(x["原価合計"]) for x in mine), "売却済枚数": len(ms),
                     "売却合計": sum(num(x["売却額"]) for x in ms),
                     "販売手数料": sum(num(x["販売手数料"]) for x in ms),
                     "利益": sum(num(x["利益"]) for x in mine),
                     "未売却の原価": sum(num(x["原価合計"]) for x in mine if x["状態"] != "売却済"),
                     "PSA10枚数": sum(1 for x in mine if x["グレード"] == "PSA10")}

    months = {}
    for m in range(1, 13):
        ms = [x for x in sold if isinstance(x["売却日"], dt.date)
              and (x["売却日"].year, x["売却日"].month) == (inp["year"], m)]
        months[m] = (sum(num(x["売却額"]) for x in ms), sum(num(x["原価合計"]) for x in ms),
                     sum(num(x["販売手数料"]) for x in ms), sum(num(x["利益"]) for x in ms), len(ms))
    year = tuple(sum(months[m][i] for m in months) for i in range(5))
    checks = (sum(1 for x in sold if not isinstance(x["売却日"], dt.date)),
              sum(1 for x in sold if x["売却額"] is None))
    grades = {g: sum(1 for x in rows if x["グレード"] == g) for g in ("PSA10", "PSA9", "PSA8以下", "未鑑定")}

    s = inp["sim"]
    qlow = 100 - s["q10"] - s["q9"]
    esale = (s["p10"] * s["q10"] + s["p9"] * s["q9"] + s["low"] * qlow) / 100
    efee = esale * fee_pct / 100
    import math
    raw_max = esale * (1 - fee_pct / 100 - s["target"] / 100) - cost
    maxbuy = max(0, math.trunc(round(raw_max, 6) / 100) * 100)
    breakeven = esale - efee - cost
    verdict = "目標内" if s["buy"] <= maxbuy else ("黒字見込み(目標未満)" if s["buy"] <= breakeven else "期待値は赤字")
    g = lambda p: p - rhu(p * fee_pct / 100) - cost - s["buy"]
    sim = {"cost": cost, "qlow": qlow, "esale": esale, "efee": efee, "eprofit": esale - efee - cost - s["buy"],
           "erate": (esale - efee - cost - s["buy"]) / esale if esale else None, "breakeven": breakeven,
           "maxbuy": maxbuy, "verdict": verdict, "g10": g(s["p10"]), "g9": g(s["p9"]), "glow": g(s["low"])}
    return {"cost": cost, "ledger": led, "orders": orders, "months": months, "year": year,
            "checks": checks, "grades": grades, "sim": sim}


# ============================================================================
# 1. 静的点検
# ============================================================================
def static_checks(wb) -> None:
    names = set(wb.defined_names.keys())
    sheets = set(wb.sheetnames)
    bad_func, bad_ref, bad_text, n_formula = [], [], [], 0
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not (isinstance(v, str) and v.startswith("=")):
                    continue
                n_formula += 1
                where = f"{ws.title}!{c.coordinate}"
                if any(m in v for m in ERROR_MARKERS) or "[" in v or "@" in v or "{" in v:
                    bad_text.append(where)
                for t in Tokenizer(v).items:
                    if t.type == "FUNC" and t.subtype == "OPEN":
                        if t.value.rstrip("(").upper() not in ALLOWED_FUNCS:
                            bad_func.append(f"{where}:{t.value}")
                    elif t.type == "OPERAND" and t.subtype == "RANGE":
                        ref = t.value
                        if "!" in ref:
                            if ref.split("!")[0].strip("'") not in sheets:
                                bad_ref.append(f"{where}:{ref}")
                        elif not ref.replace("$", "").replace(":", "").isalnum() or ref.startswith("cfg_") or "_" in ref:
                            if ref not in names:
                                bad_ref.append(f"{where}:{ref}")
    check("数式で使っている関数が許可リスト内 (XLOOKUP/LET/動的配列/構造化参照なし)", bad_func,
          f"数式 {n_formula:,} 個、関数は {sorted(ALLOWED_FUNCS)} のみ")
    check("数式の参照先シート・名前付き範囲が存在する", bad_ref)
    check("数式に #REF! などのエラー文字列・構造化参照・配列記法が無い", bad_text)

    bad = []
    for name in list(B.CFG_ROW) + ["cfg_cost_per_card"]:
        if name not in names:
            bad.append(f"{name} 未定義")
            continue
        dest = list(wb.defined_names[name].destinations)
        if len(dest) != 1 or dest[0][0] not in sheets or wb[dest[0][0]][dest[0][1].replace("$", "")].value is None:
            bad.append(f"{name} の参照先が空/不正: {dest}")
    check("名前付き範囲10個が定義され、値のあるセルを指している", bad)

    ws = wb[B.S_LEDGER]
    bad = []
    f_cols = [h for h, _, kind in B.LEDGER_COLS if kind == "f"]
    for h in f_cols:
        col = B.COL[h]
        base = ws[f"{col}{B.LEDGER_FIRST}"].value
        for r in range(B.LEDGER_FIRST, B.LEDGER_LAST + 1):
            want = Translator(base, origin=f"{col}{B.LEDGER_FIRST}").translate_formula(f"{col}{r}")
            if ws[f"{col}{r}"].value != want:
                bad.append(f"{col}{r}")
    check(f"在庫台帳の数式5列が {B.LEDGER_ROWS} 行ぶん(2〜{B.LEDGER_LAST}行)同じ形で入っている", bad)

    dvs = {str(dv.sqref): dv for dv in ws.data_validations.dataValidation}
    want_ranges = [f"B2:B{B.LEDGER_LAST}", f"J2:J{B.LEDGER_LAST}"]
    bad = [w for w in want_ranges if not any(w in k for k in dvs)]
    lists = sorted(dv.formula1 for dv in dvs.values() if dv.type == "list")
    if lists != sorted(['"在庫,鑑定中,返却済,売却済"', '"未鑑定,PSA10,PSA9,PSA8以下"']):
        bad.append(f"リスト内容: {lists}")
    check("プルダウン(状態・グレード)が500行ぶん入っている", bad)

    bad = []
    if ws.freeze_panes != "A2":
        bad.append(f"freeze_panes={ws.freeze_panes}")
    if ws.auto_filter.ref != f"A1:R{B.LEDGER_LAST}":
        bad.append(f"auto_filter={ws.auto_filter.ref}")
    if wb.sheetnames != [B.S_GUIDE, B.S_CFG, B.S_LEDGER, B.S_ORDER, B.S_MONTH, B.S_SIM]:
        bad.append(f"sheets={wb.sheetnames}")
    check("シート構成・先頭行固定・フィルタ", bad)


# ============================================================================
# 2. 手計算 ⇔ Python モデル ⇔ pokeca/core.py
# ============================================================================
def hand_checks(m: dict, inp: dict) -> None:
    bad = []
    if m["cost"] != HAND_COST:
        bad.append(f"1枚あたり費用 {m['cost']} != {HAND_COST}")
    for r, (k, total, fee, profit) in HAND_LEDGER.items():
        got = m["ledger"][r]
        if (got["鑑定費用"], got["原価合計"], got["販売手数料"], got["利益"]) != (k, total, fee, profit):
            bad.append(f"台帳{r}行 {got}")
    for mth in range(1, 13):
        if m["months"][mth] != HAND_MONTH.get(mth, (0, 0, 0, 0, 0)):
            bad.append(f"{mth}月 {m['months'][mth]}")
    if m["year"] != HAND_YEAR:
        bad.append(f"年間 {m['year']}")
    if m["orders"][5] != HAND_ORDER:
        bad.append(f"注文別 {m['orders'][5]}")
    if {g: m["grades"][g] for g in HAND_GRADES} != HAND_GRADES:
        bad.append(f"グレード {m['grades']}")
    for k, v in HAND_SIM.items():
        if not close(m["sim"][k], v):
            bad.append(f"sim {k}={m['sim'][k]} != {v}")
    check("手計算の期待値 = Python モデル(サンプル5行: 鑑定費用・原価合計・利益・月次合計・注文別・シミュレーター)", bad)

    try:
        sys.path.insert(0, str(HERE.parents[1]))
        from pokeca.core import per_card_costs
    except Exception as e:  # noqa: BLE001
        record("SKIP", "pokeca/core.py per_card_costs との突き合わせ", f"import できない: {e}")
        return
    c = inp["cfg"]
    core = per_card_costs({"usd_jpy": c["cfg_fx"], "costs": {
        "psa_fee_usd": c["cfg_psa_fee_usd"], "outbound_shipping_jpy": c["cfg_ship_out_jpy"],
        "return_shipping_usd": c["cfg_ship_back_usd"], "cards_per_shipment": c["cfg_cards_per_box"],
        "us_duty_per_shipment_usd": c["cfg_us_duty_usd"], "import_tax_rate": c["cfg_import_tax_pct"] / 100,
        "misc_per_card_jpy": c["cfg_misc_jpy"]}})
    parts = model_cost_parts(c)
    bad = [f"{k}: core={getattr(core, k)} model={v}" for k, v in parts.items() if not close(getattr(core, k), v)]
    if rhu(core.total) != HAND_COST:
        bad.append(f"core.total={core.total}")
    check("pokeca/core.py per_card_costs = Python モデル = 手計算 (内訳6項目と合計)", bad, f"core.total={core.total:.5f}")


# ============================================================================
# 3. LibreOffice で再計算して比べる
# ============================================================================
def recalc(src: Path, workdir: Path) -> Path | None:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return None
    out = workdir / "out"
    out.mkdir(exist_ok=True)
    cmd = [exe, f"-env:UserInstallation=file://{workdir / 'profile'}", "--headless",
           "--convert-to", "xlsx", "--outdir", str(out), str(src)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    res = out / src.name
    return res if res.exists() else None


def compare_recalc(label: str, calc_path: Path, m: dict, inp: dict) -> None:
    wb = load_workbook(calc_path, data_only=True)
    errs, n = [], 0
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                n += 1
                if isinstance(c.value, str) and (c.value.strip() in ERROR_VALUES or c.value.startswith("Err:")):
                    errs.append(f"{ws.title}!{c.coordinate}={c.value}")
    check(f"{label}: 再計算後、全シートにエラー値が無い", errs, f"{n:,} セルを走査")

    bad = []
    cfg = wb[B.S_CFG]
    for i, v in enumerate(model_cost_parts(inp["cfg"]).values()):
        if not close(cfg[f"B{B.COST_FIRST_ROW + i}"].value, v):
            bad.append(f"設定!B{B.COST_FIRST_ROW + i}={cfg[f'B{B.COST_FIRST_ROW + i}'].value} want {v}")
    if cfg[f"B{B.COST_TOTAL_ROW}"].value != m["cost"]:
        bad.append(f"合計={cfg[f'B{B.COST_TOTAL_ROW}'].value} want {m['cost']}")
    if cfg[f"B{B.CFG_CHECK_ROW}"].value != "OK":
        bad.append("設定チェックが OK でない")
    check(f"{label}: 設定シートの1枚あたり費用(内訳6項目+合計)", bad, f"合計 {m['cost']:,} 円")

    ws, bad, filled = wb[B.S_LEDGER], [], 0
    for r, want in m["ledger"].items():
        filled += want["鑑定費用"] is not None
        for h, v in want.items():
            got = ws[f"{B.COL[h]}{r}"].value
            if not close(got, v):
                bad.append(f"{B.COL[h]}{r}={got!r} want {v!r}")
    check(f"{label}: 在庫台帳の数式5列 × {len(m['ledger'])}行(未入力行は空白表示)", bad, f"入力のある行 {filled}")

    ws, bad = wb[B.S_ORDER], []
    keys = ["枚数", "仕入合計", "鑑定費用合計", "原価合計", "売却済枚数", "売却合計", "販売手数料", "利益", "未売却の原価", "PSA10枚数"]
    totals = dict.fromkeys(keys, 0)
    for r, want in m["orders"].items():
        for i, k in enumerate(keys):
            got = ws.cell(row=r, column=2 + i).value
            w = None if want is None else want[k]
            totals[k] += w or 0
            if not close(got, w):
                bad.append(f"{k}@{r}={got!r} want {w!r}")
    tr = 5 + B.ORDER_ROWS
    for i, k in enumerate(keys):
        if not close(ws.cell(row=tr, column=2 + i).value, totals[k]):
            bad.append(f"合計 {k}={ws.cell(row=tr, column=2 + i).value} want {totals[k]}")
    check(f"{label}: 注文別集計 30行 + 合計行", bad,
          f"入力のある注文 {sum(v is not None for v in m['orders'].values())}")

    ws, bad = wb[B.S_MONTH], []
    for mth, want in m["months"].items():
        r = B.MONTH_FIRST + mth - 1
        got = tuple(ws.cell(row=r, column=c).value for c in range(2, 7))
        if not all(close(a, b) for a, b in zip(got, want)):
            bad.append(f"{mth}月 {got} want {want}")
        rate = want[3] / want[0] if want[0] else None
        if not close(ws.cell(row=r, column=7).value, rate):
            bad.append(f"{mth}月 利益率 {ws.cell(row=r, column=7).value} want {rate}")
    tr = B.MONTH_FIRST + 12
    got = tuple(ws.cell(row=tr, column=c).value for c in range(2, 7))
    if not all(close(a, b) for a, b in zip(got, m["year"])):
        bad.append(f"年間 {got} want {m['year']}")
    got = (ws[f"B{tr + 3}"].value, ws[f"B{tr + 4}"].value)
    if got != m["checks"]:
        bad.append(f"チェック欄 {got} want {m['checks']}")
    g0 = tr + 9
    graded = sum(m["grades"][g] for g in ("PSA10", "PSA9", "PSA8以下"))
    for i, g in enumerate(("PSA10", "PSA9", "PSA8以下")):
        if ws[f"A{g0 + i}"].value != g or ws[f"B{g0 + i}"].value != m["grades"][g]:
            bad.append(f"{g} 枚数 {ws[f'B{g0 + i}'].value} want {m['grades'][g]}")
        if not close(ws[f"C{g0 + i}"].value, m["grades"][g] / graded if graded else None):
            bad.append(f"{g} 割合 {ws[f'C{g0 + i}'].value}")
    if ws[f"B{g0 + 3}"].value != graded or ws[f"B{g0 + 4}"].value != m["grades"]["未鑑定"]:
        bad.append("鑑定済み合計/未鑑定の枚数")
    check(f"{label}: 月次集計(12か月+年間合計+チェック欄+グレード別)", bad,
          f"年間 売上 {m['year'][0]:,} / 原価 {m['year'][1]:,} / 利益 {m['year'][3]:,} / {m['year'][4]}枚")

    ws = wb[B.S_SIM]
    bad = [f"{k}={ws[B.SIM[k]].value!r} want {v!r}" for k, v in m["sim"].items() if not close(ws[B.SIM[k]].value, v)]
    check(f"{label}: シミュレーター(期待利益・損益分岐・仕入れ上限・判定ほか)", bad,
          f"期待利益 {m['sim']['eprofit']:,.0f} / 分岐 {m['sim']['breakeven']:,.0f} / 上限 {m['sim']['maxbuy']:,}")


def make_stress(path: Path) -> None:
    """設定を全部変え、境界ケースの行を足したファイルを作る(数式はそのまま)。"""
    wb = load_workbook(XLSX)
    for name, v in {"cfg_fx": 148.5, "cfg_psa_fee_usd": 85, "cfg_ship_out_jpy": 9000, "cfg_ship_back_usd": 75.5,
                    "cfg_cards_per_box": 25, "cfg_us_duty_usd": 0, "cfg_import_tax_pct": 8, "cfg_misc_jpy": 200,
                    "cfg_sell_fee_pct": 10}.items():
        wb[B.S_CFG][f"B{B.CFG_ROW[name]}"].value = v
    ws = wb[B.S_LEDGER]
    D = dt.date
    extra = {
        7: dict(カード名="名前だけの行"),                                              # 状態もグレードも空 → 鑑定費用0
        8: dict(状態="売却済", カード名="12月31日", 仕入値=1000, PSA注文番号="ORD-2", グレード="PSA10",
                売却日=D(2026, 12, 31), 売却額=12345),                                  # 12月の境界 / 手数料 1234.5 → 1235
        9: dict(状態="売却済", カード名="翌年1月1日", 仕入値=1000, PSA注文番号="ORD-2", グレード="PSA9",
                売却日=D(2027, 1, 1), 売却額=30000),                                    # 翌年 → 月次に入らない
        10: dict(状態="売却済", カード名="前年12月31日", 仕入値=1000, PSA注文番号="ORD-2", グレード="PSA8以下",
                 売却日=D(2025, 12, 31), 売却額=30000),                                 # 前年 → 月次に入らない
        11: dict(状態="売却済", カード名="売却日なし", 仕入値=2000, PSA注文番号="ORD-2", グレード="PSA10", 売却額=20000),
        12: dict(状態="売却済", カード名="売却額なし", 仕入値=2000, PSA注文番号="ORD-2", グレード="PSA10",
                 売却日=D(2026, 1, 1)),
        13: dict(状態="在庫", カード名="在庫だがPSA10", 仕入値=7000, グレード="PSA10"),    # 鑑定費用が入る
        14: dict(状態="売却済", カード名="売却額0円", 仕入値=500, グレード="PSA9", 売却日=D(2026, 1, 31), 売却額=0),
        15: dict(状態="売却済", カード名="未鑑定のまま売却", 仕入値=3000, グレード="未鑑定",
                 売却日=D(2026, 2, 28), 売却額=3999),
        16: dict(管理番号="X-1"),                                                       # 管理番号だけ
        300: dict(状態="返却済", カード名="途中の行", 仕入値=1234, PSA注文番号="00123", グレード="PSA8以下"),
        B.LEDGER_LAST: dict(状態="売却済", カード名="最終行", 仕入値=9999, PSA注文番号="00123", グレード="PSA10",
                            売却日=D(2026, 12, 1), 売却額=55555),
    }
    for r, vals in extra.items():
        for h, v in vals.items():
            ws[f"{B.COL[h]}{r}"].value = v
    o = wb[B.S_ORDER]
    o["A6"].value, o["A8"].value, o["A34"].value = "ORD-2", "00123", "該当なし"
    s = wb[B.S_SIM]
    for k, v in {"buy": 12000, "p10": 33333, "p9": 9999, "low": 1500, "q10": 37.5, "q9": 45, "target": 15}.items():
        s[B.SIM[k]].value = v
    wb.save(path)


def main() -> int:
    if not XLSX.exists():
        print(f"{XLSX} がありません。先に build.py を実行してください。")
        return 2
    wb = load_workbook(XLSX)
    print("== 1. 静的点検 (openpyxl) ==")
    static_checks(wb)
    print("\n== 2. 手計算との突き合わせ ==")
    inp = read_inputs(wb)
    m = model(inp)
    hand_checks(m, inp)

    print("\n== 3. LibreOffice で再計算 ==")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        try:
            calc_path = recalc(XLSX, td)
        except Exception as e:  # noqa: BLE001
            calc_path = None
            record("SKIP", "LibreOffice での再計算", f"実行に失敗: {e}")
        if calc_path is None:
            if not any(s == "SKIP" and "LibreOffice" in n for s, n, _ in results):
                record("SKIP", "LibreOffice での再計算", "soffice が見つからない。数式の計算結果は未確認")
        else:
            compare_recalc("出荷状態", calc_path, m, inp)
            stress = td / "stress.xlsx"
            make_stress(stress)
            s_inp = read_inputs(load_workbook(stress))
            s_calc = recalc(stress, td)
            compare_recalc("負荷シナリオ", s_calc, model(s_inp), s_inp)

    record("SKIP", "Microsoft Excel での表示・再計算", "この環境に Excel が無いため未確認")
    record("SKIP", "Googleスプレッドシートへのインポートと再計算", "ネットワーク・アカウントを使わないため未確認")

    ng = [r for r in results if r[0] == "NG"]
    print(f"\n結果: OK {sum(r[0] == 'OK' for r in results)} / NG {len(ng)} / 未確認 {sum(r[0] == 'SKIP' for r in results)}")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())
