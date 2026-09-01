#!/usr/bin/env python3
"""ガイドラインPDF → 全文検索データベース（SQLite FTS5）ビルダー。

pdf/ フォルダのPDFをページ単位でテキスト化し、guidelines.db に格納します。
日本語・英語どちらも部分一致で検索できるよう trigram トークナイザを使用します。

使い方:
    python guidelines/build_index.py            # 差分ビルド（未登録/更新PDFのみ）
    python guidelines/build_index.py --rebuild  # 全再構築
    python guidelines/build_index.py --stats    # 登録状況を表示

依存: pymupdf（推奨・高速）または pypdf のどちらか。
    pip install pymupdf
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "catalog" / "guidelines.json"
PDF_DIR = HERE / "pdf"
DB_PATH = HERE / "guidelines.db"

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    title_ja      TEXT,
    title_en      TEXT,
    organization  TEXT,
    year          INTEGER,
    region        TEXT,
    country       TEXT,
    category      TEXT,
    language      TEXT,
    url           TEXT,
    landing_url   TEXT,
    doi           TEXT,
    notes         TEXT,
    file          TEXT,
    pages         INTEGER DEFAULT 0,
    chars         INTEGER DEFAULT 0,
    sha1          TEXT,
    indexed_at    TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    rowid   INTEGER PRIMARY KEY,
    doc_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page    INTEGER NOT NULL,
    text    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_doc ON pages(doc_id, page);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    text,
    content='pages',
    content_rowid='rowid',
    tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
  INSERT INTO pages_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
  INSERT INTO pages_fts(pages_fts, rowid, text) VALUES('delete', old.rowid, old.text);
END;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


# --------------------------------------------------------------------------- #
# PDFテキスト抽出
# --------------------------------------------------------------------------- #
def _extract_pymupdf(path: Path) -> list[str]:
    import pymupdf  # type: ignore

    out = []
    with pymupdf.open(path) as doc:
        for page in doc:
            out.append(page.get_text("text"))
    return out


def _extract_pypdf(path: Path) -> list[str]:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    return [(p.extract_text() or "") for p in reader.pages]


def extract_pages(path: Path) -> list[str]:
    errors = []
    for fn in (_extract_pymupdf, _extract_pypdf):
        try:
            return fn(path)
        except ImportError as exc:
            errors.append(f"{fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fn.__name__}: {type(exc).__name__}: {exc}")
    raise RuntimeError("PDFを読めませんでした。pip install pymupdf を実行してください。\n" + "\n".join(errors))


_WS_RE = re.compile(r"[ \t　]+")
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")
_JA_LINEBREAK_RE = re.compile(r"([^\x00-\x7F])\n([^\x00-\x7F])")


def normalize_text(text: str) -> str:
    """検索しやすいよう正規化する（全角英数→半角、行末ハイフン結合、日本語の改行除去など）。"""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r", "")
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)  # 英単語の行末ハイフン
    text = _JA_LINEBREAK_RE.sub(r"\1\2", text)  # 日本語文中の改行
    text = _JA_LINEBREAK_RE.sub(r"\1\2", text)
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# ビルド
# --------------------------------------------------------------------------- #
def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["guidelines"] if isinstance(data, dict) else data


def expected_filename(entry: dict) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", entry["id"]).strip("-")
    return f"{entry.get('region', 'XX')}_{entry.get('year', 0)}_{slug}.pdf"


def open_db(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_document(conn: sqlite3.Connection, e: dict, file: str | None, pages: int, chars: int, sha1: str | None) -> None:
    conn.execute(
        """INSERT INTO documents(id,title_ja,title_en,organization,year,region,country,category,language,
                                 url,landing_url,doi,notes,file,pages,chars,sha1,indexed_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             title_ja=excluded.title_ja, title_en=excluded.title_en, organization=excluded.organization,
             year=excluded.year, region=excluded.region, country=excluded.country, category=excluded.category,
             language=excluded.language, url=excluded.url, landing_url=excluded.landing_url, doi=excluded.doi,
             notes=excluded.notes, file=excluded.file, pages=excluded.pages, chars=excluded.chars,
             sha1=excluded.sha1, indexed_at=excluded.indexed_at""",
        (
            e["id"], e.get("title_ja"), e.get("title_en"), e.get("organization"), e.get("year"),
            e.get("region"), e.get("country"), e.get("category"), e.get("language"),
            e.get("url"), e.get("landing_url"), e.get("doi"), e.get("notes"),
            file, pages, chars, sha1, datetime.now(timezone.utc).isoformat() if file else None,
        ),
    )


def build(catalog_path: Path, pdf_dir: Path, db_path: Path, rebuild: bool = False) -> dict:
    catalog = load_catalog(catalog_path)
    if rebuild and db_path.exists():
        db_path.unlink()
        for suffix in ("-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
    conn = open_db(db_path)
    existing = {row[0]: row[1] for row in conn.execute("SELECT id, sha1 FROM documents")}

    stats = {"indexed": 0, "skipped": 0, "missing": 0, "failed": 0, "pages": 0}
    for e in catalog:
        fname = expected_filename(e)
        pdf = pdf_dir / fname
        if not pdf.exists():
            # 別名で保存されている場合（id を含むファイル名）も許容
            cands = list(pdf_dir.glob(f"*{e['id']}*.pdf"))
            pdf = cands[0] if cands else pdf
        if not pdf.exists():
            upsert_document(conn, e, None, 0, 0, None)
            stats["missing"] += 1
            continue
        digest = sha1_of(pdf)
        if existing.get(e["id"]) == digest:
            stats["skipped"] += 1
            continue
        try:
            raw_pages = extract_pages(pdf)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ 抽出失敗 {pdf.name}: {exc}")
            upsert_document(conn, e, pdf.name, 0, 0, None)
            stats["failed"] += 1
            continue
        upsert_document(conn, e, pdf.name, len(raw_pages), 0, None)  # 先に親行を作る（FK制約）
        conn.execute("DELETE FROM pages WHERE doc_id=?", (e["id"],))
        chars = 0
        n = 0
        for i, raw in enumerate(raw_pages, 1):
            text = normalize_text(raw)
            if len(text) < 20:
                continue
            conn.execute("INSERT INTO pages(doc_id, page, text) VALUES(?,?,?)", (e["id"], i, text))
            chars += len(text)
            n += 1
        upsert_document(conn, e, pdf.name, len(raw_pages), chars, digest)
        conn.commit()
        stats["indexed"] += 1
        stats["pages"] += n
        print(f"✅ {e.get('title_ja') or e.get('title_en')}  ({len(raw_pages)}p, {chars:,}字)")

    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('built_at',?)", (datetime.now(timezone.utc).isoformat(),))
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('catalog_count',?)", (str(len(catalog)),))
    conn.commit()
    try:
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('optimize')")
        conn.commit()
    except sqlite3.Error:
        pass
    conn.close()
    return stats


def print_stats(db_path: Path) -> None:
    if not db_path.exists():
        print("DBがまだありません。python guidelines/build_index.py を実行してください。")
        return
    conn = sqlite3.connect(db_path)
    total, with_file = conn.execute("SELECT COUNT(*), SUM(file IS NOT NULL) FROM documents").fetchone()
    pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    print(f"登録ガイドライン: {total} 件（PDFあり: {with_file or 0} 件） / 検索対象ページ: {pages:,}")
    for region, n, p in conn.execute(
        "SELECT region, COUNT(*), SUM(pages) FROM documents GROUP BY region ORDER BY region"
    ):
        print(f"  {region}: {n} 件 / {p or 0:,} ページ")
    print("\nPDF未取得:")
    for (t,) in conn.execute("SELECT COALESCE(title_ja,title_en) FROM documents WHERE file IS NULL"):
        print("  -", t)
    conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    ap.add_argument("--pdf-dir", type=Path, default=PDF_DIR)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args(argv)
    if args.stats:
        print_stats(args.db)
        return 0
    stats = build(args.catalog, args.pdf_dir, args.db, args.rebuild)
    print("\n========================================")
    print(f"新規/更新: {stats['indexed']}  変更なし: {stats['skipped']}  PDF未取得: {stats['missing']}  失敗: {stats['failed']}")
    print(f"DB: {args.db}")
    print("========================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
