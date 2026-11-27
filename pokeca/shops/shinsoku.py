"""シンソク 郵送買取価格一覧（https://shinsoku-tcg.com/yuso-kaitori）。

一覧ページに埋め込まれている商品データ（1ページ40件）を読む。
robots.txt は全ページ許可（2026-11 確認）。価格は「状態S」の郵送買取価格。
"""

from __future__ import annotations

import json
import re

SHOP = "シンソク"
URL = "https://shinsoku-tcg.com/yuso-kaitori"
RECORD_RE = re.compile(r'\{"id":"[A-Z0-9]+","item_id":.*?"buy_boost":(?:true|false)\}')
TOTAL_RE = re.compile(r"([\d,]+)\s*(?:<!-- -->)?\s*件")
PER_PAGE = 40
NUMBER_RE = re.compile(r"^[0-9A-Za-z\-]{1,12}/[0-9A-Za-z\-]{1,12}$")   # 例: 096/071, 020/M-P


def parse(html: str) -> list[dict]:
    """一覧ページ1枚から買取行を取り出す。"""
    text = html.replace('\\"', '"')
    rows, seen = [], set()
    for m in RECORD_RE.finditer(text):
        try:
            rec = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if rec["item_id"] in seen or not rec.get("is_postal_buy_target"):
            continue
        seen.add(rec["item_id"])
        price = rec.get("postal_purchase_price_s")
        number = rec.get("modelno")
        if not isinstance(price, (int, float)) or rec.get("type") not in ("PSA", "NORMAL"):
            continue  # BOX・パックなどカード以外は対象外
        grade = next((t["label"] for t in rec.get("tags", []) if t.get("category_label") == "鑑定品"), "")
        if rec["type"] == "PSA" and not grade:
            continue  # グレード不明の鑑定品は使わない
        if not isinstance(number, str) or not NUMBER_RE.match(number.strip()):
            continue  # 「PSA10保証AR以上」のようなまとめ買取枠は個別カードではない
        rows.append({
            "shop": SHOP,
            "number": number.strip(),
            "name": f'{rec["name"]} {rec.get("rarity") or ""}'.strip() if rec["type"] == "NORMAL" else rec["name"],
            "grade": grade,
            "price": price,
            "item_id": rec["item_id"],
        })
    return rows


def total_pages(html: str) -> int:
    m = TOTAL_RE.search(re.sub(r"<[^>]+>", " ", html))
    return -(-int(m.group(1).replace(",", "")) // PER_PAGE) if m else 1


def fetch(max_pages: int | None = None):
    from . import get

    first = get(URL)
    pages = total_pages(first)
    if max_pages:
        pages = min(pages, max_pages)
    yield from parse(first)
    for page in range(2, pages + 1):
        yield from parse(get(URL, page=page))
