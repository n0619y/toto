"""PSA10 買取価格の比較ページ（/kaitori-price/）のデータ: 取得して JSON に書き出す処理と、ページに載せるカードの選別。

    python products/tools-site/kaitori.py          # 掲載が「入」の店から取得して kaitori-data/prices.json を更新する
    python products/tools-site/kaitori.py --force  # 前回の取得から20時間たっていなくても取得する

- 取得そのもの（アクセス間隔 1.5 秒、上限ページ数、ページの読み方）は pokeca/shops/ のコードを呼ぶだけで、ここには書かない。
- どの店を載せるかは site.json の kaitori_price.shops（店名 → true/false）で決める。書いていない店は載せない。
  false の店には取得もしない。
- ページの生成は build.py（build_kaitori）。ここは HTML を作らない。
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pokeca.core import RARITIES, card_key, normalize_grade  # noqa: E402

# 置き場所を data/ にしないのは、リポジトリの .gitignore が data/ を除外しているため
DATA = ROOT / "kaitori-data" / "prices.json"
JST = timezone(timedelta(hours=9))
GRADE = "PSA10"
STALE_HOURS = 48          # 取得からこれを過ぎたら「古い可能性があります」と表示する
MAX_AGE_DAYS = 14         # 取得からこれを過ぎたデータでは、ページを生成しない（古い価格を出し続けない）
MIN_INTERVAL_HOURS = 20   # 取得は1日1回まで。前回の取得（失敗も含む）からこれより短ければ取得しない
MIN_SHOPS = 2             # カードごとのページを作るのに必要な店の数
MAX_RATIO = 2.0           # 店どうしの価格がこの倍率を超えて離れていたら、別のカード（仕様違いなど）の疑いがあるので載せない

# 行の店名 → 表示に使う情報。module は pokeca.shops.SHOPS のキー（site.json の入・切もこの名前）。
# 規約の確認結果（2026-11-27）は README の「PSA10 買取価格の比較」にある。
SHOPS = {
    "トレカクラブ": {"module": "トレカクラブ", "channel": "郵送", "list_url": "https://torecaclub.com/pokemon/psa10/",
                 "item_url": "https://torecaclub.com/pokemon/cards/psa10/{item_id}/",
                 "note": "ランク会員の上乗せ前の表示価格"},
    "トレカラウンジ": {"module": "トレカラウンジ", "channel": "郵送", "list_url": "https://kaitori.toreca-lounge.com/products/pokemon/single?grade=PSA10",
                  "item_url": "https://kaitori.toreca-lounge.com/product/{item_id}",
                  "note": "店の案内では「表示価格はあくまで参考価格」", "fetch_args": {"grades": ["PSA10"]}},
    "シンソク": {"module": "シンソク", "channel": "郵送", "list_url": "https://shinsoku-tcg.com/yuso-kaitori", "note": "状態Sの郵送買取価格"},
    "トレカバンク店頭": {"module": "トレカバンク", "channel": "店頭", "list_url": "https://store.torecabank.com/kaitori_list", "note": ""},
    "トレカバンク郵送": {"module": "トレカバンク", "channel": "郵送", "list_url": "https://store.torecabank.com/mail_buy_list", "note": ""},
}
MODULES = list(dict.fromkeys(s["module"] for s in SHOPS.values()))


def now_jst() -> datetime:
    return datetime.now(JST).replace(microsecond=0)


def parse_time(text) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=JST)


def settings(site: dict) -> dict:
    """site.json の kaitori_price。publish が true のときだけページを生成する。shops に true と書いた店だけ載せる。"""
    cfg = site.get("kaitori_price") or {}
    shops = cfg.get("shops") or {}
    return {"publish": cfg.get("publish") is True, "modules": [m for m in MODULES if shops.get(m) is True]}


def load(path: Path = DATA) -> dict | None:
    """書き出した JSON を読む。無い・壊れているときは None（ページを生成しない）。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("rows"), list) else None


# ---- 取得（書き出し）-------------------------------------------------------------

def _fetcher(module: str):
    from pokeca.shops import SHOPS as FETCHERS   # requests が要るので、取得するときだけ読み込む

    args = next((s.get("fetch_args") or {} for s in SHOPS.values() if s["module"] == module), {})
    return lambda: FETCHERS[module].fetch(**args)


