"""Instagram 収集（Instagram Graph API ハッシュタグ検索）。

ビジネス/クリエイターアカウントに紐づく IG_USER_ID と IG_ACCESS_TOKEN が必要。
制約: 検索できるハッシュタグは7日間で30種類まで。他人の投稿のコメント本文は
APIで取得できないため、Instagram はキャプションと いいね/コメント数のみ利用する。
"""
from __future__ import annotations

from datetime import datetime

from ..config import env, get_logger
from ..models import Post, guess_region
from .base import Collector

log = get_logger()
BASE = "https://graph.facebook.com/v21.0"


class InstagramCollector(Collector):
    name = "instagram"
    required_env = ("IG_ACCESS_TOKEN", "IG_USER_ID")

    def collect(self) -> list[Post]:
        token, uid = env("IG_ACCESS_TOKEN"), env("IG_USER_ID")
        posts: dict[str, Post] = {}
        for tag in self.cfg.get("hashtags", []):
            found = self.get_json(f"{BASE}/ig_hashtag_search", params={"user_id": uid, "q": tag, "access_token": token})
            if not found.get("data"):
                continue
            hid = found["data"][0]["id"]
            for edge in ("top_media", "recent_media"):
                data = self.get_json(f"{BASE}/{hid}/{edge}", params={
                    "user_id": uid, "access_token": token, "limit": self.cfg.get("limit_per_hashtag", 50),
                    "fields": "id,caption,like_count,comments_count,permalink,timestamp,media_type",
                })
                for m in data.get("data", []):
                    ts = m.get("timestamp", "")
                    try:
                        if datetime.fromisoformat(ts.replace("+0000", "+00:00")) < self.since:
                            continue
                    except ValueError:
                        pass
                    cap = m.get("caption") or ""
                    if not cap or m["id"] in posts:
                        continue
                    posts[m["id"]] = Post(
                        id=f"instagram:{m['id']}", source="instagram", region=guess_region(cap), author="",
                        text=cap[:2000], url=m.get("permalink", ""), created_at=ts,
                        likes=m.get("like_count", 0) or 0, comments_count=m.get("comments_count", 0) or 0,
                    )
            log.info("[instagram] #%s: 累計 %d 件", tag, len(posts))
        return list(posts.values())
