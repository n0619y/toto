#!/usr/bin/env python3
"""小児先天性心疾患ガイドライン 一括ダウンローダ。

catalog/guidelines.json に登録された全ガイドラインPDFを pdf/ フォルダへ保存します。
標準ライブラリのみで動作します（追加インストール不要）。

使い方:
    python guidelines/download_guidelines.py                 # 全件ダウンロード
    python guidelines/download_guidelines.py --region JP     # 日本のみ
    python guidelines/download_guidelines.py --retry-failed  # 前回失敗分のみ再試行
    python guidelines/download_guidelines.py --list          # 一覧表示のみ

ダウンロード結果は pdf/_download_report.json と pdf/_download_report.md に記録されます。
publisher 側の bot 対策で 403 になったものは、レポート内の URL をブラウザで開いて
手動保存してください（保存先ファイル名もレポートに記載しています）。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "catalog" / "guidelines.json"
PDF_DIR = HERE / "pdf"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/pdf,application/octet-stream,text/html;q=0.8,*/*;q=0.5",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}
TIMEOUT = 90
MAX_ATTEMPTS = 4


# --------------------------------------------------------------------------- #
# ユーティリティ
# --------------------------------------------------------------------------- #
def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["guidelines"] if isinstance(data, dict) else data


def safe_filename(entry: dict) -> str:
    """<region>_<year>_<id>.pdf 形式の安全なファイル名を返す。"""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", entry["id"]).strip("-")
    return f"{entry.get('region', 'XX')}_{entry.get('year', 0)}_{slug}.pdf"


def candidate_urls(entry: dict) -> list[str]:
    """直接PDF URL → DOI → ランディングページ の順で試す候補一覧。"""
    urls: list[str] = []
    for key in ("url", "pdf_url_alt", "landing_url"):
        u = entry.get(key)
        if u and u not in urls:
            urls.append(u)
    doi = entry.get("doi")
    if doi:
        d = f"https://doi.org/{doi}" if not doi.startswith("http") else doi
        if d not in urls:
            urls.append(d)
    return urls


def _fetch(url: str) -> tuple[bytes, str, str]:
    """URLを取得し (body, content_type, final_url) を返す。"""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        return body, ctype, resp.geturl()


_PDF_LINK_RE = re.compile(
    r"""(?:href|content|src)=["']([^"']+?\.pdf(?:\?[^"']*)?|[^"']*?/doi/pdf/[^"']+|[^"']*?/pdf/[^"']+?)["']""",
    re.IGNORECASE,
)
_CITATION_PDF_RE = re.compile(
    r"""<meta[^>]+name=["']citation_pdf_url["'][^>]+content=["']([^"']+)["']""", re.IGNORECASE
)


def find_pdf_links_in_html(html: str, base_url: str) -> list[str]:
    """ランディングページHTMLからPDFらしきリンクを抽出する。"""
    found: list[str] = []
    for m in _CITATION_PDF_RE.finditer(html):
        found.append(urllib.parse.urljoin(base_url, m.group(1)))
    for m in _PDF_LINK_RE.finditer(html):
        found.append(urllib.parse.urljoin(base_url, m.group(1)))
    # 重複除去（順序維持）
    seen: set[str] = set()
    out = []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:8]


def download_one(entry: dict, dest_dir: Path, force: bool = False) -> dict:
    """1件ダウンロード。結果 dict を返す。"""
    fname = safe_filename(entry)
    dest = dest_dir / fname
    result = {
        "id": entry["id"],
        "title": entry.get("title_ja") or entry.get("title_en"),
        "file": fname,
        "ok": False,
        "bytes": 0,
        "source_url": None,
        "error": None,
        "tried": [],
    }
    if dest.exists() and dest.stat().st_size > 1024 and not force:
        result.update(ok=True, bytes=dest.stat().st_size, source_url="(cached)")
        return result

    queue = candidate_urls(entry)
    visited: set[str] = set()
    last_error = None
    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                body, ctype, final_url = _fetch(url)
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code} ({url})"
                result["tried"].append(last_error)
                if exc.code in (401, 403, 404, 410):
                    break  # このURLは諦めて次候補へ
                time.sleep(2**attempt)
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc} ({url})"
                result["tried"].append(last_error)
                time.sleep(2**attempt)
                continue

            if body[:5] == b"%PDF-":
                dest.write_bytes(body)
                result.update(ok=True, bytes=len(body), source_url=final_url)
                return result

            # HTMLが返ってきた → PDFリンクを探して候補に追加
            if "html" in ctype.lower() or body[:1] == b"<":
                try:
                    html = body.decode("utf-8", errors="ignore")
                except Exception:  # noqa: BLE001
                    html = ""
                links = [u for u in find_pdf_links_in_html(html, final_url) if u not in visited]
                if links:
                    queue = links + queue
                last_error = f"HTMLが返却（PDFリンク {len(links)} 件を追試） ({url})"
                result["tried"].append(last_error)
                break
            last_error = f"PDF以外のデータ ({ctype}) ({url})"
            result["tried"].append(last_error)
            break

    result["error"] = last_error or "候補URLなし"
    return result


