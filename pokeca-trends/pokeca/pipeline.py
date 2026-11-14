"""日次パイプライン: 収集 → 話題化・要約 → 反応分析 → ランキング → 相場分析。"""
from __future__ import annotations

from datetime import date as Date

from . import db, demo
from .analysis import llm, offline, ranking, sentiment, topics as topic_mod
from .analysis.schemas import MarketCommentary
from .collectors import collect_all
from .config import get_logger, shops
from .market import analytics, buylist

log = get_logger()


def collect(date: str, use_demo: bool = False, only: list[str] | None = None) -> int:
    posts = demo.posts_for_day(Date.fromisoformat(date)) if use_demo else collect_all(only)
    with db.connect() as conn:
        db.save_posts(conn, posts, date)
    log.info("収集: %d 件を保存（%s）", len(posts), date)
    return len(posts)


def analyze(date: str, force_offline: bool = False) -> list[dict]:
    use_ai = llm.available() and not force_offline
    if not use_ai:
        log.warning("ANTHROPIC_API_KEY 未設定（または --offline）のため簡易分析で実行します")
    with db.connect() as conn:
        posts = db.load_posts(conn, date)
        prev_date = db.previous_topic_date(conn, date)
        prev = db.load_topics(conn, prev_date) if prev_date else []
    if not posts:
        log.warning("%s の投稿がありません。先に collect を実行してください", date)
        return []
    by_id = {p.id: p for p in posts}

    raw = topic_mod.extract_topics(posts, prev) if use_ai else offline.extract_topics(posts, prev)
    # 先にスコアで並べて上位だけ感情分析する（APIコスト削減）
    ranked = ranking.rank(raw, by_id, prev)
    for t in ranked:
        members = [by_id[i] for i in t["post_ids"] if i in by_id]
        try:
            t["sentiment"] = sentiment.analyze(t, members) if use_ai else offline.analyze_sentiment(t, members)
        except Exception as exc:
            log.error("感情分析に失敗（%s）: %s", t["title"], exc)
            t["sentiment"] = sentiment.empty()
        members.sort(key=topic_mod.engagement, reverse=True)
        # サイトには投稿の抜粋とリンクのみ載せる（投稿者名は載せない）
        t["top_posts"] = [{"source": p.source, "region": p.region, "text": " ".join(p.text.split())[:160],
                           "url": p.url, "likes": p.likes, "comments": p.comments_count, "shares": p.shares,
                           "created_at": p.created_at} for p in members[:6]]
        t["ai"] = use_ai
    with db.connect() as conn:
        db.save_topics(conn, date, ranked)
    log.info("分析完了: %d 話題（%s）", len(ranked), date)
    return ranked


def market(date: str, use_demo: bool = False, force_offline: bool = False) -> dict:
    with db.connect() as conn:
        sources: dict[str, list[dict]] = {}
        if use_demo:
            from .market.normalize import normalize_row
            for shop, rows in demo.buylist_for_day(Date.fromisoformat(date)).items():
                sources[shop] = [n for n in map(normalize_row, rows) if n]
        else:
            for shop in shops():
                try:
                    sources[shop["name"]] = buylist.collect_shop(shop)
                except Exception as exc:
                    log.error("[買取表] %s の取得に失敗: %s", shop.get("name"), exc)
            sources.update(buylist.manual_csvs(date))
        for shop, rows in sources.items():
            n = db.save_prices(conn, date, shop, rows)
            log.info("[買取表] %s: %d 件", shop, n)
        report = analytics.build(conn, date)
        db.save_report(conn, date, "market", report)
        topics = db.load_topics(conn, date)

    report["commentary"] = commentary(report, topics, use_ai=llm.available() and not force_offline)
    with db.connect() as conn:
        db.save_report(conn, date, "market", report)
    return report


def commentary(report: dict, topics: list[dict], use_ai: bool) -> dict:
    if not report["cards"]:
        return {"headline": "買取データがまだありません", "commentary": "", "watch_cards": [], "ai": False}
    fmt = lambda c: f"{c['name']} {c['rarity']} {c['price']:,}円 (7日 {c['chg_7d']:+.1f}%)"
    if not use_ai:
        up = report["risers"][:3]
        return {"headline": f"急騰トップは {up[0]['name']}" if up else "大きな値動きなし",
                "commentary": "（簡易分析）7日間の上昇率上位: " + " / ".join(map(fmt, up)) if up else "",
                "watch_cards": [c["name"] for c in up], "ai": False}
    prompt = ("## 7日上昇率 上位\n" + "\n".join(map(fmt, report["risers"][:10])) +
              "\n\n## 7日下落率 上位\n" + "\n".join(map(fmt, report["fallers"][:10])) +
              "\n\n## 相場指数（期間初日=100）\n" + ", ".join(f"{d}:{v}" for d, v in report["index"][-14:]) +
              "\n\n## 今日のSNS話題 上位\n" + "\n".join(f"- {t['title']}: {t['summary']}" for t in topics[:10]))
    try:
        r = llm.parse(MarketCommentary, content=prompt, effort="medium", system=(
            "あなたはポケカ買取相場のアナリストです。カードショップの買取価格データとSNSの話題から、"
            "今日の相場動向を日本語で簡潔に解説します。データにない数字や断定的な将来予測・投資助言は書かず、"
            "「〜の可能性」など慎重な表現を使ってください。"))
        return {**r.model_dump(), "ai": True}
    except Exception as exc:
        log.error("相場コメント生成に失敗: %s", exc)
        return commentary(report, topics, use_ai=False)
