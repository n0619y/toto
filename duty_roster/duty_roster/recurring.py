"""各月共通の定例予定 (第 N 曜日 / 毎週) を月ごとの予定に展開する.

設定ファイル (data/recurring.yaml)::

    members: [岡﨑, 仲本, 佐々木]
    rules:
      - members: all                 # all または名前のリスト
        weekday: 水
        week: all                    # 1..5 または all (毎週)
        event: "心臓カテーテル (AM)"
        exclude: [{months: even, week: 2}]
      - {members: [仲本], weekday: 金, week: 1, event: "由利組合 (PM)", months: odd}
    defaults:
      岡﨑: センター業務             # 平日の空き (AM/PM) に入れる

土日・祝日には入れない (呼び出し側から休日判定関数を渡す)。
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Callable

import yaml

WEEKDAYS = "月火水木金土日"
_AM_PATTERN = re.compile(r"[(（]\s*(AM|午前)\s*[)）]", re.I)
_PM_PATTERN = re.compile(r"[(（]\s*(PM|午後)\s*[)）]", re.I)
_ALLDAY_PATTERN = re.compile(r"[(（]\s*(AM/PM|午前/午後|終日)\s*[)）]", re.I)
_NIGHT_PATTERN = re.compile(r"[(（]\s*(夜間|夜|NIGHT)\s*[)）]", re.I)


@dataclass(frozen=True)
class Condition:
    week: int | None = None  # None = 週を問わない
    months: str = "all"  # all / odd / even

    def matches(self, month: int, week: int) -> bool:
        if self.week is not None and self.week != week:
            return False
        if self.months == "odd":
            return month % 2 == 1
        if self.months == "even":
            return month % 2 == 0
        return True


@dataclass(frozen=True)
class Rule:
    members: tuple[str, ...]  # 空 = 全員
    weekday: int  # 0 = 月
    week: int | None  # None = 毎週
    event: str
    months: str = "all"
    exclude: tuple[Condition, ...] = ()

    def applies(self, month: int, week: int) -> bool:
        if not Condition(self.week, self.months).matches(month, week):
            return False
        return not any(c.matches(month, week) for c in self.exclude)


@dataclass
class Recurring:
    members: list[str]
    rules: list[Rule] = field(default_factory=list)
    defaults: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "Recurring":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        members = [str(m) for m in (data.get("members") or [])]
        rec = cls(members)
        for i, it in enumerate(data.get("rules") or [], start=1):
            wd = str(it["weekday"]).strip()
            if wd not in WEEKDAYS:
                raise ValueError(f"rules[{i}]: 曜日が不正です: {wd!r}")
            mem = it.get("members", "all")
            members_t: tuple[str, ...] = () if mem in ("all", None) else tuple(str(m) for m in mem)
            for m in members_t:
                if m not in rec.members:
                    rec.members.append(m)
            exclude = tuple(Condition(_week(c.get("week")), _months(c.get("months"))) for c in it.get("exclude") or [])
            rec.rules.append(Rule(members_t, WEEKDAYS.index(wd), _week(it.get("week", "all")), str(it["event"]).strip(), _months(it.get("months")), exclude))
        for m, ev in (data.get("defaults") or {}).items():
            rec.defaults[str(m)] = str(ev).strip()
        return rec

    def rule_members(self, rule: Rule) -> tuple[str, ...]:
        return rule.members or tuple(self.members)


def _week(v) -> int | None:  # noqa: ANN001
    if v in (None, "all", "毎週"):
        return None
    return int(v)


def _months(v) -> str:  # noqa: ANN001
    s = str(v or "all").lower()
    if s not in ("all", "odd", "even"):
        raise ValueError(f"months は all / odd / even のいずれかです: {v!r}")
    return s


def week_of_month(day: int) -> int:
    """その曜日の第何週目か (1 日〜7 日 = 第 1)."""
    return (day - 1) // 7 + 1


def _slot_flags(event: str) -> tuple[bool, bool]:
    """予定文字列が AM / PM を占めるか."""
    if _ALLDAY_PATTERN.search(event):
        return True, True
    if _AM_PATTERN.search(event):
        return True, False
    if _PM_PATTERN.search(event):
        return False, True
    if _NIGHT_PATTERN.search(event):
        return False, False
    return True, True  # 無印 (休暇など) は終日


def _sort_key(event: str) -> int:
    am, pm = _slot_flags(event)
    if _NIGHT_PATTERN.search(event):
        return 3
    if am and pm:
        return 0
    return 1 if am else 2


def expand(rec: Recurring, year: int, month: int, is_holiday: Callable[[dt.date], bool]) -> dict[int, dict[str, str]]:
    """{day: {member: "予定, 予定"}} を返す. 休日には入れない."""
    ndays = calendar.monthrange(year, month)[1]
    out: dict[int, dict[str, list[str]]] = {}
    for day in range(1, ndays + 1):
        date = dt.date(year, month, day)
        if is_holiday(date):
            continue
        wk = week_of_month(day)
        for rule in rec.rules:
            if rule.weekday != date.weekday() or not rule.applies(month, wk):
                continue
            for m in rec.rule_members(rule):
                lst = out.setdefault(day, {}).setdefault(m, [])
                if rule.event not in lst:
                    lst.append(rule.event)
        # 既定業務: 空いている AM / PM を埋める
        for m, ev in rec.defaults.items():
            lst = out.setdefault(day, {}).setdefault(m, [])
            am = any(_slot_flags(e)[0] for e in lst)
            pm = any(_slot_flags(e)[1] for e in lst)
            if not am and not pm:
                lst.append(ev)
            elif not am:
                lst.append(f"{ev} (AM)")
            elif not pm:
                lst.append(f"{ev} (PM)")
    result: dict[int, dict[str, str]] = {}
    for day, per in out.items():
        for m, lst in per.items():
            if lst:
                result.setdefault(day, {})[m] = ", ".join(sorted(lst, key=_sort_key))
    return result


def skipped_on_holidays(rec: Recurring, year: int, month: int, is_holiday: Callable[[dt.date], bool]) -> list[tuple[int, str, str]]:
    """休日のため入力しなかった定例予定 [(day, member, event)] (既定業務は除く)."""
    ndays = calendar.monthrange(year, month)[1]
    out = []
    for day in range(1, ndays + 1):
        date = dt.date(year, month, day)
        if not is_holiday(date):
            continue
        wk = week_of_month(day)
        for rule in rec.rules:
            if rule.weekday == date.weekday() and rule.applies(month, wk):
                for m in rec.rule_members(rule):
                    out.append((day, m, rule.event))
    return out
