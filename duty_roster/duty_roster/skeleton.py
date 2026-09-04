"""plan (予定一覧) → roster の雛形 (予定だけを埋めたコマ表) を作る.

1枚目の予定文字列 "外来 (AM/PM), web会議 (19時～)" を、3 コマ (AM / PM / NIGHT) の予定に落とす。
当番 (1st / 2nd) はここでは入れない。人が (将来は自動割り当てが) 埋める。

観察した対応 (samples/ の 2026-09 より):

    外来 (AM/PM)          → AM, PM に 外来
    外来 (PM)             → PM に 外来
    外来 (AM), 休暇 (PM)  → AM 外来, PM 休暇
    休暇                  → AM, PM に 休暇 (夜は空き)
    休暇, 平鹿 (PM)       → AM 休暇, PM 平鹿   (無印の休暇は他の予定に譲る)
    男鹿 (AM)             → AM に 男鹿
    男鹿前日              → 夜は当番に入れない (出発のため). コマは空きのまま, コメントに残す
    ○○会議 (16時～)      → PM に 会議   (16 時台は PM 扱い)
    web会議 (19時～)      → NIGHT に Web会議
    空港発 (15時50分)     → PM, NIGHT (移動)
    空港着 (11時25分)     → AM (移動)
    OSCE外部評価者 (佐賀) → 終日 (括弧内が時刻でなければ場所とみなし, ラベルは括弧内)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Roster, SlotSpec
from .parse_plan import DEPT_KEY, Plan

# 表示名の置き換え (元表で使われていた略称). 必要に応じて config で上書き可能.
DEFAULT_ALIASES = {
    "web会議": "Web会議",
    "医療安全管理部担当者会議": "会議",
}

# 「前日」= 翌日朝から出張のため夜は不可、という記法
PREV_DAY_SUFFIX = "前日"


@dataclass
class ParsedEvent:
    name: str
    qualifier: str | None  # 括弧内
    slots: list[int] = field(default_factory=list)  # 0=AM 1=PM 2=NIGHT
    label: str = ""
    unavailable_night: bool = False
    priority: int = 1  # 大きいほど優先 (同じコマに複数の予定があるとき)


_AMPM = {
    "AM": [0],
    "PM": [1],
    "AM/PM": [0, 1],
    "PM/AM": [0, 1],
    "午前": [0],
    "午後": [1],
    "午前/午後": [0, 1],
    "終日": [0, 1],
    "夜間": [2],
    "夜": [2],
    "NIGHT": [2],
}


def split_top_level(text: str) -> list[str]:
    """括弧の外にあるカンマで分割する."""
    out, depth, buf = [], 0, ""
    for ch in text:
        if ch in "(（":
            depth += 1
        elif ch in ")）":
            depth = max(0, depth - 1)
        if ch in ",、" and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


def _hour_of(q: str) -> float | None:
    m = re.search(r"(\d{1,2})\s*時\s*(\d{1,2})?\s*分?", q)
    if not m:
        m2 = re.search(r"(\d{1,2}):(\d{2})", q)
        if not m2:
            return None
        return int(m2.group(1)) + int(m2.group(2)) / 60
    return int(m.group(1)) + (int(m.group(2)) / 60 if m.group(2) else 0)


def _slot_of_hour(h: float) -> int:
    if h < 12:
        return 0
    if h < 17:
        return 1
    return 2


def parse_event(item: str, aliases: dict[str, str] | None = None) -> ParsedEvent:
    aliases = {**DEFAULT_ALIASES, **(aliases or {})}
    m = re.match(r"^(.*?)\s*[(（](.*?)[)）]\s*$", item)
    name, qual = (m.group(1).strip(), m.group(2).strip()) if m else (item.strip(), None)
    ev = ParsedEvent(name=name, qualifier=qual, label=aliases.get(name, name))

    if name.endswith(PREV_DAY_SUFFIX):
        ev.unavailable_night = True
        ev.slots = []
        return ev

    if qual is None:
        # 無印: 休暇などは昼間 (AM/PM). 他の予定に譲る (優先度低)
        ev.slots = [0, 1]
        ev.priority = 0
        return ev

    q = qual.replace(" ", "").upper()
    if q in _AMPM:
        ev.slots = list(_AMPM[q])
        return ev

    hour = _hour_of(qual)
    if hour is not None:
        start = _slot_of_hour(hour)
        if "～" in qual or "〜" in qual or "~" in qual or "-" in qual:
            # "16時～" のような開始時刻: そのコマのみ (夜にまたがる会議は稀なので広げない)
            ev.slots = [start]
        elif "発" in name:
            ev.slots = list(range(start, 3))  # 出発以降は移動
        elif "着" in name:
            ev.slots = list(range(0, start + 1))  # 到着まで移動
        else:
            ev.slots = [start]
        return ev

    # 括弧内が時刻でも AM/PM でもない → 場所とみなして終日. ラベルは場所
    ev.slots = [0, 1, 2]
    ev.label = aliases.get(qual, qual)
    return ev


def events_to_slots(text: str, aliases: dict[str, str] | None = None) -> tuple[list[SlotSpec], list[str]]:
    """予定文字列 → 3 コマの SlotSpec と、コマに落とせなかった注記."""
    slots: list[SlotSpec | None] = [None, None, None]
    prio = [-1, -1, -1]
    notes: list[str] = []
    for item in split_top_level(text):
        if not item:
            continue
        ev = parse_event(item, aliases)
        if ev.unavailable_night:
            notes.append(f"{ev.name} (夜は当番不可)")
            continue
        placed = False
        for s in ev.slots:
            if ev.priority > prio[s]:
                slots[s] = SlotSpec(event=ev.label)
                prio[s] = ev.priority
                placed = True
        if not placed and ev.slots:
            notes.append(item)
    return [s or SlotSpec() for s in slots], notes


def build_skeleton(plan: Plan, aliases: dict[str, str] | None = None, title: str = "") -> tuple[Roster, dict[int, list[str]]]:
    """plan から予定だけを入れた Roster を作る. 戻り値の 2 つ目は日ごとのコメント (元の予定文字列)."""
    roster = Roster(
        year=plan.year,
        month=plan.month,
        members=list(plan.members),
        holidays={d for d in plan.holidays if plan_date_is_weekday(plan, d)},
        title=title,
    )
    comments: dict[int, list[str]] = {}
    for day in range(1, roster.ndays + 1):
        row = plan.days.get(day) or {}
        lines: list[str] = []
        for member in plan.members:
            text = row.get(member, "")
            if not text:
                continue
            specs, notes = events_to_slots(text, aliases)
            roster.days.setdefault(day, {})[member] = specs
            note = f"  ※{'; '.join(notes)}" if notes else ""
            lines.append(f"{member}: {text}{note}")
        if row.get(DEPT_KEY):
            lines.append(f"{DEPT_KEY}: {row[DEPT_KEY]}")
        comments[day] = lines
    return roster, comments


def plan_date_is_weekday(plan: Plan, day: int) -> bool:
    import datetime as dt

    return dt.date(plan.year, plan.month, day).weekday() < 5


def skeleton_yaml(roster: Roster, comments: dict[int, list[str]]) -> str:
    """コメント付きの roster.yaml テキストを作る (PyYAML はコメントを出せないので手組み)."""
    out = [
        f"month: {roster.year:04d}-{roster.month:02d}",
        f"title: {roster.title or roster.default_title()}",
        "members: [" + ", ".join(roster.members) + "]",
        "holidays: [" + ", ".join(str(d) for d in sorted(roster.holidays)) + "]",
        "# コマの書き方: 'AM, PM, NIGHT' の順. - = 空き, 1st / 2nd = 当番, 予定名 = 予定, 予定名/2nd = 予定しながら当番,",
        "#               1st+補足 = 当番ラベルの下に補足行, × = バツ印",
        "days:",
    ]
    for day in range(1, roster.ndays + 1):
        wd = "月火水木金土日"[roster.date(day).weekday()]
        hol = " 休" if roster.is_holiday(day) else ""
        out.append(f"  {day}:  # {wd}{hol}")
        for c in comments.get(day, []):
            out.append(f"    # {c}")
        for member in roster.members:
            specs = roster.slots(day, member)
            out.append(f"    {member}: " + ", ".join(s.to_text() for s in specs))
    return "\n".join(out) + "\n"
