"""トレカクラブ 郵送買取 PSA10 買取価格表（https://torecaclub.com/pokemon/psa10/）。

価格表ページ（1ページ100件、価格の高い順）の HTML を読む。掲載は PSA10 のポケモンカードだけ。
robots.txt は /api/ /dashboard/ /mypage/ /cart などが不可で、/pokemon/ は許可（2026-11 確認）。
価格はランク会員の上乗せ前の表示価格。
"""

from __future__ import annotations

import html as htmllib
import re

SHOP = "トレカクラブ"
URL = "https://torecaclub.com/pokemon/psa10/"
MAX_PAGES = 100
ITEM_RE = re.compile(
    r'<li><a [^>]*href="/pokemon/cards/psa10/([^"/]+)/?"[^>]*><img [^>]*alt="([^"]*)"'
    r'.*?font-medium">(.*?)</span>.*?<strong[^>]*>\s*¥([\d,]+)\s*</strong>', re.S)
NUMBER_RE = re.compile(r"^[0-9][0-9A-Za-z\-]{0,11}/[0-9A-Za-z\-]{1,12}$")   # 例: 096/071, 397/SM-P


def parse(html: str) -> list[dict]:
    """価格表ページ1枚から買取行を取り出す。"""
    rows = []
    for slug, alt, name, price in ITEM_RE.findall(html):
        alt, name = htmllib.unescape(alt).strip(), htmllib.unescape(re.sub(r"<[^>]+>", "", name)).strip()
        # 画像の代替テキストが「カード名 番号 PSA10」。表示欄の番号はプロモの「-P」が欠けるのでこちらを使う
        m = re.fullmatch(r"(\S+)\s+PSA10", alt[len(name):].strip()) if alt.startswith(name) else None
        if not m or not NUMBER_RE.match(m.group(1)):
            continue  # 番号の無いカード、保証枠（まとめ買取）は照合できない
        number = m.group(1)
        if re.fullmatch(r"\d+/[A-Za-z]+", number) and slug.upper().startswith(number.replace("/", "-").upper() + "-P"):
            number += "-P"   # 例: 代替テキスト 003/SV、URL 003-SV-P-CH
        rows.append({"shop": SHOP, "number": number, "name": name, "grade": "PSA10",
                     "price": int(price.replace(",", "")), "item_id": slug})
    return rows


def total_pages(html: str) -> int:
    nav = re.search(r'<nav aria-label="ページネーション".*?</nav>', html, re.S)
    m = re.search(r"\d+\s*/\s*(\d+)", re.sub(r"<[^>]+>", "", nav.group(0))) if nav else None
    return int(m.group(1)) if m else 1


def fetch(max_pages: int | None = None):
    from . import get

    first = get(URL)
    pages = min(total_pages(first), max_pages or MAX_PAGES)
    yield from parse(first)
    for page in range(2, pages + 1):
        yield from parse(get(URL, page=page))