def collect(modules: list[str], fetchers: dict | None = None, now: datetime | None = None) -> dict:
    """modules の店から PSA10 の買取行を集める。fetchers は {店名: 行を返す関数}（テスト用。省略時は pokeca.shops）。

    失敗・0件の店は status を "failed" にして、ほかの店だけで続ける。
    """
    rows, shops = [], []
    for module in modules:
        fetch = (fetchers or {}).get(module) or _fetcher(module)
        at = (now or now_jst()).isoformat()
        try:
            got = []
            for r in fetch():
                info = SHOPS.get(r.get("shop"))
                if not info or info["module"] != module or normalize_grade(r.get("grade", "")) != GRADE:
                    continue
                price = int(float(r.get("price") or 0))
                if price <= 0 or not str(r.get("number") or "").strip() or not str(r.get("name") or "").strip():
                    continue
                item = str(r.get("item_id") or "")
                got.append({"shop": r["shop"], "number": str(r["number"]).strip(), "name": str(r["name"]).strip(),
                            "rarity": str(r.get("rarity") or "").strip(), "grade": GRADE, "price": price,
                            "source_url": info["item_url"].format(item_id=item) if item and info.get("item_url") else info["list_url"],
                            "fetched_at": at})
            if not got:
                raise RuntimeError("0件でした（ページ構造が変わった可能性）")
            rows += got
            shops.append({"shop": module, "status": "ok", "count": len(got), "error": "", "fetched_at": at})
        except Exception as exc:   # 1店の失敗で全体を止めない
            shops.append({"shop": module, "status": "failed", "count": 0, "error": f"{type(exc).__name__}: {exc}"[:200], "fetched_at": at})
    return {"version": 1, "grade": GRADE, "fetched_at": (now or now_jst()).isoformat(), "shops": shops, "rows": rows}


def export(site: dict, path: Path = DATA, fetchers: dict | None = None, now: datetime | None = None, force: bool = False) -> str:
    """取得して path に書き出す。何をしたかを1行で返す。

    - 前回の取得（失敗も含む）から MIN_INTERVAL_HOURS たっていなければ、取得しない（force で無視）。
    - 取得できた店が MIN_SHOPS 未満（全店失敗を含む）なら、前回のデータを残す。比較にならないページで上書きしない。
    """
    now = now or now_jst()
    modules = settings(site)["modules"]
    if not modules:
        return "掲載が「入」の店がありません（site.json の kaitori_price.shops）。取得しませんでした。"
    old = load(path)
    last = parse_time((old or {}).get("last_attempt_at") or (old or {}).get("fetched_at"))
    if last and not force and now - last < timedelta(hours=MIN_INTERVAL_HOURS):
        return f"前回の取得（{last.isoformat()}）から {MIN_INTERVAL_HOURS} 時間たっていないので、取得しませんでした（1日1回まで）。"
    new = collect(modules, fetchers, now)
    summary = "、".join(f'{s["shop"]} {s["count"]}件' if s["status"] == "ok" else f'{s["shop"]} 失敗（{s["error"]}）' for s in new["shops"])
    ok = len({r["shop"] for r in new["rows"]})
    if ok < MIN_SHOPS:
        keep = old or {"version": 1, "grade": GRADE, "fetched_at": None, "shops": [], "rows": []}
        keep["last_attempt_at"] = now.isoformat()
        keep["last_attempt"] = new["shops"]
        _write(path, keep)
        return f"取得できた店が {ok} 店（{MIN_SHOPS} 店未満）なので、前回のデータを残しました: {summary}"
    new["last_attempt_at"] = now.isoformat()
    _write(path, new)
    return f"更新しました: {summary}"


def _write(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    tmp.replace(path)


# ---- 選別（ページに載せるカードを決める）-------------------------------------------

_SLUG_OK = re.compile(r"[^0-9a-zぁ-ゖァ-ヺー一-鿿]+")


_BRACKETS = "()[]【】「」『』"


def strict_name(number: str, name: str) -> str:
    """照合の最終確認に使うカード名。card_key と違い、括弧書きの中身（仕様・版・配布元の注記）を残す。

    例: 「ピカチュウEX(1ST)」と「ピカチュウEX」は card_key では同じになるが、ここでは別になる。
    """
    norm = lambda t: unicodedata.normalize("NFKC", str(t or "")).upper()
    n = norm(name).replace(re.sub(r"\s+", "", norm(number)), "")
    n = re.sub(rf"(?<![A-Z0-9]){RARITIES}(?![A-Z0-9])", "", n)
    return re.sub(r"PSA\s*\d{1,2}|[\s・/\-" + re.escape(_BRACKETS) + "]+", "", n)


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[\s" + re.escape(_BRACKETS) + "]+", unicodedata.normalize("NFKC", name)) if t]


def display_name(number: str, name: str) -> str:
    """表示用のカード名: 番号と、前後に単独で付いているレアリティ表記を外す（括弧書きの注記は残す）。"""
    n = unicodedata.normalize("NFKC", name)
    num = re.sub(r"\s+", "", unicodedata.normalize("NFKC", number))
    n = re.sub(r"\(\s*" + re.escape(num) + r"\s*\)", "", n, flags=re.I)
    n = re.sub(re.escape(num), " ", n, flags=re.I)
    n = re.sub(rf"^\s*{RARITIES}\s+|\s+{RARITIES}\s*(?=$|\()", " ", n)
    n = re.sub(r"\s*\(\s*", "(", re.sub(r"\s*\)", ")", n))
    return re.sub(r"\s+", " ", n).strip() or name.strip()


def rarity_of(rows: list[dict]) -> str:
    """店がレアリティを出していればそれを、無ければカード名に単独で付いている表記（2文字以上）を使う。分からなければ空。"""
    for r in rows:
        if r.get("rarity"):
            return unicodedata.normalize("NFKC", r["rarity"]).upper()
    for r in rows:
        for t in _tokens(r["name"]):
            if len(t) >= 2 and re.fullmatch(RARITIES, t.upper()):
                return t.upper()
    return ""


def slug_of(key: str) -> str:
    """照合キー（番号|名前）からパス用のスラッグを作る。例: "096/071|ナンジャモ" -> "096-071-ナンジャモ"。"""
    return _SLUG_OK.sub("-", key.lower()).strip("-")


def kana_key(name: str) -> str:
    """五十音順の並べ替え用。ひらがなをカタカナにそろえる（漢字は読みではなく文字コード順になる）。"""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in unicodedata.normalize("NFKC", name))


