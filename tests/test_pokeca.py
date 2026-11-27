import json
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
A = "201/165|サンプルカード甲"


@pytest.fixture
def db():
    d = DB(":memory:")
    assert d.import_prices(ROOT / "pokeca" / "sample" / "prices.csv", "2026-11-27") == 8
    return d


def test_normalization():
    assert card_key("201/165", "サンプルカード甲 SAR") == card_key("２０１/１６５", "サンプルカード甲") == A
    assert card_key("096/071", "ナンジャモ SAR（SV2D）") == card_key("096/071", "ナンジャモ SAR 096/071") == "096/071|ナンジャモ"
    assert card_key("096/071", "ナンジャモ") != card_key("096/071", "別のカード")   # 番号が同じ別弾は区別する
    assert card_key("003/SV-P", "ミュウex(SAR仕様/中国語版)") != card_key("003/SV-P", "ミュウex(SAR仕様)")
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
    r = recommend("350/190|サンプルカード乙", best, CFG)          # PSA9 の買取なし → 未鑑定×0.9
    assert r["psa9_value"] == pytest.approx(6500 * 0.9)
    assert not r["worth_grading"]                      # 費用負けするカード
    assert recommend("100/078|サンプルカード丙", best, CFG) is None  # PSA10 買取が無い


def test_latest_prices_are_per_shop(db, tmp_path):
    newer = tmp_path / "p.csv"
    newer.write_text("shop,number,name,grade,price\nショップB,201/165,サンプルカード甲,PSA10,40000\n", encoding="utf-8")
    db.import_prices(newer, "2026-11-28")
    best = best_offers(db.latest_prices())
    assert best[(A, "PSA10")]["shop"] == "ショップA"     # B は最新表で 40000 に下がった
    assert (A, "RAW") in best and best[(A, "RAW")]["shop"] == "ショップA"  # B の古い行は使わない


def test_stock_flow_and_sell_plan(db):
    i = db.add_stock("201/165", "サンプルカード甲 SAR", 15000, "2026-11-27", "ショップA")
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


def test_shinsoku_parser():
    from pokeca.shops import shinsoku
    rec = lambda **k: json.dumps({"id": k["item_id"], **k, "buy_boost": False}, ensure_ascii=False, separators=(",", ":"))
    psa = [{"id": 1, "slug": "psa10", "label": "PSA10", "category_label": "鑑定品"}]
    page = "x".join([
        rec(item_id="IA1", name="ナンジャモ", type="NORMAL", rarity="SAR", tags=[], is_postal_buy_target=True,
            postal_purchase_price_s=31000, modelno="096/071"),
        rec(item_id="IA2", name="メガリザードンXex", type="PSA", rarity="MA", tags=psa, is_postal_buy_target=True,
            postal_purchase_price_s=8900, modelno="223/193"),
        rec(item_id="IA3", name="拡張パック", type="BOX", rarity="", tags=[], is_postal_buy_target=True,
            postal_purchase_price_s=9800, modelno="$undefined"),
        rec(item_id="IA4", name="PSA10保証AR以上", type="PSA", rarity="", tags=psa, is_postal_buy_target=True,
            postal_purchase_price_s=3600, modelno="対象レアリティ AR SR"),
        rec(item_id="IA5", name="対象外", type="NORMAL", rarity="", tags=[], is_postal_buy_target=False,
            postal_purchase_price_s=100, modelno="001/001"),
    ]).replace('"', '\\"') + " 2,832 件"
    rows = shinsoku.parse(page)
    assert [(r["number"], r["name"], r["grade"], r["price"]) for r in rows] == [
        ("096/071", "ナンジャモ SAR", "", 31000), ("223/193", "メガリザードンXex", "PSA10", 8900)]
    assert shinsoku.total_pages(page) == 71


