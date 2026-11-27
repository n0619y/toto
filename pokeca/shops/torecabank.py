"""トレカバンク 店頭買取表（/kaitori_list）と郵送買取表（/mail_buy_list）。

robots.txt は Disallow が空で全ページ許可（2026-11 確認）。
- 店頭: ページに埋め込まれている商品データ（allProducts の JSON、全件が1ページ）を読む。
- 郵送: 商品一覧の HTML を読む（ポケモンカードゲームに絞る category=1、1ページ約100件）。
店頭と郵送で価格が違うので、店名を「トレカバンク店頭」「トレカバンク郵送」に分けて返す。
"""

from __future__ import annotations

import html as htmllib
import json
import re

SHOP = "トレカバンク"
SHOP_STORE = "トレカバンク店頭"
SHOP_MAIL = "トレカバンク郵送"
STORE_URL = "https://store.torecabank.com/kaitori_list"
MAIL_URL = "https://store.torecabank.com/mail_buy_list"
POKEMON = "1"          # カテゴリ番号（絞り込みフォームの「ポケモンカードゲーム」）
MAX_PAGES = 100
NUMBER_RE = re.compile(r"^[0-9]{1,4}[A-Za-z]?/[0-9A-Za-z\-]{1,12}$")   # 例: 096/071, 397/SM-P
PRODUCTS_RE = re.compile(r"const allProducts = (\[.*?\]);\s*\n", re.S)
ITEM_RE = re.compile(r'<li class="item[^"]*" data-id="(\d+)"[^>]*>(.*?)</li>', re.S)


def _grade(type_name: str) -> str | None:
    """商品タイプ -> グレード。カード以外（未開封BOX など）は None。"""
    t = re.sub(r"\s+", "", type_name).upper()
    if re.fullmatch(r"PSA\d{1,2}", t):
        return t
    return "" if t in ("未鑑定", "素体", "シングル") else None


def parse_store(html: str) -> list[dict]:
    """店頭買取表のページから買取行を取り出す。"""
    m = PRODUCTS_RE.search(html)
    if not m:
        return []
    rows = []
    for rec in json.loads(m.group(1)):
        grade = _grade(str(rec.get("product_type_name") or ""))
        number = str(rec.get("product_master_key2") or "").strip()
        if str(rec.get("category_id")) != POKEMON or grade is None or not NUMBER_RE.match(number):
            continue
        name = re.sub(r"^[(（]PSA\s*\d+[)）]\s*", "", str(rec.get("product_master_name") or "")).strip()
        rarity = str(rec.get("product_master_key1") or "").strip()
        if rarity and rarity != "PROMO":
            name = f"{name} {rarity}"   # 郵送の一覧と同じ「カード名 レアリティ」の形にそろえる
        try:
            price = int(float(rec.get("buy_price") or 0))
        except ValueError:
            continue
        if price > 0:
            rows.append({"shop": SHOP_STORE, "number": number, "name": name, "grade": grade, "price": price})
    return rows


def parse_mail(html: str) -> list[dict]:
    """郵送買取の商品一覧ページ1枚から買取行を取り出す（画像表示とリスト表示の重複は1件にする）。"""
    rows, seen = [], set()
    for item_id, body in ITEM_RE.findall(html):
        name = re.search(r'<p class="name">(.*?)</p>', body, re.S)
        tag = re.search(r'<p class="tag">(.*?)</p>', body, re.S)
        price = re.search(r'<p class="price">\s*([\d,]+)', body)
        if item_id in seen or not (name and tag and price):
            continue
        grade = _grade(htmllib.unescape(re.sub(r"<[^>]+>", "", tag.group(1))))
        words = htmllib.unescape(re.sub(r"<[^>]+>", "", name.group(1))).split()
        if grade is None or len(words) < 2 or not NUMBER_RE.match(words[-1]):
            continue  # BOX、番号の無いカード（旧裏など）、他ゲームの型番は対象外
        seen.add(item_id)
        if words[-2] == "PROMO":
            words.pop(-2)
        rows.append({"shop": SHOP_MAIL, "number": words[-1], "name": " ".join(words[:-1]), "grade": grade,
                     "price": int(price.group(1).replace(",", "")), "item_id": item_id})
    return rows


def total_pages(html: str) -> int:
    pages = [int(p) for p in re.findall(r'href="[^"]*mail_buy_list\?[^"]*\bpage=(\d+)', html)]
    return max(pages, default=1)


def fetch(max_pages: int | None = None):
    from . import get

    budget = max_pages or MAX_PAGES
    yield from parse_store(get(STORE_URL))
    budget -= 1
    page, pages = 1, 1
    while page <= pages and budget > 0:
        html = get(MAIL_URL, category=POKEMON, page=page)
        budget -= 1
        pages = max(pages, total_pages(html))
        yield from parse_mail(html)
        page += 1
