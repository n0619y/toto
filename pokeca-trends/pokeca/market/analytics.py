"""買取価格の時系列から相場分析を行う。

- カードごとに「最高買取価格（全ショップ中の最高値）」を代表値とする
- 前日比・7日比・30日比、急騰/急落ランキング、ショップ間の価格差、相場指数を算出
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date as Date, timedelta

from .normalize import norm_name

MIN_PRICE_FOR_MOVERS = 1000  # 低額カードの小さな値動きでランキングが埋まらないように


def _pct(now: int | None, before: int | None) -> float | None:
    if not now or not before:
        return None
    return round((now - before) / before * 100, 1)


def build(conn, today: str, history_days: int = 60) -> dict:
    start = (Date.fromisoformat(today) - timedelta(days=history_days)).isoformat()
    rows = conn.execute(
        "SELECT date, shop, card_key, card_name, card_number, rarity, price FROM buylist_prices "
        "WHERE date BETWEEN ? AND ? AND condition IN ('', '美品', '通常')", (start, today)).fetchall()
    if not rows:
        return {"date": today, "cards": [], "risers": [], "fallers": [], "index": [], "shops": []}

    by_card_date: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    meta: dict[str, dict] = {}
    for r in rows:
        by_card_date[r["card_key"]][r["date"]][r["shop"]] = r["price"]
        meta.setdefault(r["card_key"], {"name": r["card_name"], "number": r["card_number"], "rarity": r["rarity"]})
    dates = sorted({r["date"] for r in rows})
    latest = today if today in dates else dates[-1]

    def best_on_or_before(series: dict[str, dict[str, int]], target: str) -> int | None:
        ds = [d for d in series if d <= target]
        return max(series[max(ds)].values()) if ds else None

    def days_ago(n: int) -> str:
        return (Date.fromisoformat(latest) - timedelta(days=n)).isoformat()

    cards = []
    for key, series in by_card_date.items():
        if latest not in series:
            continue
        shops_today = series[latest]
        best = max(shops_today.values())
        cards.append({
            "key": key, **meta[key],
            "price": best,
            "median": int(statistics.median(shops_today.values())),
            "best_shop": max(shops_today, key=shops_today.get),
            "shop_prices": dict(sorted(shops_today.items(), key=lambda x: -x[1])),
            "spread_pct": _pct(best, min(shops_today.values())) if len(shops_today) > 1 else None,
            "chg_1d": _pct(best, best_on_or_before(series, days_ago(1))),
            "chg_7d": _pct(best, best_on_or_before(series, days_ago(7))),
            "chg_30d": _pct(best, best_on_or_before(series, days_ago(30))),
            "history": [[d, max(series[d].values())] for d in sorted(series)],
        })
    cards.sort(key=lambda c: -c["price"])

    movers = [c for c in cards if c["price"] >= MIN_PRICE_FOR_MOVERS and c["chg_7d"] is not None]
    risers = sorted([c for c in movers if c["chg_7d"] > 0], key=lambda c: -c["chg_7d"])[:20]
    fallers = sorted([c for c in movers if c["chg_7d"] < 0], key=lambda c: c["chg_7d"])[:20]

    # 相場指数: 期間の初日にも価格があるカードの「初日比」の平均 ×100
    base_date = dates[0]
    base = {k: max(s[base_date].values()) for k, s in by_card_date.items() if base_date in s}
    index = []
    for d in dates:
        ratios = [max(by_card_date[k][d].values()) / base[k] for k in base if d in by_card_date[k]]
        if ratios:
            index.append([d, round(statistics.mean(ratios) * 100, 1)])

    shop_names = sorted({r["shop"] for r in rows if r["date"] == latest})
    return {"date": latest, "cards": cards, "risers": risers, "fallers": fallers, "index": index,
            "shops": shop_names, "card_count": len(cards)}


def match_cards(topic_cards: list[str], market_cards: list[dict], limit: int = 6) -> list[dict]:
    """話題に出てきたカード名と相場データのカードを名前の部分一致で結び付ける。"""
    out, seen = [], set()
    for name in topic_cards:
        n = norm_name(name)
        if len(n) < 2:
            continue
        for c in market_cards:
            cn = norm_name(c["name"])
            if c["key"] not in seen and (n in cn or cn in n):
                seen.add(c["key"])
                out.append(c)
    return sorted(out, key=lambda c: -c["price"])[:limit]
