"""X（旧Twitter）に投稿される買取情報の取得。

公式の X API v2 だけを使う（従量課金。投稿の読み取り1件あたり約0.005ドル）。
環境変数 X_BEARER_TOKEN が無ければ何もしない。X の画面を直接読み取ることはしない（規約で禁止）。

投稿本文に「カード名（番号）￥価格」と書かれている行を買取行として読む。
番号が書かれていない行は、別名表（config/pokeca.yaml の aliases）か、
すでに台帳にあるカード名との一致で照合し、照合できなかった行は unresolved に残す。
画像だけの買取表はここでは読まない。
"""

from __future__ import annotations

import os
import re
import unicodedata

API = "https://api.x.com/2"
OTHER_GAMES = re.compile(r"ワンピ|ONE\s*PIECE|ONEPIECE|遊戯王|ドラゴンボール|\bOP\d{2}-\d{3}|\bEB\d{2}-\d{3}", re.I)
PRICE_RE = re.compile(r"[¥￥]\s*([\d,]{3,})|([\d,]{4,})\s*円")
NUMBER_RE = re.compile(r"[(（]\s*([0-9A-Za-z\-]{1,12}/[0-9A-Za-z\-]{1,12})\s*[)）]")
GRADE_RE = re.compile(r"PSA\s*(10|9)")
# 行頭の飾り（絵文字・チェック記号・箇条書き）
LEAD_RE = re.compile(r"^[\s\W_]+", re.UNICODE)


def _digits(text: str) -> str:
    """囲み数字（2⃣ など）や全角数字をふつうの数字にする。"""
    text = unicodedata.normalize("NFKC", text)
    return text.replace("⃣", "").replace("️", "")


def parse_post(text: str, shop: str) -> list[dict]:
    """投稿本文1件から買取行を取り出す。ポケカ以外の投稿は空を返す。"""
    text = _digits(text)
    if OTHER_GAMES.search(text):
        return []
    default_grade = GRADE_RE.search(text)
    rows = []
    for line in text.splitlines():
        m = PRICE_RE.search(line)
        if not m:
            continue
        price = int((m.group(1) or m.group(2)).replace(",", ""))
        head = line[: m.start()]
        num = NUMBER_RE.search(head)
        grade = GRADE_RE.search(head) or default_grade
        name = NUMBER_RE.sub("", head)
        name = GRADE_RE.sub("", name)
        name = re.sub(r"[\U0001F000-\U0001FFFF☀-➿⬀-⯿]", "", name)  # 絵文字
        name = LEAD_RE.sub("", name).strip(" :：・-→⇒")
        if not name or price < 300:
            continue
        rows.append({
            "shop": shop, "name": name, "number": num.group(1) if num else "",
            "grade": f"PSA{grade.group(1)}" if grade else "", "price": price,
        })
    return rows


def resolve(rows: list[dict], aliases: dict, known: dict) -> tuple[list[dict], list[dict]]:
    """番号の無い行を照合する。

    aliases: 通称 -> {"number": .., "name": ..}（人が確認して登録したもの）
    known:   正規化したカード名 -> 番号の集合（台帳にある買取表から作る）
    """
    norm = lambda s: re.sub(r"\s+", "", unicodedata.normalize("NFKC", s)).upper()
    ok, unresolved = [], []
    for r in rows:
        if r["number"]:
            ok.append(r)
            continue
        hit = aliases.get(r["name"]) or aliases.get(norm(r["name"]))
        if hit:
            ok.append({**r, "number": hit["number"], "name": hit.get("name", r["name"])})
            continue
        numbers = known.get(norm(r["name"]), set())
        if len(numbers) == 1:        # 同じ名前のカードが1種類だけなら確定できる
            ok.append({**r, "number": next(iter(numbers))})
        else:
            unresolved.append({**r, "candidates": sorted(numbers)})
    return ok, unresolved


def fetch_account(username: str, shop: str, since_id: str | None = None, limit: int = 10) -> tuple[list[dict], str | None]:
    """1アカウントの新着投稿を読む。戻り値は (買取行, 最新の投稿ID)。"""
    import requests

    token = os.environ["X_BEARER_TOKEN"]
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    user = s.get(f"{API}/users/by/username/{username}", timeout=30)
    user.raise_for_status()
    params = {"max_results": max(5, min(limit, 100)), "exclude": "retweets,replies",
              "tweet.fields": "created_at"}
    if since_id:
        params["since_id"] = since_id
    resp = s.get(f"{API}/users/{user.json()['data']['id']}/tweets", params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    rows = []
    for post in body.get("data", []):
        rows += parse_post(post["text"], shop)
    return rows, body.get("meta", {}).get("newest_id")
