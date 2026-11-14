"""SNS収集器。設定と環境変数が揃っているものだけ実行する。"""
from __future__ import annotations

from ..config import get_logger, settings
from ..models import Post
from .instagram import InstagramCollector
from .reddit import RedditCollector
from .threads import ThreadsCollector
from .x_twitter import XCollector

log = get_logger()
COLLECTORS = {"x": XCollector, "threads": ThreadsCollector, "instagram": InstagramCollector, "reddit": RedditCollector}


def collect_all(only: list[str] | None = None) -> list[Post]:
    s = settings()
    posts: list[Post] = []
    for name, cls in COLLECTORS.items():
        cfg = s["collectors"].get(name, {})
        if (only and name not in only) or not cfg.get("enabled", True):
            continue
        c = cls(cfg, s["keywords"])
        if not c.available():
            continue
        try:
            got = c.collect()
            log.info("[%s] 収集完了: %d 件", name, len(got))
            posts.extend(got)
        except Exception as exc:  # 1媒体の失敗で全体を止めない
            log.error("[%s] 収集失敗: %s", name, exc)
    return posts
