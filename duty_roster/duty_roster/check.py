"""当番表の集計と整合性チェック (自動割り当てのルール抽出にも使う)."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .model import SLOT_NAMES, Roster


@dataclass
class Stats:
    warnings: list[str] = field(default_factory=list)
    # 人 × 種別 (1st / 2nd) × 区分 (weekday_day / weekday_night / holiday) のコマ数
    counts: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    # 人 × 予定名 のコマ数
    events: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    per_slot: list[tuple[int, int, list[str], list[str]]] = field(default_factory=list)  # (day, slot, 1st達, 2nd達)


def analyze(roster: Roster) -> Stats:
    st = Stats()
    for day in range(1, roster.ndays + 1):
        holiday = roster.is_holiday(day)
        for si in range(3):
            firsts, seconds = [], []
            for member in roster.members:
                spec = roster.slots(day, member)[si]
                if spec.role == "1st":
                    firsts.append(member)
                elif spec.role == "2nd":
                    seconds.append(member)
                if spec.role:
                    cat = "holiday" if holiday else ("weekday_night" if si == 2 else "weekday_day")
                    st.counts[member][f"{spec.role}/{cat}"] += 1
                    st.counts[member][spec.role] += 1
                if spec.event:
                    st.events[member][spec.event] += 1
            st.per_slot.append((day, si, firsts, seconds))
            where = f"{day:2d}日 {SLOT_NAMES[si]}"
            # 時間で分担した 1st (例: "1st+(～19時)" と "1st+(19時～)") は 1 人扱い
            timed = [m for m in firsts if (roster.slots(day, m)[si].note or "").find("時") >= 0]
            effective = len(firsts) - len(timed) + (1 if timed else 0)
            if effective != 1:
                st.warnings.append(f"{where}: 1st が {len(firsts)} 人 ({', '.join(firsts) or 'なし'})")
            if len(seconds) > 1:
                st.warnings.append(f"{where}: 2nd が {len(seconds)} 人 ({', '.join(seconds)})")
            if set(firsts) & set(seconds):
                st.warnings.append(f"{where}: 同じ人が 1st と 2nd")
    return st


def format_stats(roster: Roster, st: Stats) -> str:
    lines = [f"== {roster.year}-{roster.month:02d} 集計 =="]
    header = ["メンバー", "1st計", "2nd計", "1st平日昼", "1st平日夜", "1st休日", "2nd平日昼", "2nd平日夜", "2nd休日"]
    lines.append(" | ".join(header))
    for m in roster.members:
        c = st.counts[m]
        lines.append(
            " | ".join(
                str(v)
                for v in (
                    m,
                    c["1st"],
                    c["2nd"],
                    c["1st/weekday_day"],
                    c["1st/weekday_night"],
                    c["1st/holiday"],
                    c["2nd/weekday_day"],
                    c["2nd/weekday_night"],
                    c["2nd/holiday"],
                )
            )
        )
    lines.append("")
    lines.append("予定コマ数:")
    for m in roster.members:
        ev = ", ".join(f"{k}×{v}" for k, v in st.events[m].most_common())
        lines.append(f"  {m}: {ev or '-'}")
    lines.append("")
    if st.warnings:
        lines.append(f"注意 ({len(st.warnings)} 件):")
        lines.extend("  " + w for w in st.warnings)
    else:
        lines.append("注意: なし (全コマに 1st が 1 人, 2nd は 0〜1 人)")
    return "\n".join(lines)
