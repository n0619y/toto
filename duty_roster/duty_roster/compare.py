"""2 つのカレンダー (PDF 抽出結果 / Roster) をコマ単位で突き合わせる."""

from __future__ import annotations

from dataclasses import dataclass

from .extract_calendar import ExtractedCalendar, SlotInfo, _norm, slot_to_spec_text
from .model import COLOR_CODE, SLOT_NAMES, Roster, SlotSpec


@dataclass
class Diff:
    day: int
    member: str
    slot: int
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"{self.day:2d}日 {self.member} {SLOT_NAMES[self.slot]:5s}: 期待={self.expected!r} 実際={self.actual!r}"


def roster_from_calendar(cal: ExtractedCalendar, year: int, month: int, holidays: set[int] | None = None) -> Roster:
    """抽出結果を Roster に変換する (元 PDF から roster.yaml を起こすとき用)."""
    roster = Roster(year=year, month=month, members=list(cal.members), title=cal.title)
    if holidays is None:
        # 土日以外で、全メンバーの空きコマが水色ならその日は休日とみなす
        holidays = set()
        for day in range(1, roster.ndays + 1):
            if roster.date(day).weekday() >= 5:
                continue
            frees = [s for m in cal.members for s in cal.slots.get((day, m), []) if s.color in ("W", "B")]
            if frees and all(s.color == "B" for s in frees):
                holidays.add(day)
    roster.holidays = set(holidays)
    for (day, member), slots in cal.slots.items():
        for si, info in enumerate(slots):
            roster.set_slot(day, member, si, SlotSpec.parse(slot_to_spec_text(info)))
    return roster


_MISSING = SlotInfo("?")


def compare_roster_to_calendar(roster: Roster, cal: ExtractedCalendar) -> list[Diff]:
    diffs: list[Diff] = []
    for day in range(1, roster.ndays + 1):
        for member in roster.members:
            got = cal.slots.get((day, member))
            for si in range(3):
                exp = slot_info_from_spec(roster.slots(day, member)[si], roster.is_holiday(day))
                act = got[si] if got else _MISSING
                if exp.key() != act.key():
                    diffs.append(Diff(day, member, si, _fmt(exp), _fmt(act)))
    return diffs


def compare_calendars(expected: ExtractedCalendar, actual: ExtractedCalendar) -> list[Diff]:
    diffs: list[Diff] = []
    keys = sorted(set(expected.slots) | set(actual.slots))
    for day, member in keys:
        e = expected.slots.get((day, member))
        a = actual.slots.get((day, member))
        for si in range(3):
            ei = e[si] if e else _MISSING
            ai = a[si] if a else _MISSING
            if ei.key() != ai.key():
                diffs.append(Diff(day, member, si, _fmt(ei), _fmt(ai)))
    return diffs


def _fmt(info: SlotInfo) -> str:
    return f"{info.color}:{_norm(info.label) or '-'}{' ×' if info.cross else ''}"


def slot_info_from_spec(spec: SlotSpec, holiday: bool) -> SlotInfo:
    return SlotInfo(COLOR_CODE[spec.color(holiday)], spec.label_lines(), spec.cross)
