"""リサーチ部が使う情報源。どれも「読むだけ」で、サイトへのログインや操作はしない。

- routines: 設定ファイルに書いた毎日の定番タスク
- feeds:    公開されている RSS/Atom（キャンペーン・懸賞情報など）
- mail:     ポータルから届く案内メール（IMAP・読み取り専用）
"""

from __future__ import annotations

import email
import imaplib
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from email.header import decode_header, make_header

from .models import Opportunity

POINT_RE = re.compile(r"(\d[\d,]*)\s*(?:ポイント|pt|ｐｔ|P\b|円相当|円分)", re.I)
URL_RE = re.compile(r"https://[^\s\"'<>）)]+")
DEADLINE_RE = re.compile(r"(\d{1,2})[/月](\d{1,2})日?\s*(?:まで|締切|〆切)")


def parse_points(text: str) -> float:
    m = POINT_RE.search(text or "")
    return float(m.group(1).replace(",", "")) if m else 0.0


def parse_deadline(text: str, today: date) -> str:
    m = DEADLINE_RE.search(text or "")
    if not m:
        return ""
    month, dom = int(m.group(1)), int(m.group(2))
    try:
        d = date(today.year, month, dom)
    except ValueError:
        return ""
    if d < today - timedelta(days=180):  # 年またぎ
        d = d.replace(year=today.year + 1)
    return d.isoformat()


def from_routines(cfg: dict, today: date) -> list[Opportunity]:
    return [
        Opportunity(
            site=r["site"], title=r["title"], url=r.get("url", ""),
            task_type=r.get("task_type", "unknown"),
            points=float(r.get("points", 0)), minutes=float(r.get("minutes", 0)),
            source="routine", day=today.isoformat(),
        )
        for r in cfg.get("routines", [])
    ]


def from_feeds(cfg: dict, today: date) -> list[Opportunity]:
    import requests

    out: list[Opportunity] = []
    for feed in cfg.get("feeds", []):
        resp = requests.get(feed["url"], timeout=20, headers={"User-Agent": "feed-reader"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = [e for e in root.iter() if e.tag.split("}")[-1] in ("item", "entry")]
        for item in items[: int(feed.get("max_items", 20))]:
            fields = {c.tag.split("}")[-1]: c for c in item}
            title = (fields["title"].text or "").strip() if "title" in fields else ""
            link_el = fields.get("link")
            link = ""
            if link_el is not None:
                link = (link_el.text or "").strip() or link_el.get("href", "")
            if not title:
                continue
            out.append(Opportunity(
                site=feed["site"], title=title, url=link,
                task_type=feed.get("task_type", "unknown"),
                points=parse_points(title), deadline=parse_deadline(title, today),
                source="feed",
            ))
    return out


def _body_text(msg) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    chunks = []
    for part in parts:
        if part.get_content_type() in ("text/plain", "text/html"):
            payload = part.get_payload(decode=True) or b""
            chunks.append(payload.decode(part.get_content_charset() or "utf-8", "replace"))
    return "\n".join(chunks)


def from_mail(cfg: dict, today: date) -> list[Opportunity]:
    """案内メールを読み取り専用で走査する。未設定なら何もしない。"""
    host = os.getenv("POIKATSU_IMAP_HOST")
    user = os.getenv("POIKATSU_IMAP_USER")
    password = os.getenv("POIKATSU_IMAP_PASSWORD")
    if not (host and user and password):
        return []

    senders = {
        pat.lower(): name
        for name, site in cfg.get("sites", {}).items()
        for pat in site.get("mail_from", [])
    }
    out: list[Opportunity] = []
    imap = imaplib.IMAP4_SSL(host)
    try:
        imap.login(user, password)
        imap.select(os.getenv("POIKATSU_IMAP_FOLDER", "INBOX"), readonly=True)
        since = (today - timedelta(days=1)).strftime("%d-%b-%Y")
        _, data = imap.search(None, "SINCE", since)
        for num in data[0].split()[-200:]:
            _, raw = imap.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(raw[0][1])
            sender = str(make_header(decode_header(msg.get("From", "")))).lower()
            site = next((n for pat, n in senders.items() if pat in sender), None)
            if not site:
                continue
            subject = str(make_header(decode_header(msg.get("Subject", "")))).strip()
            body = _body_text(msg)
            link = URL_RE.search(body)
            out.append(Opportunity(
                site=site, title=subject, url=link.group(0) if link else "",
                points=parse_points(subject) or parse_points(body[:2000]),
                deadline=parse_deadline(subject + " " + body[:2000], today),
                source="mail",
            ))
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return out


def demo(today: date) -> list[Opportunity]:
    """ネット接続なしで全体の流れを確認するためのサンプル。"""
    d = today.isoformat()
    soon = (today + timedelta(days=1)).isoformat()
    return [
        Opportunity("m3.com", "今日のログイン・デイリー確認", "https://www.m3.com/", "login", 5, 0.5, source="demo", day=d),
        Opportunity("m3.com", "MR君 新着メッセージ 3件", "https://www.m3.com/", "read", 30, 4, source="demo", day=d),
        Opportunity("m3.com", "【謝礼300ポイント】小児喘息治療に関するアンケート", "https://www.m3.com/", points=300, deadline=soon, source="demo"),
        Opportunity("日経メディカル", "今日のクイズに答えてポイント", "https://medical.nikkeibp.co.jp/", source="demo", day=d),
        Opportunity("CareNet", "Web講演会「小児感染症アップデート」視聴で50ポイント", "https://www.carenet.com/", points=50, source="demo"),
        Opportunity("ポイントサイトA", "毎日クリックで1ポイント", "https://example.com/click", "click", 1, 0.5, source="demo", day=d),
        Opportunity("ポイントサイトA", "クレジットカード発行で10,000ポイント", "https://example.com/card", points=10000, source="demo"),
        Opportunity("懸賞情報", "レンコン4kg プレゼント 5名（11/30まで）", "https://example.com/renkon", source="demo", deadline=parse_deadline("11/30まで", today)),
        Opportunity("公式自動化OKサイト(例)", "毎日ログインボーナス", "https://example.com/api", "login", 2, 0.2, source="demo", day=d),
    ]
