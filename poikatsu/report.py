"""朝の報告（Markdown / HTML）の生成と、任意のメール送信。"""

from __future__ import annotations

import html
import os
import smtplib
from email.mime.text import MIMEText

from .agents import DayContext
from .models import HOLD, HUMAN, Opportunity

TYPE_LABEL = {"login": "ログイン", "click": "クリック", "read": "閲覧", "video": "視聴",
              "survey": "アンケート", "quiz": "クイズ", "entry": "応募", "signup": "申込",
              "purchase": "購入", "unknown": "その他"}


def _groups(opps: list[Opportunity]):
    route = sorted((o for o in opps if o.selected and o.verdict == HUMAN), key=lambda o: -o.score)
    hold = [o for o in opps if o.verdict == HOLD]
    rest = sorted((o for o in opps if not o.selected and o.verdict == HUMAN), key=lambda o: -o.score)
    return route, hold, rest


def _line(o: Opportunity) -> str:
    bits = [TYPE_LABEL[o.task_type], f"約{o.minutes:g}分"]
    if o.value_yen:
        bits.append(f"約{o.value_yen:.0f}円相当")
    if o.deadline:
        bits.append(f"〆{o.deadline}")
    bits += o.notes
    return " / ".join(bits)


def to_markdown(ctx: DayContext, opps: list[Opportunity]) -> str:
    route, hold, rest = _groups(opps)
    out = [f"# ポイ活カンパニー 朝報 {ctx.today.isoformat()}", "", ctx.briefing, ""]
    out.append(f"## 今日のルート（{len(route)}件・約{sum(o.minutes for o in route):.0f}分）")
    for o in route:
        out.append(f"- [ ] `{o.id}` **[{o.site}]** [{o.title}]({o.url}) — {_line(o)}")
    if ctx.executed:
        out += ["", "## 自動実行済み"] + [f"- {e}" for e in ctx.executed]
    if hold:
        out += ["", "## 本人判断待ち（お金・契約が絡む）"]
        out += [f"- **[{o.site}]** [{o.title}]({o.url}) — {_line(o)}" for o in hold]
    if rest:
        out += ["", "## 今日は見送り（時間予算外・価値不明）"]
        out += [f"- `{o.id}` [{o.site}] {o.title} — {_line(o)}" for o in rest[:30]]
    if ctx.warnings:
        out += ["", "## 各部署からの警告"] + [f"- {w}" for w in ctx.warnings]
    out += ["", "完了したら: `python -m poikatsu done all`（一部だけなら ID を指定）"]
    return "\n".join(out) + "\n"


def to_html(ctx: DayContext, opps: list[Opportunity]) -> str:
    route, hold, rest = _groups(opps)
    e = html.escape

    def items(group, link=True):
        rows = []
        for o in group:
            title = f'<a href="{e(o.url)}">{e(o.title)}</a>' if link and o.url else e(o.title)
            rows.append(f"<li><b>{e(o.site)}</b> {title}<br><small>{e(_line(o))} · {o.id}</small></li>")
        return "<ul>" + "".join(rows) + "</ul>"

    def route_buttons(group):
        rows = [
            f'<li><a href="{e(o.url)}">{e(o.site)}｜{e(o.title)}</a>'
            f"<small>{e(_line(o))} · {o.id}</small></li>"
            for o in group
        ]
        return '<ol class="route">' + "".join(rows) + "</ol>"

    parts = [
        "<!doctype html><html lang='ja'><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>ポイ活朝報 {ctx.today}</title>",
        "<style>body{font-family:sans-serif;max-width:640px;margin:auto;padding:16px;line-height:1.6}"
        "li{margin:10px 0}small{color:#666}a{font-size:1.05em}"
        "ol.route{list-style:none;padding:0;counter-reset:n}"
        "ol.route a{display:block;padding:14px 16px;border-radius:12px;background:#1a73e8;"
        "color:#fff;text-decoration:none;font-weight:bold}"
        "ol.route a::before{counter-increment:n;content:counter(n) '. '}"
        "ol.route a:visited{background:#9aa0a6}</style>",
        f"<h1>ポイ活朝報 {ctx.today}</h1><p>{e(ctx.briefing)}</p>",
        f"<h2>今日のルート（{len(route)}件・約{sum(o.minutes for o in route):.0f}分）</h2>", route_buttons(route),
    ]
    if ctx.executed:
        parts.append("<h2>自動実行済み</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in ctx.executed) + "</ul>")
    if hold:
        parts += ["<h2>本人判断待ち</h2>", items(hold)]
    if rest:
        parts += ["<h2>今日は見送り</h2>", items(rest[:30], link=False)]
    if ctx.warnings:
        parts.append("<h2>警告</h2><ul>" + "".join(f"<li>{e(w)}</li>" for w in ctx.warnings) + "</ul>")
    return "".join(parts)


def send_mail(subject: str, html_body: str) -> bool:
    """POIKATSU_SMTP_* と POIKATSU_REPORT_TO が揃っている場合だけ送信する。"""
    host, user = os.getenv("POIKATSU_SMTP_HOST"), os.getenv("POIKATSU_SMTP_USER")
    password, to = os.getenv("POIKATSU_SMTP_PASSWORD"), os.getenv("POIKATSU_REPORT_TO")
    if not (host and user and password and to):
        return False
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    with smtplib.SMTP_SSL(host, int(os.getenv("POIKATSU_SMTP_PORT", "465"))) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    return True
