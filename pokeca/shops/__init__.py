"""買取店ごとの買取表取得。

各店のモジュールは fetch(max_pages=None) -> Iterable[dict] を持ち、
shop / number / name / grade / price の行を返す。公開ページを読むだけで、ログインはしない。
"""

from __future__ import annotations

import logging
import time

import requests

from . import shinsoku, toreca_lounge, torecabank, torecaclub

log = logging.getLogger("pokeca")

SHOPS = {m.SHOP: m for m in (shinsoku, toreca_lounge, torecaclub, torecabank)}

USER_AGENT = "Mozilla/5.0 (compatible; pokeca-price-check; personal use)"
DELAY_SECONDS = 1.5   # 1店あたりの連続アクセス間隔（相手サーバーに負荷をかけない）


def get(url: str, **params) -> str:
    """間隔を空けて1ページ取得する。"""
    time.sleep(DELAY_SECONDS)
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.encoding if resp.encoding and resp.encoding.lower() != "iso-8859-1" else "utf-8"
    return resp.text


def fetch_all(db, day: str, only: list[str] | None = None, max_pages: int | None = None) -> list[str]:
    """対応している店の買取表を取得して保存する。失敗した店名の一覧を返す。"""
    failed = []
    for name, mod in SHOPS.items():
        if only and name not in only:
            continue
        try:
            rows = list(mod.fetch(max_pages=max_pages))
            if not rows:
                raise RuntimeError("0件でした（ページ構造が変わった可能性）")
            n = db.save_prices(rows, day)
            print(f"{name}: {len(rows)}件取得、うちカード番号のある{n}件を保存")
        except Exception as exc:
            failed.append(name)
            print(f"{name}: 取得に失敗しました ({exc})")
    return failed


def fetch_x(db, cfg: dict, day: str, limit: int = 10) -> list[dict]:
    """X の公式 API で各店の新着投稿を読み、買取行を保存する。照合できなかった行を返す。"""
    import os

    from . import xposts

    if not os.getenv("X_BEARER_TOKEN"):
        raise RuntimeError("X_BEARER_TOKEN が未設定です（X の開発者アカウントで発行したトークンが必要）")
    aliases = cfg.get("aliases") or {}
    unresolved_all = []
    for shop, username in (cfg.get("x_accounts") or {}).items():
        try:
            rows, newest = xposts.fetch_account(username, shop, db.get(f"x_since:{username}"), limit)
        except Exception as exc:
            print(f"{shop} (@{username}): 取得に失敗しました ({exc})")
            continue
        ok, unresolved = xposts.resolve(rows, aliases, db.known_names())
        n = db.save_prices(ok, day)
        if newest:
            db.put(f"x_since:{username}", newest)
        unresolved_all += unresolved
        print(f"{shop} (@{username}): 買取行 {len(rows)}件、保存 {n}件、未照合 {len(unresolved)}件")
        time.sleep(DELAY_SECONDS)
    return unresolved_all