def test_toreca_lounge_parser():
    from pokeca.shops import toreca_lounge
    row = lambda span: ('<div class="flex items-end justify-between"><span class="shrink-0">%s:</span>'
                        '<span class="min-w-0 text-right">%s</span></div>') % span
    card = lambda pid, name, number, kind, price, series="": (
        f'<a href="/product/{pid}"><div class="rounded-xl"><div><img alt="{name}" loading="lazy" src="/_next/image?url=x"/></div>'
        f'<div class="shrink-0 text-base font-semibold">{name}</div><div class="flex flex-col">'
        + row(("型番", number)) + row(("レアリティ/種別", kind)) + (row(("収録弾", series)) if series else "")
        + f'</div><div><span class="text-sm font-medium">買取価格:</span><span class="text-base">{price}</span></div></div></a>')
    page = "<div>全<!-- -->212<!-- -->件</div>" + "".join([
        card("P1", "おくるだけ買取※ポケカのみ", "-", "-<!-- --> /<!-- --> <!-- -->PSA10,9,8", "¥1"),
        card("P2", "ハナコ", "401/SM-P", "-<!-- --> /<!-- --> <!-- -->PSA10", "¥123,000",
             "プロモーションカード<!-- -->(<!-- -->PROMO<!-- -->)"),
        card("P3", "ヒトカゲex", "132/106", "SAR<!-- --> /<!-- --> <!-- -->素体, PSA10", "～¥7,900"),
        card("P4", "ヒトカゲex", "132/106", "SAR<!-- --> /<!-- --> <!-- -->素体", "¥5,000"),
        card("P5", "ゼニガメ", "007/165", "C<!-- --> /<!-- --> <!-- -->PSA9", "¥2,300", "テスト弾<!-- -->(<!-- -->SV0<!-- -->)"),
    ])
    rows = toreca_lounge.parse(page)
    assert [(r["number"], r["name"], r["grade"], r["price"]) for r in rows] == [
        ("401/SM-P", "ハナコ", "PSA10", 123000), ("132/106", "ヒトカゲex", "", 5000), ("007/165", "ゼニガメ", "PSA9", 2300)]
    assert toreca_lounge.total_pages(page) == 3


def test_torecaclub_parser():
    from pokeca.shops import torecaclub
    item = lambda slug, alt, name, code, price: (
        f'<li><a class="flex items-center gap-3 p-3" href="/pokemon/cards/psa10/{slug}/"><img src="https://example.com/c.png" '
        f'alt="{alt}" class="h-16 w-12"/><span class="min-w-0 flex-1"><span class="block truncate font-medium">{name}</span>'
        f'<span class="text-xs text-gray-500">{code}<!-- -->・PSA10</span></span><span class="block text-right " '
        f'data-testid="rank-price-display"><strong class="block font-bold">{price}</strong><small class="flex">'
        'ランク会員最大<!-- -->2%UP</small></span></a></li>')
    page = "<ul>" + "".join([
        item("401-SM-P", "ハナコ 401/SM-P PSA10", "ハナコ", "401/SM", "¥1,230,000"),
        item("077-070-SV0-B", "タケシの勇気 077/070 PSA10", "タケシの勇気", "077/070", "¥45,000"),
        item("009-SV-P-CH", "ゼニガメex(中国語版） 009/SV PSA10", "ゼニガメex(中国語版）", "009/SV", "¥65,000"),
        item("XY-P", "ヒトカゲ 記念 XY/P PSA10", "ヒトカゲ 記念", "XY/P", "¥32,000"),
    ]) + ('</ul><nav aria-label="ページネーション" class="mt-6"><span>1<!-- --> / <!-- -->6</span>'
          '<a href="/pokemon/psa10/?page=2">次のページ</a></nav>')
    rows = torecaclub.parse(page)
    assert [(r["number"], r["name"], r["grade"], r["price"]) for r in rows] == [
        ("401/SM-P", "ハナコ", "PSA10", 1230000), ("077/070", "タケシの勇気", "PSA10", 45000),
        ("009/SV-P", "ゼニガメex(中国語版）", "PSA10", 65000)]
    assert torecaclub.total_pages(page) == 6


