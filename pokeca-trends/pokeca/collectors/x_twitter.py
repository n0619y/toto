"""X（旧Twitter）収集（公式 API v2 Recent Search）。

X Developer Portal で発行した Bearer Token を X_BEARER_TOKEN に設定する。
検索APIは有料プランが必要で、月間の取得上限があるため max_results / replies を調整すること。
"""
from __future__ import annotations

from ..config import env, get_logger
from ..models import Comment, Post
from .base import Collector

log = get_logger()
API = "https://api.x.com/2/tweets/search/recent"
FIELDS = {
    "tweet.fields": "public_metrics,created_at,lang,conversation_id,author_id",
    "expansions": "author_id",
    "user.fields": "username",
}


class XCollector(Collector):
    name = "x"
    required_env = ("X_BEARER_TOKEN",)

    @property
    def headers(self):
        return {"Authorization": f"Bearer {env('X_BEARER_TOKEN')}"}

    def _search(self, query: str, max_results: int) -> tuple[list[dict], dict]:
        data = self.get_json(API, headers=self.headers, params={
            "query": query, "max_results": max(10, min(max_results, 100)),
            "start_time": self.since.strftime("%Y-%m-%dT%H:%M:%SZ"), "sort_order": "relevancy", **FIELDS,
        })
        users = {u["id"]: u["username"] for u in data.get("includes", {}).get("users", [])}
        return data.get("data", []), users

    def collect(self) -> list[Post]:
        posts: dict[str, Post] = {}
        for region, words in (("ja", self.keywords.get("ja", [])), ("global", self.keywords.get("en", []))):
            if not words:
                continue
            q = "(" + " OR ".join(f'"{w}"' if " " in w else w for w in words) + ") -is:retweet"
            q += " lang:ja" if region == "ja" else " -lang:ja"
            tweets, users = self._search(q, self.cfg.get("max_results_per_query", 100))
            for t in tweets:
                m = t.get("public_metrics", {})
                user = users.get(t.get("author_id"), "")
                posts[t["id"]] = Post(
                    id=f"x:{t['id']}", source="x", region=region, author=user, text=t["text"],
                    url=f"https://x.com/{user or 'i'}/status/{t['id']}", created_at=t.get("created_at", ""),
                    likes=m.get("like_count", 0), comments_count=m.get("reply_count", 0),
                    shares=m.get("retweet_count", 0) + m.get("quote_count", 0),
                    views=m.get("impression_count", 0), lang=t.get("lang", ""),
                )
            log.info("[x] %s: %d 件", region, len(tweets))

        if self.cfg.get("fetch_replies", True):
            # API消費を抑えるため、返信の多い上位投稿だけ返信を取得
            top = sorted(posts.values(), key=lambda p: p.comments_count, reverse=True)
            for p in top[: self.cfg.get("reply_top_n", 20)]:
                if not p.comments_count:
                    continue
                tid = p.id.split(":", 1)[1]
                replies, users = self._search(f"conversation_id:{tid} is:reply", self.cfg.get("replies_per_post", 30))
                p.comments = [
                    Comment(id=f"x:{r['id']}", author=users.get(r.get("author_id"), ""), text=r["text"],
                            likes=r.get("public_metrics", {}).get("like_count", 0), created_at=r.get("created_at", ""))
                    for r in replies
                ]
        return list(posts.values())
