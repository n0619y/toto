"""静的サイト生成。DBの内容から HTML 一式を出力する（GitHub Pages などでそのまま公開可能）。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import db
from ..config import ROOT, get_logger, settings
from ..market.analytics import match_cards

log = get_logger()
HERE = Path(__file__).parent
SOURCE_LABEL = {"x": "X", "threads": "Threads", "instagram": "Instagram", "reddit": "Reddit"}
REGION_LABEL = {"ja": "国内", "global": "海外", "both": "国内＋海外"}
JST = timezone(timedelta(hours=9))


def _pct(v):
    if v is None:
        return '<span class="sub">-</span>'
    cls, arrow = ("up", "▲") if v > 0 else ("down", "▼") if v < 0 else ("", "")
    return f'<span class="{cls}">{arrow}{abs(v):.1f}%</span>'


def _trend(t):
    tr = t.get("trend")
    if tr == "new":
        return '<small class="trend-new">NEW</small>'
    if tr == "hot":
        return '<small class="trend-hot">急上昇</small>'
    ch = t.get("rank_change") or 0
    if tr == "up":
        return f'<small class="trend-up">▲{ch}</small>'
    if tr == "down":
        return f'<small class="trend-down">▼{-ch}</small>'
    return '<small class="trend-stay">→</small>'


def env() -> Environment:
    e = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))
    e.filters.update(source=lambda s: SOURCE_LABEL.get(s, s), region=lambda r: REGION_LABEL.get(r, r),
                     yen=lambda v: f"¥{int(v):,}" if v is not None else "-", pct=_pct, trend=_trend)
    return e


def build(demo: bool = False) -> Path:
    s = settings()
    out = (ROOT / s["site"]["output_dir"]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(HERE / "static", out / "static", dirs_exist_ok=True)
    (out / ".nojekyll").touch()
    e = env()
    common = {"site_title": s["site"]["title"], "demo": demo,
              "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")}

    with db.connect() as conn:
        dates = db.topic_dates(conn)[: s["site"]["archive_days"]]
        market_dates = [r[0] for r in conn.execute("SELECT date FROM reports WHERE kind='market' ORDER BY date DESC")]
        market = db.load_report(conn, market_dates[0], "market") if market_dates else None
        days = []
        for i, d in enumerate(dates):
            topics = db.load_topics(conn, d)
            n_posts, n_comments = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM((SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id)),0) "
                "FROM posts p WHERE collected_date=?", (d,)).fetchone()
            days.append({"date": d, "top": topics[:3]})
            m_for_day = market if (market and market["date"] == d) else (db.load_report(conn, d, "market") or market)
            ctx = {**common, "date": d, "topics": topics, "market": m_for_day,
                   "ai": all(t.get("ai") for t in topics) if topics else True,
                   "all_sources": sorted({src for t in topics for src in t["sources"]}),
                   "stats": {"posts": n_posts, "comments": n_comments,
                             "new": sum(t.get("trend") == "new" for t in topics),
                             "positive": sum(t["sentiment"]["overall"] == "好意的" for t in topics)}}
            write(out / "daily" / f"{d}.html", e.get_template("index.html").render(**ctx, root="../", nav="topics"))
            if i == 0:
                write(out / "index.html", e.get_template("index.html").render(**ctx, root="", nav="topics"))
            cards = (m_for_day or {}).get("cards", [])
            for t in topics:
                write(out / "topic" / d / f"{t['topic_key']}.html", e.get_template("topic.html").render(
                    **common, date=d, t=t, related=match_cards(t.get("cards", []), cards), root="../../", nav="topics"))

    write(out / "archive.html", e.get_template("archive.html").render(**common, days=days, root="", nav="archive"))
    m = market or {"date": "-", "cards": [], "risers": [], "fallers": [], "index": [], "shops": []}
    m.setdefault("commentary", {})
    slim = [{k: c[k] for k in ("key", "name", "rarity", "number", "history", "shop_prices")} for c in m["cards"]]
    write(out / "market.html", e.get_template("market.html").render(
        **common, m=m, root="", nav="market", cards_json=json.dumps(slim, ensure_ascii=False).replace("</", "<\\/"),
        index_json=json.dumps(m["index"]), initial_key=(m["risers"][0]["key"] if m["risers"] else "")))
    # 外部連携用に JSON も出力
    write(out / "data" / "latest.json", json.dumps(
        {"date": dates[0] if dates else None, "topics": db_topics_light(dates[0]) if dates else [],
         "market": {k: m.get(k) for k in ("date", "commentary", "risers", "fallers")}},
        ensure_ascii=False, default=str))
    log.info("サイトを出力しました: %s", out)
    return out


def db_topics_light(date: str) -> list[dict]:
    with db.connect() as conn:
        return [{k: t.get(k) for k in ("rank", "topic_key", "title", "summary", "category", "region", "sources",
                                       "score", "trend", "sentiment")} for t in db.load_topics(conn, date)]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
