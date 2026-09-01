#!/usr/bin/env python3
"""小児先天性心疾患ガイドライン 検索アプリ（ローカルWebサーバー）。

標準ライブラリだけで動きます（Flask等は不要）。

使い方:
    python guidelines/app.py                # http://127.0.0.1:8765 で起動
    python guidelines/app.py --port 9000
    python guidelines/app.py --open         # ブラウザを自動で開く

機能:
    - 全ガイドライン本文の全文検索（日本語/英語、部分一致、AND検索、"フレーズ"検索）
    - 地域 / カテゴリ / 年 / 発行団体 / 言語 で絞り込み
    - ヒット箇所のハイライト表示、該当ページをPDFで直接開く（#page=N）
    - ガイドライン一覧（カタログ）表示・元サイトへのリンク
    - （任意）Claude によるガイドライン根拠付きQ&A（ANTHROPIC_API_KEY を .env に設定した場合）
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = HERE / "guidelines.db"
PDF_DIR = HERE / "pdf"
STATIC_DIR = HERE / "static"
CATALOG_PATH = HERE / "catalog" / "guidelines.json"

# .env（リポジトリ直下）を読み込む。python-dotenv が無くても動くよう簡易実装
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


# --------------------------------------------------------------------------- #
# 検索エンジン
# --------------------------------------------------------------------------- #
class SearchEngine:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if not self.db_path.exists():
                raise FileNotFoundError(
                    f"{self.db_path} がありません。先に python guidelines/build_index.py を実行してください。"
                )
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # ---- クエリ解釈 ------------------------------------------------------- #
    @staticmethod
    def parse_query(q: str) -> list[str]:
        """"フレーズ" と 空白区切り語 を抽出。全角スペースも区切りとして扱う。"""
        q = q.replace("　", " ").strip()
        terms = []
        for m in re.finditer(r'"([^"]+)"|(\S+)', q):
            t = (m.group(1) or m.group(2)).strip()
            if t:
                terms.append(t)
        return terms

    @staticmethod
    def _fts_expr(terms: list[str]) -> str:
        # trigram トークナイザは 3文字未満の語をマッチできないため除外（LIKEで補完）
        parts = []
        for t in terms:
            if len(t) >= 3:
                parts.append('"' + t.replace('"', '""') + '"')
        return " AND ".join(parts)

    def _filters_sql(self, f: dict) -> tuple[str, list]:
        sql, params = [], []
        for col in ("region", "category", "organization", "language"):
            vals = f.get(col)
            if vals:
                sql.append(f"d.{col} IN ({','.join('?' * len(vals))})")
                params.extend(vals)
        if f.get("year_from"):
            sql.append("d.year >= ?")
            params.append(int(f["year_from"]))
        if f.get("year_to"):
            sql.append("d.year <= ?")
            params.append(int(f["year_to"]))
        if f.get("doc_id"):
            sql.append("d.id = ?")
            params.append(f["doc_id"])
        return (" AND " + " AND ".join(sql)) if sql else "", params

    # ---- 検索 ------------------------------------------------------------- #
    def search(self, q: str, filters: dict | None = None, limit: int = 50, offset: int = 0) -> dict:
        filters = filters or {}
        terms = self.parse_query(q)
        conn = self._conn()
        fsql, fparams = self._filters_sql(filters)
        if not terms:
            return {"query": q, "terms": [], "total": 0, "hits": [], "by_doc": []}

        fts_expr = self._fts_expr(terms)
        short_terms = [t for t in terms if len(t) < 3]
        like_sql = "".join(" AND p.text LIKE ? COLLATE NOCASE" for _ in short_terms)
        like_params = [f"%{t}%" for t in short_terms]

        if fts_expr:
            base_from = (
                "FROM pages_fts f JOIN pages p ON p.rowid = f.rowid JOIN documents d ON d.id = p.doc_id "
                "WHERE pages_fts MATCH ?" + like_sql + fsql
            )
            base_params = [fts_expr] + like_params + fparams
            order = "ORDER BY bm25(pages_fts)"
        else:  # 全部短い語 → LIKE のみ
            base_from = (
                "FROM pages p JOIN documents d ON d.id = p.doc_id WHERE 1=1" + like_sql + fsql
            )
            base_params = like_params + fparams
            order = "ORDER BY d.year DESC, p.page"

        total = conn.execute(f"SELECT COUNT(*) {base_from}", base_params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT p.rowid AS rid, p.doc_id, p.page, p.text AS text,
                       d.title_ja, d.title_en, d.organization, d.year, d.region, d.category, d.file, d.url, d.language
                {base_from} {order} LIMIT ? OFFSET ?""",
            base_params + [limit, offset],
        ).fetchall()
        by_doc = conn.execute(
            f"""SELECT d.id, COALESCE(d.title_ja, d.title_en) AS title, d.region, d.year, COUNT(*) AS n
                {base_from} GROUP BY d.id ORDER BY n DESC LIMIT 100""",
            base_params,
        ).fetchall()

        hits = []
        for r in rows:
            snip = self._make_snippet(r["text"], terms)
            hits.append(
                {
                    "doc_id": r["doc_id"],
                    "page": r["page"],
                    "snippet": self._highlight(snip, terms),
                    "title": r["title_ja"] or r["title_en"],
                    "title_en": r["title_en"],
                    "organization": r["organization"],
                    "year": r["year"],
                    "region": r["region"],
                    "category": r["category"],
                    "language": r["language"],
                    "pdf": f"/pdf/{urllib.parse.quote(r['file'])}#page={r['page']}" if r["file"] else None,
                    "source_url": r["url"],
                }
            )
        return {
            "query": q,
            "terms": terms,
            "total": total,
            "offset": offset,
            "limit": limit,
            "hits": hits,
            "by_doc": [dict(r) for r in by_doc],
        }

    @staticmethod
    def _make_snippet(text: str, terms: list[str], width: int = 260) -> str:
        """最初にヒットした語を中心に前後 width 文字を切り出す（できるだけ全語を含める）。"""
        low = text.lower()
        positions = sorted(p for p in (low.find(t.lower()) for t in terms) if p >= 0)
        if not positions:
            return text[:width] + ("…" if len(text) > width else "")
        first = positions[0]
        # 全ヒット語が width 内に収まるなら、その範囲を中心にする
        span_end = max(p for p in positions if p - first < width - 40) + 20
        center = (first + span_end) // 2
        start = max(0, center - width // 2)
        end = min(len(text), start + width)
        snippet = text[start:end].replace("\n", " ")
        return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")

    @staticmethod
    def _highlight(snippet: str, terms: list[str]) -> str:
        """[[…]] を <mark> に変換し、短語も <mark> で囲む。HTMLエスケープ済みで返す。"""
        import html

        s = html.escape(snippet)
        s = s.replace("[[", "\x00").replace("]]", "\x01")
        for t in sorted(terms, key=len, reverse=True):
            # snippet() が印を付けなかった語（短語・複数語の片方）も強調する
            s = re.sub(
                r"(?<!\x00)" + re.escape(html.escape(t)) + r"(?!\x01)",
                lambda m: "\x00" + m.group(0) + "\x01",
                s,
                flags=re.IGNORECASE,
            )
        return s.replace("\x00", "<mark>").replace("\x01", "</mark>")

    # ---- メタ情報 --------------------------------------------------------- #
    def facets(self) -> dict:
        conn = self._conn()
        out = {}
        for col in ("region", "category", "organization", "language", "year"):
            out[col] = [
                {"value": r[0], "count": r[1], "pages": r[2] or 0}
                for r in conn.execute(
                    f"SELECT {col}, COUNT(*), SUM(pages) FROM documents WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY {col}"
                )
            ]
        row = conn.execute("SELECT COUNT(*), SUM(file IS NOT NULL), SUM(pages) FROM documents").fetchone()
        meta = dict(conn.execute("SELECT key, value FROM meta"))
        out["summary"] = {"documents": row[0], "with_pdf": row[1] or 0, "pages": row[2] or 0, "built_at": meta.get("built_at")}
        return out

    def documents(self) -> list[dict]:
        conn = self._conn()
        docs = []
        for r in conn.execute("SELECT * FROM documents ORDER BY region, year DESC, title_ja"):
            d = dict(r)
            d["pdf"] = f"/pdf/{urllib.parse.quote(d['file'])}" if d.get("file") else None
            docs.append(d)
        return docs

    def page_text(self, doc_id: str, page: int) -> str | None:
        row = self._conn().execute("SELECT text FROM pages WHERE doc_id=? AND page=?", (doc_id, page)).fetchone()
        return row[0] if row else None


# --------------------------------------------------------------------------- #
# Claude Q&A（任意機能）
# --------------------------------------------------------------------------- #
def _qa_model() -> str:
    m = os.getenv("GUIDELINE_QA_MODEL")
    if m:
        return m
    try:  # 既存プロジェクトの設定を流用
        import yaml  # type: ignore

        cfg = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
        return cfg["claude"]["model"]
    except Exception:  # noqa: BLE001
        return "claude-sonnet-5"


QA_SYSTEM = """あなたは小児循環器領域の診療ガイドラインに基づいて質問に答えるアシスタントです。
必ず以下を守ってください。
- 回答は提供された【資料】の記載のみを根拠にし、資料にない内容は「資料内に記載なし」と明示する。
- 各主張の末尾に必ず出典を [資料番号] の形式で付ける（例: [2]）。
- 日本・米国・欧州で推奨が異なる場合は、その違いを明示する。
- 推奨クラス/エビデンスレベルが記載されていれば引用する。
- 最終的な診療判断は担当医が行うこと、原文を確認することを最後に一文で添える。
- 日本語で、簡潔かつ構造的に答える。"""


def answer_with_claude(engine: SearchEngine, question: str, filters: dict, k: int = 12) -> dict:
    try:
        import anthropic  # type: ignore
    except ImportError:
        return {"error": "anthropic パッケージが未インストールです。pip install anthropic を実行してください。"}
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("sk-ant-xxxx"):
        return {"error": "ANTHROPIC_API_KEY が .env に設定されていません（Q&A機能は任意です。全文検索は利用できます）。"}

    # 質問から検索語を作る（Claudeに検索語を作らせるより、まず素朴に検索）
    terms = [t for t in re.split(r"[\s、。，,.？?（）()「」]+", question) if len(t) >= 2][:6]
    res = engine.search(" ".join(terms), filters, limit=k) if terms else {"hits": []}
    if not res["hits"]:
        # 語を減らして再試行
        for n in range(len(terms) - 1, 0, -1):
            res = engine.search(" ".join(terms[:n]), filters, limit=k)
            if res["hits"]:
                break
    if not res["hits"]:
        return {"error": "関連するガイドライン本文が見つかりませんでした。検索語を変えてお試しください。", "hits": []}

    contexts = []
    for i, h in enumerate(res["hits"][:k], 1):
        text = engine.page_text(h["doc_id"], h["page"]) or ""
        contexts.append(
            f"【資料{i}】{h['title']}（{h['organization']}, {h['year']}, {h['region']}）p.{h['page']}\n{text[:3500]}"
        )
    prompt = (
        "以下の【資料】を根拠に質問に答えてください。\n\n" + "\n\n".join(contexts) + f"\n\n【質問】{question}"
    )
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=_qa_model(),
        max_tokens=2000,
        system=QA_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = "".join(getattr(b, "text", "") for b in msg.content)
    return {"answer": answer, "sources": res["hits"][:k], "model": _qa_model()}


# --------------------------------------------------------------------------- #
# HTTP サーバー
# --------------------------------------------------------------------------- #
class Handler(SimpleHTTPRequestHandler):
    engine: SearchEngine = None  # type: ignore  # main() で注入

    def log_message(self, fmt, *args):  # 静かに
        if os.getenv("GUIDELINE_APP_DEBUG"):
            super().log_message(fmt, *args)

    # ---- helpers ---------------------------------------------------------- #
    def _json(self, obj, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type: str | None = None):
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _filters_from_qs(qs: dict) -> dict:
        f = {}
        for col in ("region", "category", "organization", "language"):
            vals = [v for v in qs.get(col, []) if v]
            if vals:
                f[col] = vals
        for k in ("year_from", "year_to", "doc_id"):
            if qs.get(k) and qs[k][0]:
                f[k] = qs[k][0]
        return f

    # ---- routes ----------------------------------------------------------- #
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                return self._file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            if path == "/api/search":
                q = qs.get("q", [""])[0]
                limit = min(int(qs.get("limit", ["50"])[0]), 200)
                offset = int(qs.get("offset", ["0"])[0])
                return self._json(self.engine.search(q, self._filters_from_qs(qs), limit, offset))
            if path == "/api/facets":
                return self._json(self.engine.facets())
            if path == "/api/documents":
                return self._json(self.engine.documents())
            if path == "/api/page":
                text = self.engine.page_text(qs.get("doc_id", [""])[0], int(qs.get("page", ["0"])[0]))
                return self._json({"text": text})
            if path.startswith("/pdf/"):
                name = Path(path[len("/pdf/") :]).name  # ディレクトリトラバーサル防止
                return self._file(PDF_DIR / name, "application/pdf")
            if path.startswith("/static/"):
                name = Path(path[len("/static/") :]).name
                return self._file(STATIC_DIR / name)
            self.send_error(HTTPStatus.NOT_FOUND)
        except FileNotFoundError as exc:
            self._json({"error": str(exc)}, 503)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "invalid json"}, 400)
        try:
            if parsed.path == "/api/ask":
                q = (payload.get("question") or "").strip()
                if not q:
                    return self._json({"error": "question が空です"}, 400)
                return self._json(answer_with_claude(self.engine, q, payload.get("filters") or {}))
            self.send_error(HTTPStatus.NOT_FOUND)
        except FileNotFoundError as exc:
            self._json({"error": str(exc)}, 503)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main(argv: list[str] | None = None) -> int:
    global PDF_DIR
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--pdf-dir", type=Path, default=PDF_DIR, help="PDF保存フォルダ（既定: guidelines/pdf）")
    ap.add_argument("--open", action="store_true", help="起動後にブラウザを開く")
    args = ap.parse_args(argv)

    PDF_DIR = args.pdf_dir
    Handler.engine = SearchEngine(args.db)
    if not args.db.exists():
        print(f"⚠ {args.db} がありません。先に次を実行してください:")
        print("    python guidelines/download_guidelines.py")
        print("    python guidelines/build_index.py")
        print("  （サーバーは起動しますが検索結果は空になります）")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print("========================================")
    print(" 小児先天性心疾患ガイドライン 検索アプリ")
    print(f" {url}   （終了: Ctrl+C）")
    print("========================================")
    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します")
    return 0


if __name__ == "__main__":
    sys.exit(main())
