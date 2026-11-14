"""収集器の共通処理。"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import requests

from ..config import get_logger
from ..models import Post

log = get_logger()


class Collector:
    name = "base"
    required_env: tuple[str, ...] = ()

    def __init__(self, cfg: dict, keywords: dict):
        self.cfg = cfg
        self.keywords = keywords
        self.session = requests.Session()
        self.since = datetime.now(timezone.utc) - timedelta(hours=24)

    def available(self) -> bool:
        from ..config import env
        missing = [k for k in self.required_env if not env(k)]
        if missing:
            log.warning("[%s] スキップ: 環境変数 %s が未設定です", self.name, ", ".join(missing))
            return False
        return True

    def collect(self) -> list[Post]:  # pragma: no cover - 各収集器で実装
        raise NotImplementedError

    # 429/5xx はバックオフしてリトライ
    def get_json(self, url: str, *, params=None, headers=None, auth=None, retries: int = 3):
        for attempt in range(retries + 1):
            r = self.session.get(url, params=params, headers=headers, auth=auth, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                wait = int(r.headers.get("retry-after", 0) or 0) or 2 ** (attempt + 2)
                log.warning("[%s] HTTP %s — %d秒待機してリトライ", self.name, r.status_code, wait)
                time.sleep(min(wait, 120))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()


def iso(ts: float | str) -> str:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ts
