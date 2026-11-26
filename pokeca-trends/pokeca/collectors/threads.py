"""Threads 収集（Threads API keyword_search）。

Meta開発者アプリで threads_basic / threads_keyword_search 権限を取得し、
THREADS_ACCESS_TOKEN を設定する。※他人の投稿のいいね数は取得できないため、
ランキングでは返信数を主な指標として使う。
"""
from __future__ import annotations

from ..config import env, get_logger
from ..models import Comment, Post, guess_region
from .base import Collector

log = get_logger()
BASE = "https://graph.threads.net/v1.0"


class ThreadsCollector(Collector):
    name = "threads"
    required_env = ("THREADS_ACCESS_TOKEN",)

    def collect(self) -> list[Post]:
        token = env("THREADS_ACCESS_TOKEN")
        posts: dict[str, Post] = {}
        for word in self.keywords.get("ja", []) + self.keywords.get("en", []):
            data = self.get_json(f"{BASE}/keyword_search", params={
                "q": word, "search_type": "TOP", "since": int(self.since.timestamp()),
                "limit": self.cfg.get("limit_per_query", 50),
                "fields": "id,text,permalink,timestamp,username,has_replies",
                "access_token": token,
            })
            for m in data.get("data", []):
                if m["id"] in posts or not m.get("text"):
                    continue
                p = Post(id=f"threads:{m['id']}", source="threads", region=guess_region(m["text"]),
                         author=m.get("username", ""), text=m["text"], url=m.get("permalink", ""),
                         created_at=m.get("timestamp", ""))
                if m.get("has_replies"):
                    rep = self.get_json(f"{BASE}/{m['id']}/replies", params={
                        "fields": "id,text,username,timestamp", "access_token": token,
                        "limit": self.cfg.get("replies_per_post", 30)})
                    p.comments = [Comment(id=f"threads:{r['id']}", author=r.get("username", ""),
                                          text=r.get("text", ""), created_at=r.get("timestamp", ""))
                                  for r in rep.get("data", []) if r.get("text")]
                    p.comments_count = len(p.comments)
                posts[m["id"]] = p
            log.info("[threads] '%s': 累計 %d 件", word, len(posts))
        return list(posts.values())
