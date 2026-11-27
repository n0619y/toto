"""計算ロジック（外部サービスに依存しない純粋関数）。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def card_key(set_code: str, number: str) -> str:
    """店ごとの表記ゆれを吸収するカード識別キー。例: ("sv2a", "201/165") -> "SV2A-201/165" """
    norm = lambda s: re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s))).upper()
    return f"{norm(set_code)}-{norm(number)}"


def normalize_grade(text: str) -> str:
    """ "PSA 10" "psa10" "PSA１０" -> "PSA10" / 未鑑定は "RAW" """
    t = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or ""))).upper()
    m = re.fullmatch(r"PSA(\d{1,2})", t)
    return f"PSA{int(m.group(1))}" if m else "RAW"


def best_offers(prices: list[dict]) -> dict[tuple[str, str], dict]:
    """(カード, グレード) ごとの最高買取。prices は各店の最新行。"""
    best: dict[tuple[str, str], dict] = {}
    for p in prices:
        k = (p["card_key"], p["grade"])
        if k not in best or p["price"] > best[k]["price"]:
            best[k] = p
    return best


@dataclass
class Costs:
    """1枚あたりの費用（円）。"""

    grading: float
    ship_out: float
    ship_back: float
    import_tax: float
    us_duty: float
    misc: float

    @property
    def total(self) -> float:
        return self.grading + self.ship_out + self.ship_back + self.import_tax + self.us_duty + self.misc


def per_card_costs(cfg: dict) -> Costs:
    c, fx, n = cfg["costs"], float(cfg["usd_jpy"]), float(cfg["costs"]["cards_per_shipment"])
    grading = float(c["psa_fee_usd"]) * fx
    ship_back = float(c["return_shipping_usd"]) * fx / n
    return Costs(
        grading=grading,
        ship_out=float(c["outbound_shipping_jpy"]) / n,
        ship_back=ship_back,
        import_tax=(grading + ship_back) * float(c["import_tax_rate"]),
        us_duty=float(c.get("us_duty_per_shipment_usd", 0)) * fx / n,
        misc=float(c["misc_per_card_jpy"]),
    )


def recommend(card: str, best: dict, cfg: dict, probs: dict | None = None) -> dict | None:
    """未鑑定カード1種の推奨仕入れ上限を計算する。

    期待売値 = Σ 確率(グレード) × そのグレードの最高買取
    推奨上限 = (期待売値 − 費用) ÷ (1 + 目標利益率)
    PSA10 の買取が無いカードは鑑定に出す根拠が無いので None。
    """
    probs = probs or cfg["grade_probabilities"]
    p10 = best.get((card, "PSA10"))
    if not p10:
        return None
    price = lambda g: best.get((card, g), {}).get("price", 0.0)
    raw = price("RAW")
    # PSA9 以下は買取表に無いことが多い。無ければ未鑑定買取 × 係数で控えめに置く。
    v9 = price("PSA9") or raw * float(cfg["fallback"]["psa9_of_raw"])
    v_low = raw * float(cfg["fallback"]["low_of_raw"])
    expected = probs["PSA10"] * p10["price"] + probs["PSA9"] * v9 + probs["LOW"] * v_low
    costs = per_card_costs(cfg).total
    max_buy = (expected - costs) / (1 + float(cfg["target_margin"]))
    return {
        "card_key": card,
        "name": p10.get("name", ""),
        "psa10_price": p10["price"], "psa10_shop": p10["shop"],
        "psa9_value": v9, "raw_price": raw,
        "expected_sale": expected, "costs": costs,
        "max_buy": max(0.0, max_buy // 100 * 100),          # 100円単位に切り下げ
        "breakeven_buy": expected - costs,
        "profit_if_psa10": p10["price"] - costs,             # ここから仕入れ値を引く
        "worth_grading": max_buy > raw,                      # 未鑑定のまま売るより得か
    }


def sell_plan(items: list[dict], best: dict) -> list[dict]:
    """在庫1点ごとに最高値の買取店を選ぶ。"""
    out = []
    for it in items:
        offer = best.get((it["card_key"], it["grade"]))
        out.append({
            **it,
            "shop": offer["shop"] if offer else None,
            "price": offer["price"] if offer else None,
            "profit": (offer["price"] - it["cost_basis"]) if offer else None,
        })
    return out
