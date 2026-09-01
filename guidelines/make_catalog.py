#!/usr/bin/env python3
"""カタログ(JSON)から配布物を生成する。

- catalog/urls.txt      : wget / curl 用のURL一覧（1行1URL）
- catalog/guidelines.csv: Excel等で開ける一覧
- index.html            : ブラウザで開ける一覧ページ（全リンク + 一括DLリンク）

使い方:
    python guidelines/make_catalog.py
"""

from __future__ import annotations

import csv
import html
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "catalog" / "guidelines.json"
RELEASE_BASE = "https://github.com/n0619y/toto/releases/download/guidelines-latest"

REGION_LABEL = {"JP": "日本", "US": "米国", "EU": "欧州"}
CATEGORY_ORDER = [
    "総合/ACHD", "診断・画像", "胎児", "カテーテル治療", "外科治療", "術後管理・遠隔期", "不整脈",
    "心不全", "肺高血圧", "感染性心内膜炎", "川崎病", "薬物療法", "妊娠・出産", "学校・スポーツ",
    "遺伝・発達", "その他",
]


def load_catalog(path: Path = CATALOG_PATH) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["guidelines"] if isinstance(data, dict) else data


def write_urls(entries: list[dict]) -> None:
    lines = []
    for e in entries:
        if e.get("url"):
            lines.append(e["url"])
    (HERE / "catalog" / "urls.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(entries: list[dict]) -> None:
    cols = ["id", "region", "year", "organization", "category", "title_ja", "title_en", "language", "url", "landing_url", "doi", "notes"]
    with (HERE / "catalog" / "guidelines.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            w.writerow(e)


def write_html(entries: list[dict]) -> None:
    h = html.escape
    by_region = Counter(e.get("region") for e in entries)
    rows = []
    for region in ("JP", "US", "EU"):
        es = [e for e in entries if e.get("region") == region]
        if not es:
            continue
        rows.append(f'<h2 id="{region}">{REGION_LABEL.get(region, region)}（{len(es)}件）</h2>')
        es.sort(key=lambda e: (CATEGORY_ORDER.index(e.get("category")) if e.get("category") in CATEGORY_ORDER else 99, -(e.get("year") or 0)))
        rows.append("<table><tr><th>年</th><th>カテゴリ</th><th>ガイドライン</th><th>発行</th><th>リンク</th></tr>")
        for e in es:
            links = []
            if e.get("url"):
                links.append(f'<a href="{h(e["url"])}" target="_blank" rel="noopener">PDF</a>')
            if e.get("landing_url") and e.get("landing_url") != e.get("url"):
                links.append(f'<a href="{h(e["landing_url"])}" target="_blank" rel="noopener">紹介頁</a>')
            if e.get("doi"):
                links.append(f'<a href="https://doi.org/{h(e["doi"])}" target="_blank" rel="noopener">DOI</a>')
            title = h(e.get("title_ja") or e.get("title_en") or "")
            sub = ""
            if e.get("title_en") and e.get("title_en") != e.get("title_ja"):
                sub = f'<div class="sub">{h(e["title_en"])}</div>'
            note = f'<div class="sub">{h(e["notes"])}</div>' if e.get("notes") else ""
            rows.append(
                f"<tr><td>{e.get('year') or ''}</td><td>{h(e.get('category') or '')}</td>"
                f"<td>{title}{sub}{note}</td><td>{h(e.get('organization') or '')}</td><td>{' / '.join(links)}</td></tr>"
            )
        rows.append("</table>")

    page = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>小児先天性心疾患ガイドライン集（日本・米国・欧州）</title>
<style>
body{{font:14px/1.6 -apple-system,"Hiragino Sans","Noto Sans JP",Segoe UI,sans-serif;max-width:1200px;margin:0 auto;padding:24px;color:#1c2330}}
h1{{font-size:22px}} h2{{font-size:18px;margin-top:32px;border-bottom:2px solid #e2e6ee;padding-bottom:4px}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid #e2e6ee;padding:6px 8px;text-align:left;vertical-align:top;font-size:13px}}
th{{background:#f6f7f9;white-space:nowrap}} .sub{{color:#62708a;font-size:12px}}
.box{{background:#eef5ff;border:1px solid #bcd4f5;border-radius:10px;padding:14px 18px;margin:16px 0}}
.box code{{background:#fff;padding:1px 5px;border-radius:4px}}
a{{color:#0f6fd6;text-decoration:none}} a:hover{{text-decoration:underline}}
.nav a{{margin-right:14px}}
</style></head><body>
<h1>🫀 小児先天性心疾患ガイドライン集</h1>
<p>解剖・病態・診断・内科/外科治療・カテーテル治療・合併症・術後管理・外来診療（移行期医療、学校・スポーツ、妊娠）に関する
日本・米国・欧州のガイドライン／学会ステートメント <b>{len(entries)}件</b>
（日本 {by_region.get('JP',0)} / 米国 {by_region.get('US',0)} / 欧州 {by_region.get('EU',0)}）。</p>

<div class="box">
<b>📦 一括ダウンロード</b>
<ul>
<li>全PDF ZIP（GitHub Actions が自動取得・毎回最新）: <a href="{RELEASE_BASE}/chd-guidelines-pdf.zip">{RELEASE_BASE}/chd-guidelines-pdf.zip</a></li>
<li>全文検索DB: <a href="{RELEASE_BASE}/guidelines.db">{RELEASE_BASE}/guidelines.db</a></li>
<li>自分のPCで取得する場合: <code>python guidelines/download_guidelines.py</code>（または <code>wget -i guidelines/catalog/urls.txt</code>）</li>
</ul>
<b>🔍 検索アプリ</b>: <code>python guidelines/build_index.py</code> → <code>python guidelines/app.py --open</code>
</div>
<p class="nav"><a href="#JP">日本</a><a href="#US">米国</a><a href="#EU">欧州</a></p>
{''.join(rows)}
<p class="sub">各PDFの著作権は発行団体に帰属します。本一覧はリンク集であり、個人の学習・診療参照目的での利用を想定しています。</p>
</body></html>"""
    (HERE / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    entries = load_catalog()
    write_urls(entries)
    write_csv(entries)
    write_html(entries)
    by_region = Counter(e.get("region") for e in entries)
    print(f"生成完了: {len(entries)} 件  {dict(by_region)}")
    print(f"  {HERE / 'catalog' / 'urls.txt'}\n  {HERE / 'catalog' / 'guidelines.csv'}\n  {HERE / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
