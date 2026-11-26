"""SQLite 永続化。日次の投稿・トピック・買取価格を蓄積する。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import ROOT
from .models import Post, Comment

DB_PATH = ROOT / "data" / "pokeca.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY, source TEXT, region TEXT, author TEXT, text TEXT, url TEXT,
  created_at TEXT, collected_date TEXT, likes INT, comments_count INT, shares INT,
  views INT, lang TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(collected_date);
CREATE TABLE IF NOT EXISTS comments (
  id TEXT PRIMARY KEY, post_id TEXT, author TEXT, text TEXT, likes INT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE TABLE IF NOT EXISTS topics (
  date TEXT, topic_key TEXT, rank INT, data TEXT, PRIMARY KEY(date, topic_key)
);
CREATE TABLE IF NOT EXISTS buylist_prices (
  date TEXT, shop TEXT, card_key TEXT, card_name TEXT, card_number TEXT, rarity TEXT,
  price INT, condition TEXT, PRIMARY KEY(date, shop, card_key, condition)
);
CREATE INDEX IF NOT EXISTS idx_prices_card ON buylist_prices(card_key, date);
CREATE TABLE IF NOT EXISTS reports (date TEXT, kind TEXT, data TEXT, PRIMARY KEY(date, kind));
CREATE TABLE IF NOT EXISTS own_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, platform_id TEXT, status TEXT,
  text TEXT, topic_key TEXT, topic_title TEXT, archetype TEXT, created_at TEXT, cycle TEXT,
  metrics TEXT, metrics_at TEXT, reward REAL, reply_sentiment TEXT, review TEXT
);
CREATE INDEX IF NOT EXISTS idx_own_created ON own_posts(created_at);
"""


@contextmanager
def connect(path: Path | None = None):
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- 投稿 ----------
def save_posts(conn, posts: list[Post], date: str) -> None:
    for p in posts:
        conn.execute(
            "INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.source, p.region, p.author, p.text, p.url, p.created_at, date,
             p.likes, p.comments_count, p.shares, p.views, p.lang),
        )
        for c in p.comments:
            conn.execute(
                "INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?)",
                (c.id, p.id, c.author, c.text, c.likes, c.created_at),
            )


def load_posts(conn, date: str) -> list[Post]:
    posts = []
    for r in conn.execute("SELECT * FROM posts WHERE collected_date=?", (date,)):
        d = dict(r)
        d.pop("collected_date")
        p = Post(**d)
        p.comments = [
            Comment(id=c["id"], author=c["author"], text=c["text"], likes=c["likes"], created_at=c["created_at"])
            for c in conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY likes DESC", (p.id,))
        ]
        posts.append(p)
    return posts


# ---------- トピック ----------
def save_topics(conn, date: str, topics: list[dict]) -> None:
    conn.execute("DELETE FROM topics WHERE date=?", (date,))
    for t in topics:
        conn.execute("INSERT INTO topics VALUES (?,?,?,?)",
                     (date, t["topic_key"], t["rank"], json.dumps(t, ensure_ascii=False)))


def load_topics(conn, date: str) -> list[dict]:
    return [json.loads(r["data"]) for r in
            conn.execute("SELECT data FROM topics WHERE date=? ORDER BY rank", (date,))]


def topic_dates(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT date FROM topics ORDER BY date DESC")]


def previous_topic_date(conn, date: str) -> str | None:
    r = conn.execute("SELECT MAX(date) FROM topics WHERE date<?", (date,)).fetchone()
    return r[0] if r else None


# ---------- 買取価格 ----------
def save_prices(conn, date: str, shop: str, rows: list[dict]) -> int:
    conn.execute("DELETE FROM buylist_prices WHERE date=? AND shop=?", (date, shop))
    n = 0
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO buylist_prices VALUES (?,?,?,?,?,?,?,?)",
            (date, shop, r["card_key"], r["card_name"], r.get("card_number", ""),
             r.get("rarity", ""), int(r["price"]), r.get("condition", "")),
        )
        n += 1
    return n


# ---------- レポート ----------
def save_report(conn, date: str, kind: str, data: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?)",
                 (date, kind, json.dumps(data, ensure_ascii=False)))


def load_report(conn, date: str, kind: str) -> dict | None:
    r = conn.execute("SELECT data FROM reports WHERE date=? AND kind=?", (date, kind)).fetchone()
    return json.loads(r[0]) if r else None


# ---------- 自動投稿 ----------
OWN_COLS = ("platform", "platform_id", "status", "text", "topic_key", "topic_title", "archetype",
            "created_at", "cycle", "metrics", "metrics_at", "reward", "reply_sentiment", "review")
JSON_COLS = ("metrics", "reply_sentiment", "review")


def _j(v):
    return None if v is None else json.dumps(v, ensure_ascii=False)


def add_own_post(conn, rec: dict) -> int:
    vals = [_j(rec.get(c)) if c in JSON_COLS else rec.get(c) for c in OWN_COLS]
    cur = conn.execute(f"INSERT INTO own_posts ({','.join(OWN_COLS)}) VALUES ({','.join('?' * len(OWN_COLS))})", vals)
    return cur.lastrowid


def update_own_post(conn, pid: int, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = [_j(v) if k in JSON_COLS else v for k, v in fields.items()]
    conn.execute(f"UPDATE own_posts SET {sets} WHERE id=?", (*vals, pid))


def own_posts(conn, where: str = "1=1", params: tuple = (), limit: int = 500) -> list[dict]:
    out = []
    for r in conn.execute(f"SELECT * FROM own_posts WHERE {where} ORDER BY created_at DESC LIMIT ?", (*params, limit)):
        d = dict(r)
        for c in JSON_COLS:
            d[c] = json.loads(d[c]) if d[c] else None
        out.append(d)
    return out


def latest_report(conn, kind: str) -> dict | None:
    r = conn.execute("SELECT data FROM reports WHERE kind=? ORDER BY date DESC LIMIT 1", (kind,)).fetchone()
    return json.loads(r[0]) if r else None
