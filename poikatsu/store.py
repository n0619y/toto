"""台帳（SQLite）。提示した案件と、本人が完了した実績を記録する。"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .models import Opportunity

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id TEXT PRIMARY KEY,
    first_day TEXT NOT NULL,
    last_day TEXT NOT NULL,
    site TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    task_type TEXT,
    verdict TEXT,
    value_yen REAL,
    minutes REAL,
    selected INTEGER DEFAULT 0,
    done_at TEXT,
    actual_yen REAL
);
CREATE TABLE IF NOT EXISTS grants (
    id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    site TEXT NOT NULL,
    title TEXT NOT NULL,
    yen REAL
);
"""


class Store:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def done_ids(self) -> set[str]:
        rows = self.db.execute("SELECT id FROM offers WHERE done_at IS NOT NULL")
        return {r["id"] for r in rows}

    def record_offers(self, day: str, opps: list[Opportunity]) -> None:
        for o in opps:
            self.db.execute(
                """INSERT INTO offers
                   (id, first_day, last_day, site, title, url, task_type, verdict,
                    value_yen, minutes, selected)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     last_day=excluded.last_day, verdict=excluded.verdict,
                     value_yen=excluded.value_yen, minutes=excluded.minutes,
                     selected=MAX(selected, excluded.selected)""",
                (o.id, day, day, o.site, o.title, o.url, o.task_type, o.verdict,
                 o.value_yen, o.minutes, int(o.selected)),
            )
        self.db.commit()

    def mark_done(self, ids: list[str], day: str, actual_yen: float | None = None) -> int:
        """完了を記録。ids に 'all' を渡すと、その日に選定された未完了案件すべて。"""
        if ids == ["all"]:
            cur = self.db.execute(
                """UPDATE offers SET done_at=?, actual_yen=COALESCE(?, value_yen)
                   WHERE last_day=? AND selected=1 AND done_at IS NULL""",
                (day, actual_yen, day),
            )
        else:
            marks = ",".join("?" * len(ids))
            cur = self.db.execute(
                f"""UPDATE offers SET done_at=?, actual_yen=COALESCE(?, value_yen)
                    WHERE id IN ({marks}) AND done_at IS NULL""",
                (day, actual_yen, *ids),
            )
        self.db.commit()
        return cur.rowcount

    def record_grant(self, day: str, site: str, title: str, yen: float) -> bool:
        """ポイント付与通知を記帳する。新規なら True。同額の未完了案件があれば完了にする。"""
        gid = hashlib.sha1(f"{site}|{title}|{day}".encode("utf-8")).hexdigest()[:8]
        cur = self.db.execute(
            "INSERT OR IGNORE INTO grants (id, day, site, title, yen) VALUES (?,?,?,?,?)",
            (gid, day, site, title, yen),
        )
        if cur.rowcount and yen:
            row = self.db.execute(
                """SELECT id FROM offers WHERE site=? AND done_at IS NULL
                   AND ABS(value_yen - ?) < 0.01 ORDER BY last_day DESC LIMIT 1""",
                (site, yen),
            ).fetchone()
            if row:
                self.db.execute("UPDATE offers SET done_at=?, actual_yen=? WHERE id=?",
                                (day, yen, row["id"]))
        self.db.commit()
        return bool(cur.rowcount)

    def month_grants(self, month: str) -> tuple[int, float]:
        r = self.db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(yen), 0) AS yen FROM grants WHERE day LIKE ?",
            (month + "%",),
        ).fetchone()
        return r["n"], r["yen"]

    def site_stats(self, since_day: str) -> dict[str, dict]:
        """サイト別の「選定数・完了数・実績円」。経理部→経営企画部のフィードバック用。"""
        rows = self.db.execute(
            """SELECT site,
                      SUM(selected) AS offered,
                      SUM(CASE WHEN done_at IS NOT NULL THEN 1 ELSE 0 END) AS done,
                      SUM(COALESCE(actual_yen, 0)) AS yen
               FROM offers WHERE last_day >= ? GROUP BY site""",
            (since_day,),
        )
        return {r["site"]: dict(r) for r in rows}

    def month_total(self, month: str) -> tuple[int, float]:
        r = self.db.execute(
            """SELECT COUNT(*) AS n, COALESCE(SUM(actual_yen), 0) AS yen
               FROM offers WHERE done_at LIKE ?""",
            (month + "%",),
        ).fetchone()
        return r["n"], r["yen"]
