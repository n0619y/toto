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
import os
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
    """直接PDF URL → 代替URL → ランディングページ → DOI の順で試す候補一覧（表示用）。"""
    urls: list[str] = []
    for u in direct_urls(entry) + landing_urls(entry):
        if u not in urls:
            urls.append(u)
    return urls


def direct_urls(entry: dict) -> list[str]:
    urls: list[str] = []
    for key in ("url", "pdf_url_alt"):
        u = entry.get(key)
        if u and u not in urls:
            urls.append(u)
    for u in entry.get("alt_urls") or []:
        if u and u not in urls:
            urls.append(u)
    return urls


def landing_urls(entry: dict) -> list[str]:
    urls: list[str] = []
    u = entry.get("landing_url")
    if u:
        urls.append(u)
    doi = normalize_doi(entry.get("doi"))
    if doi:
        d = f"https://doi.org/{doi}"
        if d not in urls:
            urls.append(d)
    return urls


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
    return doi or None


# --------------------------------------------------------------------------- #
# オープンアクセス版の探索（出版社サイトが bot をブロックする場合の迂回路）
# --------------------------------------------------------------------------- #
def europepmc_pdf_urls(doi: str) -> list[str]:
    """Europe PMC REST API で DOI → PMCID / 全文PDF URL を引く（API キー不要）。"""
    q = urllib.parse.quote(f'DOI:"{doi}"')
    api = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={q}&format=json&resultType=core&pageSize=3"
    )
    out: list[str] = []
    try:
        body, _, _ = _fetch(api)
        data = json.loads(body.decode("utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return out
    for r in data.get("resultList", {}).get("result", []):
        for ft in r.get("fullTextUrlList", {}).get("fullTextUrl", []):
            if ft.get("documentStyle") == "pdf" and ft.get("url"):
                out.append(ft["url"])
        pmcid = r.get("pmcid")
        if pmcid:
            out.append(f"https://europepmc.org/articles/{pmcid}?pdf=render")
            out.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/")
    return out


def unpaywall_pdf_urls(doi: str) -> list[str]:
    """Unpaywall API で OA 版 PDF を探す。環境変数 UNPAYWALL_EMAIL が設定されている時のみ使用。"""
    email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
    if not email:
        return []
    api = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='')}?email={urllib.parse.quote(email)}"
    out: list[str] = []
    try:
        body, _, _ = _fetch(api)
        data = json.loads(body.decode("utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return out
    locs = []
    if data.get("best_oa_location"):
        locs.append(data["best_oa_location"])
    locs += data.get("oa_locations") or []
    for loc in locs:
        for key in ("url_for_pdf", "url"):
            u = loc.get(key)
            if u and u not in out:
                out.append(u)
    return out


_AWMF_RE = re.compile(r"register\.awmf\.org/de/leitlinien/detail/(\d{3}-\d{3}[A-Za-z]*)")


def awmf_pdf_urls(url: str) -> list[str]:
    """AWMF レジスタ（ドイツ）の SPA ランディングページから PDF URL を解決する。"""
    m = _AWMF_RE.search(url or "")
    if not m:
        return []
    reg = m.group(1)
    out: list[str] = []
    # 公開 JSON API（SPA が内部で使用しているもの）を順に試す
    for api in (
        f"https://register.awmf.org/api/v1/guidelines/{reg}",
        f"https://register.awmf.org/api/guidelines/{reg}",
        f"https://leitlinien-api.awmf.org/v1/guidelines/{reg}",
    ):
        try:
            body, ctype, _ = _fetch(api)
        except Exception:  # noqa: BLE001
            continue
        text = body.decode("utf-8", errors="ignore")
        for link in re.findall(r"https?://[^\s\"'<>]+?\.pdf", text):
            if link not in out:
                out.append(link)
        for rel in re.findall(r"\"(/?assets/guidelines/[^\"]+?\.pdf)\"", text):
            link = urllib.parse.urljoin("https://register.awmf.org/", rel)
            if link not in out:
                out.append(link)
        if out:
            break
    return out


def resolver_urls(entry: dict) -> list[str]:
    """DOI / ランディングURLから OA 版 PDF 候補を集める。"""
    out: list[str] = []
    doi = normalize_doi(entry.get("doi"))
    if doi:
        for u in europepmc_pdf_urls(doi) + unpaywall_pdf_urls(doi):
            if u not in out:
                out.append(u)
    for u in (entry.get("landing_url"), entry.get("url")):
        for link in awmf_pdf_urls(u or ""):
            if link not in out:
                out.append(link)
    return out


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

    visited: set[str] = set()
    last_error = None

    def try_queue(queue: list[str]) -> bool:
        nonlocal last_error
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
                    if exc.code in (401, 403, 404, 410, 500):
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
                    return True

                # HTMLが返ってきた → PDFリンクを探して候補に追加
                if "html" in ctype.lower() or body.lstrip()[:1] == b"<":
                    html = body.decode("utf-8", errors="ignore")
                    links = [u for u in find_pdf_links_in_html(html, final_url) if u not in visited]
                    if links:
                        queue[:0] = links
                    last_error = f"HTMLが返却（PDFリンク {len(links)} 件を追試） ({url})"
                    result["tried"].append(last_error)
                    break
                last_error = f"PDF以外のデータ ({ctype}) ({url})"
                result["tried"].append(last_error)
                break
        return False

    # 第1段階: 直接PDF URL・代替URL
    if try_queue(direct_urls(entry)):
        return result
    # 第2段階: Europe PMC / Unpaywall / AWMF API で OA 版を探す
    if try_queue(resolver_urls(entry)):
        return result
    # 第3段階: ランディングページ・doi.org（HTML内のPDFリンクを追跡）
    if try_queue(landing_urls(entry)):
        return result

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


def probe(urls: list[str]) -> int:
    """診断: 各URLの HTTP 状態・Content-Type・最終URL・PDFリンク候補・API手掛かりを表示する。"""
    for url in urls:
        print("=" * 100)
        print("URL:", url)
        if url.startswith("doi:"):
            doi = url[4:]
            print("  EuropePMC:", europepmc_pdf_urls(doi))
            print("  Unpaywall:", unpaywall_pdf_urls(doi))
            continue
        try:
            body, ctype, final_url = _fetch(url)
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code}  final={exc.geturl()}")
            head = exc.read()[:400].decode("utf-8", errors="ignore")
            print("  body:", head.replace("\n", " ")[:400])
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {type(exc).__name__}: {exc}")
            continue
        print(f"  status=200 ctype={ctype} bytes={len(body)} final={final_url}")
        if body[:5] == b"%PDF-":
            print("  -> PDF OK")
            continue
        text = body.decode("utf-8", errors="ignore")
        print("  pdf links:", find_pdf_links_in_html(text, final_url)[:8])
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text)[:6]
        print("  scripts:", scripts)
        hints = set(re.findall(r'["\'](https?://[^"\']*api[^"\']*)["\']', text))
        hints |= set(re.findall(r'["\'](/api/[^"\']*)["\']', text))
        print("  api hints (html):", sorted(hints)[:10])
        for sc in scripts[:3]:
            try:
                js, _, _ = _fetch(urllib.parse.urljoin(final_url, sc))
                jt = js.decode("utf-8", errors="ignore")
                h2 = set(re.findall(r'["\'](https?://[^"\'\s]{0,120}api[^"\'\s]{0,120})["\']', jt))
                h2 |= set(re.findall(r'["\'](/api/[^"\'\s]{0,120})["\']', jt))
                h2 |= set(re.findall(r'(assets/guidelines[^"\'\s]{0,80})', jt))
                print(f"  api hints ({sc[:60]}):", sorted(h2)[:15])
            except Exception as exc:  # noqa: BLE001
                print(f"  script fetch failed {sc[:60]}: {exc}")
        print("  body head:", re.sub(r"\s+", " ", text[:600]))
    return 0


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
    ap.add_argument("--probe", nargs="+", metavar="URL", help="URLの応答を調査して表示（診断用）")
    args = ap.parse_args(argv)

    if args.probe:
        return probe(args.probe)

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
