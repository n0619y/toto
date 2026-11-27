"""トレカラウンジ かんたん郵送買取（https://kaitori.toreca-lounge.com/products/pokemon/single）。

ポケモンカードのシングル一覧（1ページ約100件）の HTML を読む。
robots.txt は /sign-in/ /sign-up/ /member/ /purchase/ だけ不可で、/products/ は許可（2026-11 確認）。
グレードを指定しない一覧では「素体, PSA10」のように複数グレードをまとめた行の価格が「～¥79,000」と
上限表示になるため、グレードごと（?grade=PSA10 など）に取得して、そのグレードの価格を読む。
"""

from __future__ import annotations

import html as htmllib
import re

SHOP = "トレカラウンジ"
URL = "https://kaitori.toreca-lounge.com/products/pokemon/single"
GRADES = {"PSA10": "PSA10", "PSA9": "PSA9", "素体": ""}   # サイトの絞り込み値 -> 保存するグレード
PER_PAGE = 100
MAX_PAGES = 100
CARD_RE = re.compile(r'<a href="/product/([^"]+)">(.*?)</a>', re.S)
NAME_RE = re.compile(r'<img alt="([^"]*)"')
NUMBER_RE = re.compile(r"^[0-9A-Za-z\-]{1,12}/[0-9A-Za-z\-]{1,12}$")   # 例: 096/071, 020/M-P
TOTAL_RE = re.compile(r"全\s*([\d,]+)\s*件")


def _text(fragment: str) -> str:
    return htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse(html: str) -> list[dict]:
    """一覧ページ1枚から買取行を取り出す。"""
    rows = []
    for item_id, body in CARD_RE.findall(html):
        text = _text(body)
        m = re.search(r"型番:\s*(\S+)\s+レアリティ/種別:\s*(\S+)\s*/\s*(.*?)\s*(?:収録弾:.*?)?買取価格:\s*(～?)\s*¥([\d,]+)", text)
        name = NAME_RE.search(body)
        if not m or not name:
            continue
        number, rarity, grade, upto, price = m.groups()
        if upto or grade not in GRADES:
            continue  # 複数グレードをまとめた行（価格が上限表示）は、どのグレードの価格か決まらない
        if not NUMBER_RE.match(number):
            continue  # 「おくるだけ買取」のような個別カードでない枠
        rows.append({
            "shop": SHOP,
            "number": number,
            "name": htmllib.unescape(name.group(1)).strip(),
            "grade": GRADES[grade],
            "price": int(price.replace(",", "")),
            "item_id": item_id,
        })
    return rows


def total_pages(html: str) -> int:
    m = TOTAL_RE.search(_text(html))
    return -(-int(m.group(1).replace(",", "")) // PER_PAGE) if m else 1


def fetch(max_pages: int | None = None):
    from . import get

    budget = max_pages or MAX_PAGES
    for grade in GRADES:
        page, pages = 1, 1
        while page <= pages and budget > 0:
            html = get(URL, grade=grade, page=page)
            budget -= 1
            if page == 1:
                pages = total_pages(html)
            rows = parse(html)
            if not rows:
                break
            yield from rows
            page += 1