def test_torecabank_parsers():
    from pokeca.shops import torecabank
    rec = lambda name, key1, key2, kind, cat, price: {
        "product_master_name": name, "product_master_key1": key1, "product_master_key2": key2,
        "product_type_name": kind, "product_type_id": "1", "category_id": cat, "image_path": "uploads/x.jpg",
        "buy_price": price, "remaining_quantity": "3", "tag_ids": [4], "image_url": "https://example.com/x.jpg"}
    store = ("<script>\n    const showBuyList = true;\n    if (showBuyList) {\n        const perPage = 60;\n"
             "        const allProducts = " + json.dumps([
                 rec("(PSA10)ハナコ(テスト大会)", "PROMO", "401/SM-P", "PSA10", "1", "1060000"),
                 rec("(PSA10)タケシの勇気[SV0]", "SR", "077/070", "PSA10", "1", "45000"),
                 rec("(PSA10)ヒトカゲ LV.10(テストCD)", "★", "No.004", "PSA10", "1", "70000"),
                 rec("テスト拡張パック【未開封BOX】", "", "", "未開封BOX（シュリンク付き）", "1", "42000"),
                 rec("(PSA10)テスト船長(パラレル)", "SR", "OP99-001", "PSA10", "2", "26000"),
             ], ensure_ascii=False).replace("/", "\\/") + ";\n        let filtered = [];\n    }\n</script>")
    assert [(r["shop"], r["number"], r["name"], r["grade"], r["price"]) for r in torecabank.parse_store(store)] == [
        ("トレカバンク店頭", "401/SM-P", "ハナコ(テスト大会)", "PSA10", 1060000),
        ("トレカバンク店頭", "077/070", "タケシの勇気[SV0] SR", "PSA10", 45000)]

    item = lambda pid, name, tag, price: (
        f'<li class="item " data-id="{pid}" data-max="3" data-is-custom-item="0">\n<p class="card"><img src="https://example.com/x.jpg" '
        f'alt="{name}"></p>\n<p class="name">{name}</p>\n<p class="tag">{tag}</p>\n<p class="price">{price}<span>円</span></p>\n'
        '<p class="stock">残り3点</p>\n<a class="add-btn btn btn--red" href="https://store.torecabank.com/line">追加</a>\n</li>')
    items = [item(2, "ハナコ(テスト大会) PROMO 401/SM-P", "PSA10", "1,054,000"),
             item(7, "タケシの勇気[SV0] SR 077/070", "PSA10", "44,000"),
             item(8, "ヒトカゲ LV.10(テストCD) ★ No.004", "PSA10", "70,000"),
             item(9, "テスト拡張パック(SV0)【未開封BOX】", "未開封BOX（シュリンク付き）", "42,000"),
             item(10, "テスト船長(パラレル) SR★ OP99-001", "PSA10", "26,000")]
    mail = ('<ul class="tab__body list list--card">' + "".join(items) + '</ul><ul class="tab__body list list--list">' + "".join(items)
            + '</ul><a href="https://store.torecabank.com/mail_buy_list?category=1&amp;page=1">1</a>'
              '<a href="https://store.torecabank.com/mail_buy_list?category=1&amp;page=2">2</a>')
    assert [(r["shop"], r["number"], r["name"], r["grade"], r["price"]) for r in torecabank.parse_mail(mail)] == [
        ("トレカバンク郵送", "401/SM-P", "ハナコ(テスト大会)", "PSA10", 1054000),
        ("トレカバンク郵送", "077/070", "タケシの勇気[SV0] SR", "PSA10", 44000)]
    assert torecabank.total_pages(mail) == 2


# 実際の投稿文の形（2024〜2026年の公開投稿から、形式確認用に抜粋）
POST_NUMBERED = """📢＃スニダンポケカ買取情報📢
ただいまポケカサポートPSA10の買取大募集‼
🔥🔥🔥🔥🔥
✅メイ（067/049）￥81,000
✅リーリエの全力（068/049）￥82,000
✅ブルーの探索 （196/173）￥140,000
https://t.co/xxxx"""
POST_NICKNAMES = """📢#スニダン #ポケカ #PSA10 買取情報📢
✅エクバリーリエ✨ ￥5,900,000
✅アセロラ👻 ￥880,000
本日は11時から買取開始"""
POST_ONEPIECE = """#ワンピ #PSA10 金＆銀ニカの買取金額🆙
金背景 ニカルフィ ￥2⃣6⃣5⃣,0⃣0⃣0⃣"""


def test_x_post_parsing():
    from pokeca.shops.xposts import parse_post, resolve
    rows = parse_post(POST_NUMBERED, "スニダン")
    assert [(r["name"], r["number"], r["grade"], r["price"]) for r in rows] == [
        ("メイ", "067/049", "PSA10", 81000), ("リーリエの全力", "068/049", "PSA10", 82000),
        ("ブルーの探索", "196/173", "PSA10", 140000)]
    nick = parse_post(POST_NICKNAMES, "スニダン")
    assert [(r["name"], r["price"]) for r in nick] == [("エクバリーリエ", 5900000), ("アセロラ", 880000)]
    assert parse_post(POST_ONEPIECE, "スニダン") == []          # ポケカ以外は読まない

    aliases = {"エクバリーリエ": {"number": "397/SM-P", "name": "リーリエ"}}
    ok, unresolved = resolve(nick, aliases, {"アセロラ": {"056/049", "063/SM-P"}})
    assert [(r["name"], r["number"]) for r in ok] == [("リーリエ", "397/SM-P")]
    assert unresolved[0]["name"] == "アセロラ" and unresolved[0]["candidates"] == ["056/049", "063/SM-P"]
    ok2, _ = resolve(nick[1:], {}, {"アセロラ": {"056/049"}})
    assert ok2[0]["number"] == "056/049"                         # 候補が1つなら確定
