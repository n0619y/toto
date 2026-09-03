"""当番表のデータモデル.

カレンダー（2枚目 PDF）は「1日 = 3コマ（8:30 / 12:00 / 17:00）」×「メンバー行」で構成され、
各コマは次のいずれかの状態を持つ。

* 1st 当番  … 黄色 (FFFF00)  ラベル "1st"
* 2nd 当番  … 緑   (92D050)  ラベル "2nd"
* 予定あり  … 紫   (B1A0C7)  ラベル = 予定名（外来・休暇・出張先・会議 など）
* 予定 + 当番 … 当番色でラベル = 予定名（例: 外来をしながら 2nd → 緑 "外来", NICU 当直中に 1st → 黄 "NICU"）
* 空き（平日）… 白
* 空き（休日）… 水色 (92CDDC)

コマ指定文字列 (roster.yaml で使用) の文法::

    ""            空き
    "1st" / "2nd" 当番のみ
    "外来"        予定のみ
    "外来/2nd"    予定 + 当番   (表示は予定名, 色は当番色)
    "1st+一般外来当番"  当番 + 補足行 (表示は "1st" の下に補足行)
    "×"           バツ印付きの空きセル
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable

import yaml

SLOT_NAMES = ("AM", "PM", "NIGHT")
SLOT_TIMES = ("8:30", "12:00", "17:00")
WEEKDAY_JA = ("月", "火", "水", "木", "金", "土", "日")
ROLES = ("1st", "2nd")

COLOR_1ST = "FFFF00"
COLOR_2ND = "92D050"
COLOR_EVENT = "B1A0C7"
COLOR_HOLIDAY = "92CDDC"
COLOR_FREE = "FFFFFF"

# 抽出・比較で使う 1 文字コード
COLOR_CODE = {
    COLOR_1ST: "Y",
    COLOR_2ND: "G",
    COLOR_EVENT: "P",
    COLOR_HOLIDAY: "B",
    COLOR_FREE: "W",
}
CODE_COLOR = {v: k for k, v in COLOR_CODE.items()}


@dataclass(frozen=True)
class SlotSpec:
    """1 コマ分の状態."""

    role: str | None = None  # "1st" / "2nd" / None
    event: str | None = None  # 予定名 (紫 or 当番色で表示)
    note: str | None = None  # 当番ラベルの下に付ける補足行
    cross: bool = False  # バツ印

    # ---- 文字列との相互変換 -------------------------------------------------
    @classmethod
    def parse(cls, text: str | None) -> "SlotSpec":
        text = (text or "").strip()
        if text in ("", "-"):
            return cls()
        if text in ("×", "x", "X"):
            return cls(cross=True)
        if "/" in text:
            event, role = text.split("/", 1)
            event, role = event.strip(), role.strip()
            if role not in ROLES:
                raise ValueError(f"当番名が不正です: {text!r}")
            return cls(role=role, event=event or None)
        if "+" in text and text.split("+", 1)[0].strip() in ROLES:
            role, note = text.split("+", 1)
            return cls(role=role.strip(), note=note.strip() or None)
        if text in ROLES:
            return cls(role=text)
        return cls(event=text)

    def to_text(self) -> str:
        if self.cross:
            return "×"
        if self.event and self.role:
            return f"{self.event}/{self.role}"
        if self.event:
            return self.event
        if self.role and self.note:
            return f"{self.role}+{self.note}"
        if self.role:
            return self.role
        return "-"

    # ---- 表示 ---------------------------------------------------------------
    def color(self, holiday: bool) -> str:
        if self.role == "1st":
            return COLOR_1ST
        if self.role == "2nd":
            return COLOR_2ND
        if self.event:
            return COLOR_EVENT
        return COLOR_HOLIDAY if holiday else COLOR_FREE

    def label_lines(self) -> tuple[str, ...]:
        if self.event:
            return (self.event,)
        if self.role:
            return (self.role, self.note) if self.note else (self.role,)
        return ()

    @property
    def is_event_only(self) -> bool:
        return bool(self.event) and self.role is None

    @property
    def is_free(self) -> bool:
        return self.role is None and self.event is None


@dataclass
class Roster:
    """1 か月分の当番表."""

    year: int
    month: int
    members: list[str]
    holidays: set[int] = field(default_factory=set)  # 土日以外の休日（土日は自動）
    title: str = ""
    # days[day][member] = [SlotSpec, SlotSpec, SlotSpec]
    days: dict[int, dict[str, list[SlotSpec]]] = field(default_factory=dict)

    # ---- 基本情報 -----------------------------------------------------------
    @property
    def ndays(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    def date(self, day: int) -> dt.date:
        return dt.date(self.year, self.month, day)

    def is_holiday(self, day: int) -> bool:
        return self.date(day).weekday() >= 5 or day in self.holidays

    def slots(self, day: int, member: str) -> list[SlotSpec]:
        return self.days.setdefault(day, {}).setdefault(member, [SlotSpec(), SlotSpec(), SlotSpec()])

    def set_slot(self, day: int, member: str, slot: int, spec: SlotSpec) -> None:
        self.slots(day, member)[slot] = spec

    def weeks(self) -> list[list[int | None]]:
        """月曜始まりの週ごとの日付リスト (月外は None)."""
        return [
            [d if d != 0 else None for d in week]
            for week in calendar.Calendar(firstweekday=0).monthdayscalendar(self.year, self.month)
        ]

    def default_title(self) -> str:
        return f"Schedule for {calendar.month_name[self.month]} {self.year} (Cardiology)"

    # ---- YAML 入出力 ---------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "Roster":
        y, m = (int(v) for v in str(data["month"]).split("-"))
        roster = cls(
            year=y,
            month=m,
            members=list(data["members"]),
            holidays=set(int(d) for d in data.get("holidays", [])),
            title=data.get("title", "") or "",
        )
        for day, per_member in (data.get("days") or {}).items():
            day = int(day)
            for member, specs in (per_member or {}).items():
                if member not in roster.members:
                    raise ValueError(f"{day}日: 未知のメンバー {member!r}")
                if isinstance(specs, str):
                    specs = [s.strip() for s in specs.split(",")]
                if len(specs) != 3:
                    raise ValueError(f"{day}日 {member}: コマは 3 つ必要です: {specs!r}")
                roster.days.setdefault(day, {})[member] = [SlotSpec.parse(s) for s in specs]
        return roster

    def to_dict(self) -> dict:
        days: dict[int, dict[str, str]] = {}
        for day in range(1, self.ndays + 1):
            row = {}
            for member in self.members:
                specs = self.slots(day, member)
                row[member] = ", ".join(s.to_text() for s in specs)
            days[day] = row
        return {
            "month": f"{self.year:04d}-{self.month:02d}",
            "title": self.title or self.default_title(),
            "members": list(self.members),
            "holidays": sorted(self.holidays),
            "days": days,
        }

    @classmethod
    def load(cls, path: str) -> "Roster":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(dump_yaml(self.to_dict()))


class _Dumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, value: str):  # noqa: ANN001
    if "\n" in value:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


_Dumper.add_representer(str, _str_representer)


def dump_yaml(data: object) -> str:
    return yaml.dump(data, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=200)


# ---- 表示セル（結合済み）の計算 ------------------------------------------------


@dataclass
class Cell:
    """描画用のセル. 週内の連続コマ列 (start..end) を結合したもの."""

    member: str
    week_index: int
    start: int  # 週内コマ番号 0..20 (曜日*3 + コマ)
    end: int  # inclusive
    color: str
    lines: tuple[str, ...]
    cross: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def build_cells(roster: Roster) -> list[Cell]:
    """結合ルールに従って描画セルを生成する.

    * 同じ色・同じ表示文字の隣接コマは結合する
    * 「予定のみ」のセルは日をまたいで結合できる (例: 出張 4日PM〜6日AM)
    * 当番セルは同じ日の中でのみ結合する
    * 空きセル (白 / 水色) は結合しない (バツ印付きの空きセル同士は結合する)
    """
    cells: list[Cell] = []
    for wi, week in enumerate(roster.weeks()):
        for member in roster.members:
            run: Cell | None = None
            run_day: int | None = None
            run_event_only = False
            for di, day in enumerate(week):
                for si in range(3):
                    idx = di * 3 + si
                    if day is None:
                        # 月外セル: 土日は水色, 平日は白
                        wd = di
                        color = COLOR_HOLIDAY if wd >= 5 else COLOR_FREE
                        cells.append(Cell(member, wi, idx, idx, color, ()))
                        run = None
                        continue
                    spec = roster.slots(day, member)[si]
                    color = spec.color(roster.is_holiday(day))
                    lines = spec.label_lines()
                    mergeable = bool(lines) or spec.cross
                    if (
                        run is not None
                        and mergeable
                        and run.color == color
                        and run.lines == lines
                        and run.cross == spec.cross
                        and run.end == idx - 1
                        and (run_day == day or (run_event_only and spec.is_event_only))
                    ):
                        run.end = idx
                        continue
                    cell = Cell(member, wi, idx, idx, color, lines, cross=spec.cross)
                    cells.append(cell)
                    run = cell if mergeable else None
                    run_day = day
                    run_event_only = spec.is_event_only
    return cells


def iter_slots(roster: Roster) -> Iterable[tuple[int, str, int, SlotSpec]]:
    for day in range(1, roster.ndays + 1):
        for member in roster.members:
            for si, spec in enumerate(roster.slots(day, member)):
                yield day, member, si, spec
