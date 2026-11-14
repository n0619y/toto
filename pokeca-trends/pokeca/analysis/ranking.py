"""トピックランキングのスコア計算と前日比（急上昇・新着）の判定。"""
from __future__ import annotations

import math

from ..config import settings
from ..models import Post
from .topics import engagement


def score_topic(posts: list[Post]) -> float:
    w = settings()["ranking"]
    base = sum(engagement(p) for p in posts) + w["weight_post_count"] * math.log1p(len(posts)) * 3
    n_sources = len({p.source for p in posts})
    return round(base * (1 + w["source_diversity_bonus"] * (n_sources - 1)), 1)


def rank(topics: list[dict], posts_by_id: dict[str, Post], prev: list[dict]) -> list[dict]:
    prev_rank = {t["topic_key"]: t for t in prev}
    for t in topics:
        members = [posts_by_id[i] for i in t["post_ids"] if i in posts_by_id]
        t["score"] = score_topic(members)
        t["sources"] = sorted({p.source for p in members})
        regions = {p.region for p in members}
        t["region"] = "both" if len(regions) > 1 else (regions.pop() if regions else "ja")
        t["post_count"] = len(members)
        t["engagement"] = {
            "likes": sum(p.likes for p in members), "comments": sum(p.comments_count for p in members),
            "shares": sum(p.shares for p in members), "views": sum(p.views for p in members),
        }
    topics.sort(key=lambda t: t["score"], reverse=True)
    topics = topics[: settings()["ranking"]["top_n"]]
    for i, t in enumerate(topics, 1):
        t["rank"] = i
        p = prev_rank.get(t["topic_key"])
        if not p:
            t["trend"] = "new"
            t["rank_change"] = None
        else:
            t["rank_change"] = p["rank"] - i
            growth = t["score"] / p["score"] if p.get("score") else 1
            t["trend"] = "hot" if growth >= 1.5 else ("up" if t["rank_change"] > 0 else
                                                      "down" if t["rank_change"] < 0 else "stay")
            t["days_running"] = p.get("days_running", 1) + 1
        t.setdefault("days_running", 1)
    return topics