def write_report(results: list[dict], dest_dir: Path, catalog: list[dict]) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    by_id = {e["id"]: e for e in catalog}
    ok = [r for r in results if r["ok"]]
    ng = [r for r in results if not r["ok"]]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "succeeded": len(ok),
        "failed": len(ng),
        "results": results,
    }
    (dest_dir / "_download_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# ガイドラインPDF ダウンロード結果",
        "",
        f"- 実行日時: {report['generated_at']}",
        f"- 成功: **{len(ok)} / {len(results)}**",
        f"- 失敗: {len(ng)}",
        "",
    ]
    if ng:
        lines += [
            "## 手動ダウンロードが必要なもの",
            "",
            "以下はサイト側の自動取得制限などで保存できませんでした。",
            "リンクをブラウザで開いてPDFを保存し、**指定のファイル名** で `guidelines/pdf/` に置いてください。",
            "",
            "| # | ガイドライン | 開くURL | 保存ファイル名 | エラー |",
            "|---|---|---|---|---|",
        ]
        for i, r in enumerate(ng, 1):
            e = by_id.get(r["id"], {})
            links = " / ".join(f"[{i2+1}]({u})" for i2, u in enumerate(candidate_urls(e)))
            lines.append(
                f"| {i} | {r['title']} | {links} | `{r['file']}` | {r['error']} |"
            )
        lines.append("")
    lines += ["## 成功一覧", "", "| ガイドライン | ファイル | サイズ |", "|---|---|---|"]
    for r in ok:
        lines.append(f"| {r['title']} | `{r['file']}` | {r['bytes']/1024/1024:.1f} MB |")
    (dest_dir / "_download_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    ap.add_argument("--dest", type=Path, default=PDF_DIR)
    ap.add_argument("--region", choices=["JP", "US", "EU"], action="append", help="地域で絞り込み（複数指定可）")
    ap.add_argument("--id", action="append", help="IDで絞り込み（複数指定可）")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="既存ファイルも再取得")
    ap.add_argument("--retry-failed", action="store_true", help="前回レポートで失敗したものだけ再試行")
    ap.add_argument("--list", action="store_true", help="対象一覧を表示して終了")
    args = ap.parse_args(argv)

    catalog = load_catalog(args.catalog)
    targets = catalog
    if args.region:
        targets = [e for e in targets if e.get("region") in args.region]
    if args.id:
        targets = [e for e in targets if e["id"] in set(args.id)]
    if args.retry_failed:
        rep = args.dest / "_download_report.json"
        if rep.exists():
            failed_ids = {r["id"] for r in json.loads(rep.read_text(encoding="utf-8"))["results"] if not r["ok"]}
            targets = [e for e in targets if e["id"] in failed_ids]

    if args.list:
        for e in targets:
            print(f"[{e.get('region')}] {e.get('year')}  {e.get('title_ja') or e.get('title_en')}\n      {e.get('url')}")
        print(f"\n合計 {len(targets)} 件")
        return 0

    args.dest.mkdir(parents=True, exist_ok=True)
    print(f"▶ {len(targets)} 件をダウンロードします → {args.dest}")
    results: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download_one, e, args.dest, args.force): e for e in targets}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            mark = "✅" if r["ok"] else "❌"
            size = f"{r['bytes']/1024/1024:.1f}MB" if r["ok"] else r["error"]
            print(f"{mark} [{i}/{len(targets)}] {r['title'][:60]}  {size}")

    # 前回レポートとマージ（--retry-failed / 絞り込み実行時に他の結果を失わないため）
    rep_path = args.dest / "_download_report.json"
    merged: dict[str, dict] = {}
    if rep_path.exists():
        try:
            for r in json.loads(rep_path.read_text(encoding="utf-8"))["results"]:
                merged[r["id"]] = r
        except Exception:  # noqa: BLE001
            pass
    for r in results:
        merged[r["id"]] = r
    order = {e["id"]: i for i, e in enumerate(catalog)}
    all_results = sorted(merged.values(), key=lambda r: order.get(r["id"], 9999))
    write_report(all_results, args.dest, catalog)

    ok = sum(1 for r in results if r["ok"])
    print("\n========================================")
    print(f"完了: 成功 {ok} / {len(results)}   失敗 {len(results)-ok}")
    print(f"レポート: {args.dest / '_download_report.md'}")
    if ok < len(results):
        print("失敗分はレポートのURLをブラウザで開き、指定ファイル名で保存してください。")
    print("========================================")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
