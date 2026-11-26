"""カードショップ買取表の取得。

対応形式: html_table（CSSセレクタ） / image（Claude画像認識） / csv（URL or ローカル）
※ 取得前に robots.txt を確認し、ショップの利用規約に従うこと。
"""
from __future__ import annotations

import base64
import csv
import io
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from ..analysis import llm
from ..analysis.schemas import BuylistExtraction
from ..config import ROOT, get_logger, settings
from .normalize import normalize_row

log = get_logger()
UA = "pokeca-trends/0.1 (buylist price tracker)"
_robots: dict[str, RobotFileParser] = {}

VISION_SYSTEM = """あなたはカードショップの買取表画像を正確に書き起こすデータ入力担当です。
画像内の表から、ポケモンカードの カード名・型番・レアリティ・買取価格・状態条件 を1行ずつ抜き出してください。
- 読み取れない行は推測せず省略する
- 価格は円の整数にする（「1.2万」は12000）
- ポケモンカード以外（サプライ、他TCG）は除外する"""


def allowed(url: str) -> bool:
    if not settings()["market"].get("respect_robots_txt", True):
        return True
    base = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if base not in _robots:
        rp = RobotFileParser(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)


def fetch(url: str) -> requests.Response:
    if not allowed(url):
        raise PermissionError(f"robots.txt により取得が許可されていません: {url}")
    time.sleep(settings()["market"].get("request_interval_sec", 3))
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r


def from_html(shop: dict) -> list[dict]:
    sel = shop["selectors"]
    soup = BeautifulSoup(fetch(shop["url"]).text, "html.parser")
    rows = []
    for tr in soup.select(sel["row"]):
        def cell(key):
            css = sel.get(key)
            el = tr.select_one(css) if css else None
            return el.get_text(" ", strip=True) if el else ""
        rows.append({k: cell(k) for k in ("card_name", "card_number", "rarity", "price", "condition")})
    return rows


def from_images(shop: dict) -> list[dict]:
    if not llm.available():
        log.warning("[%s] 画像の買取表は ANTHROPIC_API_KEY が必要なためスキップ", shop["name"])
        return []
    urls = list(shop.get("image_urls") or [])
    if shop.get("page_url") and shop.get("image_selector"):
        soup = BeautifulSoup(fetch(shop["page_url"]).text, "html.parser")
        urls += [urljoin(shop["page_url"], img.get("src")) for img in soup.select(shop["image_selector"]) if img.get("src")]
    rows = []
    for url in urls:
        r = fetch(url)
        media = r.headers.get("content-type", "image/jpeg").split(";")[0]
        if media not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            media = "image/jpeg"
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media,
                                         "data": base64.standard_b64encode(r.content).decode()}},
            {"type": "text", "text": "この買取表の全行を書き起こしてください。"},
        ]
        result = llm.parse(BuylistExtraction, system=VISION_SYSTEM, content=content, effort="medium")
        rows += [x.model_dump() for x in result.rows]
        log.info("[%s] 画像 %s: %d 行", shop["name"], url.rsplit("/", 1)[-1], len(result.rows))
    return rows


def from_csv_text(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def from_csv(shop: dict) -> list[dict]:
    if shop.get("url"):
        r = fetch(shop["url"])
        r.encoding = r.apparent_encoding
        return from_csv_text(r.text)
    return from_csv_text((ROOT / shop["path"]).read_text(encoding="utf-8-sig"))


HANDLERS = {"html_table": from_html, "image": from_images, "csv": from_csv}


def collect_shop(shop: dict) -> list[dict]:
    raw = HANDLERS[shop["type"]](shop)
    rows, seen = [], set()
    for r in raw:
        n = normalize_row(r)
        if n and (n["card_key"], n["condition"]) not in seen:
            seen.add((n["card_key"], n["condition"]))
            rows.append(n)
    return rows


def manual_csvs(date: str) -> dict[str, list[dict]]:
    """data/buylists/<ショップ名>_<YYYY-MM-DD>.csv または <ショップ名>.csv を取り込む。"""
    d = ROOT / settings()["market"]["manual_csv_dir"]
    out: dict[str, list[dict]] = {}
    for f in sorted(Path(d).glob("*.csv")):
        stem = f.stem
        if "_" in stem:
            shop, fdate = stem.rsplit("_", 1)
            if fdate != date:
                continue
        else:
            shop = stem
        rows = [n for n in (normalize_row(r) for r in from_csv_text(f.read_text(encoding="utf-8-sig"))) if n]
        out[shop] = rows
    return out
