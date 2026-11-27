"""PSA10 買取価格の比較ページ（products/tools-site/kaitori.py と build.py の build_kaitori）のテスト。

店名は実在の取得対象の名前を使うが、カード・価格・URL はすべて架空。ネットワークには出ない。
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "products" / "tools-site"))
import kaitori as K  # noqa: E402

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=K.JST)
SITE = {"kaitori_price": {"publish": True, "shops": {"トレカクラブ": True, "トレカラウンジ": True, "シンソク": True, "トレカバンク": False}}}


def row(shop, number, name, price, grade="PSA10", **extra):
    return {"shop": shop, "number": number, "name": name, "grade": grade, "price": price, **extra}


def data(rows, at=NOW, failed=()):
    """collect と同じ形のデータを、架空の行から作る。"""
    fetchers = {m: (lambda m=m: [r for r in rows if K.SHOPS[r["shop"]]["module"] == m]) for m in K.MODULES}
    for m in failed:
        fetchers[m] = lambda: (_ for _ in ()).throw(RuntimeError("接続できません"))
    return K.collect(K.settings(SITE)["modules"], fetchers, at)


BASE_ROWS = [
    row("トレカクラブ", "001/100", "テストカゲex", 10000, item_id="001-100-X"),
    row("トレカラウンジ", "001/100", "テストカゲex SAR", 9500, item_id="abc", rarity="SAR"),
    row("シンソク", "００１／１００", "テストカゲｅｘ", 9000),
]


def cards(rows, site=SITE, now=NOW, **kw):
    return {c["key"]: c for c in K.select(data(rows, **kw), site, now)["cards"]}


def test_same_number_and_name_are_joined_across_shops():
    got = cards(BASE_ROWS)
    assert list(got) == ["001/100|テストカゲEX"]
    c = got["001/100|テストカゲEX"]
    assert [(o["shop"], o["price"], o["channel"]) for o in c["offers"]] == [
        ("トレカクラブ", 10000, "郵送"), ("トレカラウンジ", 9500, "郵送"), ("シンソク", 9000, "郵送")]
    assert (c["max"], c["min"], c["diff"], c["rarity"], c["number"], c["name"]) == (10000, 9000, 1000, "SAR", "001/100", "テストカゲex")
    assert c["slug"] == "001-100-テストカゲex"
    # 出典は、商品ページのURLを作れる店は商品ページ、作れない店は買取価格表のページ
    assert [o["source_url"] for o in c["offers"]] == [
        "https://torecaclub.com/pokemon/cards/psa10/001-100-X/", "https://kaitori.toreca-lounge.com/product/abc", "https://shinsoku-tcg.com/yuso-kaitori"]
    assert all(o["fetched_at"] == NOW.isoformat() for o in c["offers"])


@pytest.mark.parametrize("rows, why", [
    ([row("トレカクラブ", "002/100", "テストガメ", 5000)], "1店だけ"),
    ([row("トレカクラブ", "002/100", "テストガメ", 5000), row("トレカラウンジ", "002/101", "テストガメ", 5000)], "1店だけ"),       # 番号が違う
    ([row("トレカクラブ", "002/100", "テストガメ", 5000), row("トレカラウンジ", "002/100", "テストダネ", 5000)], "1店だけ"),       # 名前が違う
    ([row("トレカクラブ", "002/100", "テストガメ", 5000), row("トレカラウンジ", "002/100", "テストガメ(1ST)", 5200)], "名前の注記が不一致"),
    ([row("トレカクラブ", "002/100", "テストガメ", 5000), row("トレカクラブ", "002/100", "テストガメ(ミラー)", 7000),
      row("トレカラウンジ", "002/100", "テストガメ", 5000)], "同じ店に価格が複数"),
    ([row("トレカクラブ", "002/100", "テストガメ", 50000), row("トレカラウンジ", "002/100", "テストガメ", 20000)], "価格が離れすぎ"),
])
def test_doubtful_matches_are_not_listed(rows, why):
    r = K.select(data(BASE_ROWS + rows), SITE, NOW)
    assert [c["key"] for c in r["cards"]] == ["001/100|テストカゲEX"]
    assert r["dropped"][why] >= 1


def test_only_psa10_rows_with_a_card_number_are_used():
    rows = [row("トレカクラブ", "003/100", "テストダネ", 4000, grade="PSA9"), row("トレカラウンジ", "003/100", "テストダネ", 4000, grade=""),
            row("トレカクラブ", "", "番号なし", 4000), row("トレカラウンジ", "", "番号なし", 4000),
            row("トレカクラブ", "004/100", "テストダネ", 0), row("トレカラウンジ", "004/100", "テストダネ", 3000)]
    assert list(cards(BASE_ROWS + rows)) == ["001/100|テストカゲEX"]


def test_same_annotation_in_both_shops_is_kept_in_the_name():
    got = cards([row("トレカクラブ", "010/018", "テストチュウ(記念配布)", 30000), row("トレカラウンジ", "010/018", "テストチュウ （記念配布）", 31000)])
    assert [(c["name"], c["slug"]) for c in got.values()] == [("テストチュウ(記念配布)", "010-018-テストチュウ")]


def test_stale_label_and_too_old_data():
    d = data(BASE_ROWS)
    assert K.select(d, SITE, NOW + timedelta(hours=48))["stale"] is False
    assert K.select(d, SITE, NOW + timedelta(hours=48, minutes=1))["stale"] is True
    assert K.select(d, SITE, NOW + timedelta(days=K.MAX_AGE_DAYS, minutes=1)) is None   # 古すぎるデータではページを作らない
    assert K.select(None, SITE, NOW) is None
    assert K.select({**d, "fetched_at": None}, SITE, NOW) is None


def test_shop_switch_and_publish_switch():
    off = {"kaitori_price": {"publish": True, "shops": {"トレカクラブ": True, "トレカラウンジ": True, "シンソク": False}}}
    c = cards(BASE_ROWS, site=off)["001/100|テストカゲEX"]   # 取得済みのデータにあっても、切にした店は出さない
    assert [o["shop"] for o in c["offers"]] == ["トレカクラブ", "トレカラウンジ"]
    assert [s["shop"] for s in K.select(data(BASE_ROWS), off, NOW)["shops"]] == ["トレカクラブ", "トレカラウンジ"]
    one = {"kaitori_price": {"publish": True, "shops": {"トレカクラブ": True}}}   # 書いていない店は切。1店では比較にならない
    assert K.select(data(BASE_ROWS), one, NOW)["cards"] == []
    assert K.select(data(BASE_ROWS), {"kaitori_price": {"publish": False, "shops": SITE["kaitori_price"]["shops"]}}, NOW) is None
    assert K.select(data(BASE_ROWS), {}, NOW) is None
    assert K.settings({"kaitori_price": {"publish": "yes", "shops": {"シンソク": "true"}}}) == {"publish": False, "modules": []}   # true 以外は切


def test_failed_shop_is_shown_as_failed_and_others_are_used():
    d = data(BASE_ROWS, failed=["シンソク"])
    assert [(s["shop"], s["status"], s["count"]) for s in d["shops"]] == [("トレカクラブ", "ok", 1), ("トレカラウンジ", "ok", 1), ("シンソク", "failed", 0)]
    r = K.select(d, SITE, NOW)
    assert [(s["shop"], s["ok"]) for s in r["shops"]] == [("トレカクラブ", True), ("トレカラウンジ", True), ("シンソク", False)]
    assert [o["shop"] for o in r["cards"][0]["offers"]] == ["トレカクラブ", "トレカラウンジ"]
    empty = K.collect(["トレカクラブ"], {"トレカクラブ": lambda: []}, NOW)   # 0件も失敗として扱う
    assert empty["shops"][0]["status"] == "failed" and "0件" in empty["shops"][0]["error"]


def test_export_keeps_previous_data_when_fetch_fails(tmp_path):
    path = tmp_path / "prices.json"
    calls = []
    ok = {m: (lambda m=m: calls.append(m) or [r for r in BASE_ROWS if r["shop"] == m]) for m in ("トレカクラブ", "トレカラウンジ", "シンソク")}
    boom = {m: (lambda: (_ for _ in ()).throw(RuntimeError("落ちています"))) for m in ok}
    site = {"kaitori_price": {"publish": False, "shops": {"トレカクラブ": True, "トレカラウンジ": True, "シンソク": False}}}

    assert "更新しました" in K.export(site, path, ok, NOW)
    assert calls == ["トレカクラブ", "トレカラウンジ"]   # 切の店には取得に行かない
    first = json.loads(path.read_text(encoding="utf-8"))
    assert len(first["rows"]) == 2 and set(first["rows"][0]) == {"shop", "number", "name", "rarity", "grade", "price", "source_url", "fetched_at"}

    assert "取得しませんでした" in K.export(site, path, ok, NOW + timedelta(hours=3))   # 1日1回まで
    assert calls == ["トレカクラブ", "トレカラウンジ"]

    later = NOW + timedelta(hours=24)
    assert "前回のデータを残しました" in K.export(site, path, boom, later)   # 全店失敗
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert kept["rows"] == first["rows"] and kept["fetched_at"] == first["fetched_at"] and kept["last_attempt_at"] == later.isoformat()
    assert "取得しませんでした" in K.export(site, path, ok, later + timedelta(hours=1))   # 失敗した回も1回に数える

    half = {**ok, "トレカラウンジ": boom["トレカラウンジ"]}   # 1店しか取れないと比較にならないので、これも前回のまま
    assert "前回のデータを残しました" in K.export(site, path, half, later + timedelta(hours=24))
    assert json.loads(path.read_text(encoding="utf-8"))["rows"] == first["rows"]

    assert "掲載が「入」の店がありません" in K.export({"kaitori_price": {"shops": {}}}, tmp_path / "none.json", ok, NOW)
    assert not (tmp_path / "none.json").exists()
    assert "前回のデータを残しました" in K.export(site, tmp_path / "new.json", boom, NOW)   # 初回から全店失敗: 空のデータ（ページは作られない）
    assert K.select(K.load(tmp_path / "new.json"), SITE, NOW) is None


def test_load_returns_none_for_missing_or_broken_file(tmp_path):
    assert K.load(tmp_path / "nai.json") is None
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    assert K.load(tmp_path / "bad.json") is None


# ---- build.py（ページの生成）-------------------------------------------------------

@pytest.fixture
def build(tmp_path, monkeypatch):
    import build as B
    monkeypatch.setattr(B, "OUT", tmp_path / "public")
    monkeypatch.setattr(B, "PAGES", [])
    return B


def test_build_writes_nothing_without_data(build):
    assert build.build_kaitori(None) == []
    assert build.build_kaitori(K.select(data([BASE_ROWS[0]]), SITE, NOW)) == []   # 載せられるカードが0枚
    assert not build.OUT.exists()


def test_build_pages(build):
    rows = BASE_ROWS + [row("トレカクラブ", "005/100", "あいうえお", 3000), row("トレカラウンジ", "005/100", "あいうえお", 3300)]
    kp = K.select(data(rows, failed=["シンソク"]), SITE, NOW + timedelta(hours=49))
    paths = build.build_kaitori(kp)
    assert paths == ["kaitori-price/", "kaitori-price/aiueo/", "kaitori-price/001-100-%E3%83%86%E3%82%B9%E3%83%88%E3%82%AB%E3%82%B2ex/",
                     "kaitori-price/005-100-%E3%81%82%E3%81%84%E3%81%86%E3%81%88%E3%81%8A/"]
    assert [p[0] for p in build.PAGES] == paths
    assert len({p[1] for p in build.PAGES}) == len({p[2] for p in build.PAGES}) == 4   # title・description は重複しない
    read = lambda p: (build.OUT / p / "index.html").read_text(encoding="utf-8")
    card = read("kaitori-price/001-100-テストカゲex")
    assert "取得日時: <b>2026年11月27日 12:00</b>" in card and "各店の最新の表示と査定で決まります" in card
    assert 'data-stale-hours="48">取得から48時間以上たっています' in card   # 49時間たっているので、隠さずに出す
    assert "10,000円" in card and "9,500円" in card and "<td>500円</td>" in card and "<td>SAR</td>" in card and "<td>001/100</td>" in card
    assert 'href="https://torecaclub.com/pokemon/cards/psa10/001-100-X/"' in card and "郵送" in card
    assert "<td>シンソク<small>郵送</small></td><td>取得できませんでした</td>" in card and "9,000円" not in card
    assert "<img" not in card
    for word in ("必ず", "最高値", "おすすめ", "高価買取", "お得"):
        assert word not in card
    top = read("kaitori-price")
    assert top.index("テストカゲex") < top.index("あいうえお") and "<td>取得できませんでした</td>" in top   # 価格の高い順
    kana = read("kaitori-price/aiueo")
    assert kana.index(">あいうえお<") < kana.index(">テストカゲex<")
    fresh = build._kp_notice(K.select(data(rows), SITE, NOW + timedelta(hours=1)))
    assert 'data-stale-hours="48" hidden>' in fresh   # 新しいうちは隠しておく（開いたときに app.js が判定し直す）
