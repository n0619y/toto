"""Reddit 収集（公式 OAuth API / application-only）。

https://www.reddit.com/prefs/apps で "script" タイプのアプリを作り、
REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT を設定する。
"""
from __future__ import annotations

import time

from ..config import env, get_logger
from ..models import Comment, Post, guess_region
from .base import Collector, iso

log = get_logger()


class RedditCollector(Collector):
    name = "reddit"
    required_env = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")

    def _token(self) -> str:
        r = self.session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(env("REDDIT_CLIENT_ID"), env("REDDIT_CLIENT_SECRET")),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.ua},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    @property
    def ua(self) -> str:
        return env("REDDIT_USER_AGENT") or "pokeca-trends/0.1"

    def collect(self) -> list[Post]:
        headers = {"User-Agent": self.ua, "Authorization": f"bearer {self._token()}"}
        posts: list[Post] = []
        for sub in self.cfg.get("subreddits", []):
            listing = self.get_json(
                f"https://oauth.reddit.com/r/{sub}/{self.cfg.get('listing', 'top')}",
                params={"t": self.cfg.get("time_filter", "day"), "limit": self.cfg.get("limit_per_sub", 50)},
                headers=headers,
            )
            for child in listing["data"]["children"]:
                d = child["data"]
                if d.get("stickied"):
                    continue
                text = (d.get("title", "") + "\n" + (d.get("selftext") or "")).strip()
                post = Post(
                    id=f"reddit:{d['id']}", source="reddit", region=guess_region(text),
                    author=d.get("author", ""), text=text[:4000],
                    url="https://www.reddit.com" + d["permalink"], created_at=iso(d["created_utc"]),
                    likes=d.get("score", 0), comments_count=d.get("num_comments", 0),
                    lang="en", shares=d.get("num_crossposts", 0),
                )
                if post.comments_count:
                    post.comments = self._comments(d["id"], headers)
                posts.append(post)
                time.sleep(0.7)  # レート制限（100req/分）に余裕を持たせる
            log.info("[reddit] r/%s: 累計 %d 件", sub, len(posts))
        return posts

    def _comments(self, post_id: str, headers: dict) -> list[Comment]:
        data = self.get_json(
            f"https://oauth.reddit.com/comments/{post_id}",
            params={"limit": self.cfg.get("comments_per_post", 40), "depth": 1, "sort": "top"},
            headers=headers,
        )
        out = []
        for c in data[1]["data"]["children"]:
            if c["kind"] != "t1":
                continue
            cd = c["data"]
            out.append(Comment(id=f"reddit:{cd['id']}", author=cd.get("author", ""), text=cd.get("body", "")[:1500],
                               likes=cd.get("score", 0), created_at=iso(cd.get("created_utc", 0))))
        return out
