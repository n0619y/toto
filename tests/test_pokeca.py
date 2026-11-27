from pathlib import Path

import pytest
import yaml

from pokeca.core import best_offers, card_key, normalize_grade, per_card_costs, recommend, sell_plan
from pokeca.db import DB

ROOT = Path(__file__).resolve().parents[1]
# テストは設定ファイルの金額に依存させない（設定は実績に合わせて変わるため）
CFG = {
    "usd_jpy": 155,
    "costs": {"psa_fee_usd": 25, "cards_per_shipment": 20, "outbound_shipping_jpy": 8000,
              "return_shipping_usd": 60, "us_duty_per_shipment_usd": 30,
              "import_tax_rate": 0.10, "misc_per_card_jpy": 150},
    "target_margin": 0.25,
    "grade_probabilities": {"PSA10": 0.5, "PSA9": 0.4, "LOW": 0.1},
    "fallback": {"psa9_of_raw": 0.9, "low_of_raw": 0.5},
}


def test_shipped_config_is_valid():
    cfg = yaml.safe_load((ROOT / "config" / "pokeca.yaml").read_text(encoding="utf-8"))
    assert per_card_costs(cfg).total > 0
    assert sum(cfg["grade_probabilities"].values()) == pytest.approx(1.0)
A = "SV2A-201/165"


@pytest.fixture
def db():
    d = DB(":memory:")
    assert d.import_prices(ROOT / "pokeca" / "sample" / "prices.csv", "2026-11-27") == 8
    return d


def test_normalization():
    assert card_key("sv2a", "201/165") == card_key("SV2a", "２０１/１６５") == A
    assert normalize_grade("PSA 10") == normalize_grade("psa１０") == "PSA10"
    assert normalize_grade("") == normalize_grade("美品") == "RAW"


def test_costs_per_card():
    c = per_card_costs(CFG)
    c = per_card_costs(CFG)
    assert c.grading == 25 * 155
    assert c.ship_out == 8000 / 20
    assert c.ship_back == 60 * 155 / 20
    assert c.import_tax == pytest.approx((3875 + 465) * 0.10)
    assert c.us_duty == 30 * 155 / 20
    assert c.total == pytest.approx(3875 + 400 + 465 + 434 + 232.5 + 150)


def test_recommend_uses_best_shop_and_margin(db):
    best = best_offers(db.latest_prices())
    assert best[(A, "PSA10")]["shop"] == "ショップB"
    assert best[(A, "RAW")]["price"] == 22000
    r = recommend(A, best, CFG)
    expected = 0.5 * 55000 + 0.4 * 21000 + 0.1 * (22000 * 0.5)
    assert r["expected_sale"] == pytest.approx(expected)
    assert r["max_buy"] == ((expected - r["costs"]) / 1.25) // 100 * 100
    assert r["worth_grading"]


def test_recommend_fallbacks_and_skips(db):
    best = best_offers(db.latest_prices())
    r = recommend("SV4A-350/190", best, CFG)          # PSA9 の買取なし → 未鑑定×0.9
    assert r["psa9_value"] == pytest.approx(6500 * 0.9)
    assert not r["worth_grading"]                      # 費用負けするカード
    assert recommend("SV1-100/078", best, CFG) is None  # PSA10 買取が無い


def test_latest_prices_are_per_shop(db, tmp_path):
    newer = tmp_path / "p.csv"
    newer.write_text("shop,set_code,number,name,grade,price\nショップB,sv2a,201/165,甲,PSA10,40000\n", encoding="utf-8")
    db.import_prices(newer, "2026-11-28")
    best = best_offers(db.latest_prices())
    assert best[(A, "PSA10")]["shop"] == "ショップA"     # B は最新表で 40000 に下がった
    assert (A, "RAW") in best and best[(A, "RAW")]["shop"] == "ショップA"  # B の古い行は使わない


def test_stock_flow_and_sell_plan(db):
    i = db.add_stock("sv2a", "201/165", "甲", 15000, "2026-11-27", "ショップA")
    db.update_stock(i, status="鑑定中", extra_cost=5324)
    db.update_stock(i, status="返却済", grade="psa 10", cert="12345678")
    item = db.stock("返却済")[0]
    assert item["grade"] == "PSA10" and item["cost_basis"] == 20324
    plan = sell_plan([item], best_offers(db.latest_prices()))[0]
    assert plan["shop"] == "ショップB" and plan["profit"] == 55000 - 20324
    with pytest.raises(ValueError):
        db.update_stock(i, status="紛失")
    with pytest.raises(KeyError):
        db.update_stock(999, status="在庫")