def select(data: dict | None, site: dict, now: datetime | None = None) -> dict | None:
    """ページに載せる内容を決める。生成しないときは None。

    載せるカードの条件（保守的に。満たさないものは黙って落とす）:
    1. 掲載が「入」で、今回の取得に成功した店の PSA10 の行だけを使う。
    2. 番号（NFKC・大文字・空白なし）とカード名（レアリティ表記・括弧書きを除く）が一致する行だけを同じカードとみなす
       （pokeca.core.card_key が同じ）。番号だけ・名前だけの一致では結び付けない。
    3. 1つの店の中で同じキーに違う価格が2つ以上あるカードは、どの仕様の価格か決まらないので載せない。
    4. MIN_SHOPS 店以上に価格があるカードだけ。
    5. 括弧書きの注記（1ST、ミラー仕様、言語、配布元など）まで含めた名前が店どうしで違うカードは載せない（strict_name）。
    6. 最も高い店の価格が最も低い店の MAX_RATIO 倍を超えるカードは、別のカードを結び付けた疑いがあるので載せない。
    """
    now = now or now_jst()
    cfg = settings(site)
    fetched = parse_time((data or {}).get("fetched_at"))
    if not cfg["publish"] or not data or not fetched or now - fetched > timedelta(days=MAX_AGE_DAYS):
        return None
    status = {s.get("shop"): s for s in data.get("shops") or []}
    shops = [{"shop": m, "ok": status.get(m, {}).get("status") == "ok", "count": status.get(m, {}).get("count", 0),
              "fetched_at": status.get(m, {}).get("fetched_at") or data["fetched_at"],
              "sources": [(name, info) for name, info in SHOPS.items() if info["module"] == m]} for m in cfg["modules"]]
    ok_modules = {s["shop"] for s in shops if s["ok"]}

    by_key: dict[str, dict[str, list[dict]]] = {}
    for r in data["rows"]:
        info = SHOPS.get(r.get("shop"))
        if not info or info["module"] not in ok_modules or r.get("grade") != GRADE or not isinstance(r.get("price"), int) or r["price"] <= 0:
            continue
        key = card_key(r.get("number", ""), r.get("name", ""))
        num, _, nm = key.partition("|")
        if "/" not in num or not nm:
            continue
        by_key.setdefault(key, {}).setdefault(r["shop"], []).append(r)

    cards, slugs, dropped = [], set(), {"1店だけ": 0, "同じ店に価格が複数": 0, "名前の注記が不一致": 0, "価格が離れすぎ": 0, "スラッグの重複": 0}
    for key in sorted(by_key):
        per_shop = by_key[key]
        if any(len({r["price"] for r in rs}) > 1 for rs in per_shop.values()):
            dropped["同じ店に価格が複数"] += 1
            continue
        if len(per_shop) < MIN_SHOPS:
            dropped["1店だけ"] += 1
            continue
        offers = sorted((rs[0] for rs in per_shop.values()), key=lambda r: (-r["price"], r["shop"]))
        if len({strict_name(r["number"], r["name"]) for r in offers}) > 1:
            dropped["名前の注記が不一致"] += 1
            continue
        hi, lo = offers[0]["price"], offers[-1]["price"]
        if hi > lo * MAX_RATIO:
            dropped["価格が離れすぎ"] += 1
            continue
        slug = slug_of(key)
        if not slug or slug in slugs:
            dropped["スラッグの重複"] += 1
            continue
        slugs.add(slug)
        number = unicodedata.normalize("NFKC", offers[0]["number"]).upper()
        name = min((display_name(r["number"], r["name"]) for r in offers), key=lambda n: (len(n), n))
        cards.append({"key": key, "slug": slug, "number": number, "name": name, "rarity": rarity_of(offers),
                      "offers": [{**r, "channel": SHOPS[r["shop"]]["channel"], "note": SHOPS[r["shop"]]["note"]} for r in offers],
                      "max": hi, "min": lo, "diff": hi - lo})
    return {"fetched_at": fetched, "stale": now - fetched > timedelta(hours=STALE_HOURS), "shops": shops, "cards": cards, "dropped": dropped}


if __name__ == "__main__":
    print(export(json.loads((ROOT / "site.json").read_text(encoding="utf-8")), force="--force" in sys.argv[1:]))
