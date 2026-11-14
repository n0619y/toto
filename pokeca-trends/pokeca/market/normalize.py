"""カード名・型番・価格の正規化。ショップごとに表記が違うため、同一カードを同じキーにまとめる。"""
from __future__ import annotations

import re
import unicodedata

RARITY_ALIASES = {"sar": "SAR", "sr": "SR", "ar": "AR", "ur": "UR", "hr": "HR", "chr": "CHR", "csr": "CSR",
                  "rr": "RR", "rrr": "RRR", "s": "S", "ssr": "SSR", "acespec": "ACE", "ace": "ACE",
                  "プロモ": "PROMO", "promo": "PROMO", "ma": "MA", "bwr": "BWR", "mur": "MUR"}


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def norm_name(name: str) -> str:
    s = nfkc(name)
    s = re.sub(r"[【\[(（].*?[】\])）]", "", s)   # 【SAR】などの括弧書きは名前から外す
    s = re.sub(r"\s+", "", s)
    return s.replace("ＥＸ", "ex").replace("EX", "ex")


def norm_number(num: str) -> str:
    s = nfkc(num).replace(" ", "")
    m = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", s)
    if m:
        return f"{int(m.group(1)):03d}/{int(m.group(2)):03d}"
    return s.upper()


def norm_rarity(r: str) -> str:
    s = nfkc(r).replace(" ", "")
    return RARITY_ALIASES.get(s.lower(), s.upper())


def parse_price(v) -> int | None:
    if isinstance(v, (int, float)):
        return int(v)
    s = nfkc(str(v)).replace(",", "").replace("¥", "").replace("円", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def card_key(name: str, number: str = "", rarity: str = "") -> str:
    return "|".join([norm_name(name), norm_number(number), norm_rarity(rarity)])


def normalize_row(row: dict) -> dict | None:
    price = parse_price(row.get("price"))
    name = nfkc(row.get("card_name", ""))
    if not name or not price or price <= 0:
        return None
    # 型番・レアリティがカード名に混ざっている場合は抜き出す
    number = row.get("card_number") or ""
    if not number:
        m = re.search(r"\d{1,3}\s*/\s*\d{1,3}", name)
        number = m.group() if m else ""
    rarity = row.get("rarity") or ""
    if not rarity:
        m = re.search(r"[【\[(（]\s*(SAR|SR|AR|UR|HR|CHR|CSR|RRR|RR|SSR|S|ACE|MA|BWR|MUR)\s*[】\])）]", name, re.I)
        rarity = m.group(1) if m else ""
    clean_name = re.sub(r"\d{1,3}\s*/\s*\d{1,3}", "", norm_name(name)).strip()
    return {
        "card_key": card_key(clean_name, number, rarity),
        "card_name": clean_name, "card_number": norm_number(number) if number else "",
        "rarity": norm_rarity(rarity) if rarity else "", "price": price,
        "condition": nfkc(row.get("condition", "")),
    }
