"""X / Threads への投稿と、投稿後の反応（数値・返信）の取得。すべて公式API。"""
from __future__ import annotations

import time

import requests

from ..config import env, get_logger
from ..models import Comment

log = get_logger()


class XPublisher:
    """X API v2。投稿には OAuth 1.0a ユーザー認証（Read and Write 権限）が必要。"""
    name = "x"
    env_keys = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")

    def ready(self) -> bool:
        return all(env(k) for k in self.env_keys)

    def _auth(self):
        from requests_oauthlib import OAuth1
        return OAuth1(env("X_API_KEY"), env("X_API_SECRET"), env("X_ACCESS_TOKEN"), env("X_ACCESS_SECRET"))

    def post(self, text: str) -> str:
        r = requests.post("https://api.x.com/2/tweets", json={"text": text}, auth=self._auth(), timeout=30)
        r.raise_for_status()
        return r.json()["data"]["id"]

    def metrics(self, ids: list[str]) -> dict[str, dict]:
        out = {}
        for i in range(0, len(ids), 100):
            r = requests.get("https://api.x.com/2/tweets", auth=self._auth(), timeout=30, params={
                "ids": ",".join(ids[i:i + 100]), "tweet.fields": "public_metrics,non_public_metrics"})
            if r.status_code == 400:  # 古い投稿は non_public_metrics が取れないため公開指標のみで再取得
                r = requests.get("https://api.x.com/2/tweets", auth=self._auth(), timeout=30,
                                 params={"ids": ",".join(ids[i:i + 100]), "tweet.fields": "public_metrics"})
            r.raise_for_status()
            for t in r.json().get("data", []):
                m = t.get("public_metrics", {})
                out[t["id"]] = {"likes": m.get("like_count", 0), "replies": m.get("reply_count", 0),
                                "reposts": m.get("retweet_count", 0), "quotes": m.get("quote_count", 0),
                                "bookmarks": m.get("bookmark_count", 0), "views": m.get("impression_count", 0)}
        return out

    def replies(self, pid: str, limit: int = 50) -> list[Comment]:
        r = requests.get("https://api.x.com/2/tweets/search/recent", auth=self._auth(), timeout=30, params={
            "query": f"conversation_id:{pid} is:reply", "max_results": max(10, min(limit, 100)),
            "tweet.fields": "public_metrics,created_at"})
        r.raise_for_status()
        return [Comment(id=f"x:{t['id']}", author="", text=t["text"],
                        likes=t.get("public_metrics", {}).get("like_count", 0)) for t in r.json().get("data", [])]


class ThreadsPublisher:
    """Threads API。threads_content_publish / threads_manage_insights / threads_read_replies 権限が必要。"""
    name = "threads"
    base = "https://graph.threads.net/v1.0"

    def ready(self) -> bool:
        return bool(env("THREADS_ACCESS_TOKEN"))

    def _p(self, **kw):
        return {"access_token": env("THREADS_ACCESS_TOKEN"), **kw}

    def post(self, text: str) -> str:
        uid = env("THREADS_USER_ID") or "me"
        r = requests.post(f"{self.base}/{uid}/threads", params=self._p(media_type="TEXT", text=text), timeout=30)
        r.raise_for_status()
        creation = r.json()["id"]
        time.sleep(5)  # コンテナの準備待ち（公式ドキュメント推奨）
        r = requests.post(f"{self.base}/{uid}/threads_publish", params=self._p(creation_id=creation), timeout=30)
        r.raise_for_status()
        return r.json()["id"]

    def metrics(self, ids: list[str]) -> dict[str, dict]:
        out = {}
        for i in ids:
            r = requests.get(f"{self.base}/{i}/insights", params=self._p(metric="views,likes,replies,reposts,quotes"), timeout=30)
            if not r.ok:
                log.warning("[threads] %s のインサイト取得失敗: %s", i, r.text[:120])
                continue
            vals = {d["name"]: (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value", 0))
                    for d in r.json().get("data", [])}
            out[i] = {k: vals.get(k, 0) or 0 for k in ("views", "likes", "replies", "reposts", "quotes")}
        return out

    def replies(self, pid: str, limit: int = 50) -> list[Comment]:
        r = requests.get(f"{self.base}/{pid}/replies", params=self._p(fields="id,text,timestamp"), timeout=30)
        r.raise_for_status()
        return [Comment(id=f"threads:{x['id']}", author="", text=x.get("text", ""))
                for x in r.json().get("data", [])[:limit] if x.get("text")]


PUBLISHERS = {"x": XPublisher, "threads": ThreadsPublisher}
