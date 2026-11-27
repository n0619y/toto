"""在庫と買取価格の台帳（SQLite）。"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .core import card_key, normalize_grade

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    day TEXT, shop TEXT, card_key TEXT, name TEXT, grade TEXT, price REAL,
    PRIMARY KEY (day, shop, card_key, grade)
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_key TEXT NOT NULL, name TEXT,
    bought_on TEXT, bought_from TEXT, buy_price REAL NOT NULL,
    status TEXT NOT NULL DEFAULT '在庫',      -- 在庫 / 鑑定中 / 返却済 / 売却済
    psa_order TEXT, cert TEXT, grade TEXT NOT NULL DEFAULT 'RAW',
    extra_cost REAL NOT NULL DEFAULT 0,       -- 鑑定費・送料など、この1枚に按分した費用
    sold_on TEXT, sold_to TEXT, sold_price REAL
);
"""
STATUSES = ("在庫", "鑑定中", "返却済", "売却済")


class DB:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---- 買取表 -----------------------------------------------------------
    def save_prices(self, rows, day: str) -> int:
        """rows: shop, number, name, grade, price を持つ辞書の列。"""
        n = 0
        for row in rows:
            price = float(str(row["price"]).replace(",", "").replace("円", "") or 0)
            if price <= 0 or not str(row.get("number") or "").strip():
                continue
            name = str(row.get("name") or "").strip()
            self.db.execute(
                "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?)",
                (day, row["shop"].strip(), card_key(row["number"], name), name,
                 normalize_grade(row.get("grade", "")), price),
            )
            n += 1
        self.db.commit()
        return n

    def import_prices(self, csv_path: str | Path, day: str) -> int:
        """CSV 列: shop, number, name, grade, price"""
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            return self.save_prices(csv.DictReader(f), day)

    def latest_prices(self) -> list[dict]:
        """各店の「その店の最新取得日」の行だけを返す。"""
        rows = self.db.execute(
            """SELECT p.* FROM prices p
               JOIN (SELECT shop, MAX(day) AS d FROM prices GROUP BY shop) m
                 ON p.shop = m.shop AND p.day = m.d"""
        )
        return [dict(r) for r in rows]

    def known_names(self) -> dict[str, set[str]]:
        """正規化したカード名 -> 番号の集合（番号の無い投稿を照合するため）。"""
        out: dict[str, set[str]] = {}
        for r in self.db.execute("SELECT DISTINCT card_key FROM prices"):
            number, name = r["card_key"].split("|", 1)
            out.setdefault(name, set()).add(number)
        return out

    def get(self, key: str) -> str | None:
        r = self.db.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return r["v"] if r else None

    def put(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, value))
        self.db.commit()

    # ---- 在庫 -------------------------------------------------------------
    def add_stock(self, number, name, buy_price, bought_on, bought_from="") -> int:
        cur = self.db.execute(
            "INSERT INTO stock (card_key, name, buy_price, bought_on, bought_from) VALUES (?,?,?,?,?)",
            (card_key(number, name), name, float(buy_price), bought_on, bought_from),
        )
        self.db.commit()
        return cur.lastrowid

    def update_stock(self, stock_id: int, **fields) -> None:
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"status は {STATUSES} のいずれか")
        if "grade" in fields:
            fields["grade"] = normalize_grade(fields["grade"])
        sets = ", ".join(f"{k}=?" for k in fields)
        cur = self.db.execute(f"UPDATE stock SET {sets} WHERE id=?", (*fields.values(), stock_id))
        if cur.rowcount == 0:
            raise KeyError(f"在庫ID {stock_id} がありません")
        self.db.commit()

    def stock(self, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM stock", ()
        if status:
            q, args = q + " WHERE status=?", (status,)
        return [dict(r) | {"cost_basis": r["buy_price"] + r["extra_cost"]}
                for r in self.db.execute(q + " ORDER BY id", args)]
