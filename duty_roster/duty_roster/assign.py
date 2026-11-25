"""1st / 2nd call の自動割り当て.

参考 (2026-10 ver.2, 2026-11 の完成版) から読み取った運用:

* 1st / 2nd を担当するのは callers (既定: 仲本, 佐々木) のみ。
* 各コマ (AM / PM / 夜) に 1st は 1 人。もう 1 人は手が空いていれば 2nd。
* 当直 (夜) の人はその日の AM / PM / 夜すべて 1st を兼務 (夜のセルは "NICU/1st" のように当直名を表示)。
  日直 (昼) の人は AM / PM に加えて夜も 1st (相手が当直なら夜は相手)。
* 当直の翌日は原則 1st を避ける (相手が空いていれば相手が 1st)。
* 外勤・外来・休暇などの予定が最優先。そのコマは 1st にも 2nd にもならない。
  両者とも予定があれば 1st は空白。
* 「休み」「私用」は 1st にはならないが 2nd には入る (11 月の運用に合わせる)。無印なら夜も同じ扱い。
* 心臓カテーテル・検査 (院内) は 1st / 2nd を妨げない。当番が付いたコマは当番だけを表示する (参考と同じ)。
* 「1st不可」はその日 1st にしない。「○○前日」は夜の 1st を避ける (相手が居なければ入る)。
* 1st の回数は平等に。休日 (土日祝) のコマは 1.3 倍で数える。
* 同じ日の中ではなるべく同じ人が 1st を続ける (日単位のブロック)。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Roster, SlotSpec
from .parse_plan import Plan
from .skeleton import parse_event, split_top_level

SOFT_OFF = {"休み", "私用", "休暇"}  # 1st にはならないが 2nd には入れる予定名 (無印なら終日)
IN_HOUSE = {"心臓カテーテル", "検査"}  # 院内業務: 1st / 2nd を妨げない (当番が付けば表示は当番のみ)
HOLIDAY_WEIGHT = 1.3
POST_DUTY_PENALTY = 2.0  # 当直翌日に 1st を選ぶときのスコア加算
CONTINUITY_BONUS = 0.5  # 前日と同じ人を主担当にするときのスコア加算 (= 交代を促す)

FREE, SOFT, BUSY, DUTY = "free", "soft", "busy", "duty"


@dataclass
class DayAvail:
    kind: list[str] = field(default_factory=lambda: [FREE, FREE, FREE])  # free / soft / busy / duty
    duty_label: list[str | None] = field(default_factory=lambda: [None, None, None])
    no_first: bool = False  # 1st不可
    avoid_night: bool = False  # ○○前日
    notes: list[str] = field(default_factory=list)


@dataclass
class AssignReport:
    blanks: list[tuple[int, int]] = field(default_factory=list)  # (day, slot) 1st なし
    discouraged: list[tuple[int, int, str, str]] = field(default_factory=list)  # (day, slot, member, reason)
    weighted: dict[str, float] = field(default_factory=dict)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)


def availability(plan: Plan, roster: Roster, callers: list[str], aliases: dict[str, str] | None) -> dict[tuple[int, str], DayAvail]:
    out: dict[tuple[int, str], DayAvail] = {}
    for day in range(1, roster.last_day + 1):
        row = plan.days.get(day) or {}
        for m in callers:
            av = DayAvail()
            for item in split_top_level(row.get(m, "") or ""):
                ev = parse_event(item, aliases)
                if ev.unavailable_night:
                    av.avoid_night = True
                    av.notes.append(item)
                    continue
                if ev.note_only:
                    if "不可" in ev.name:
                        av.no_first = True
                    av.notes.append(item)
                    continue
                if ev.duty:
                    for s in ev.slots:
                        av.kind[s] = DUTY
                        av.duty_label[s] = ev.label
                    continue
                if ev.name in IN_HOUSE:
                    continue
                k = SOFT if ev.name in SOFT_OFF else BUSY
                slots = [0, 1, 2] if (k == SOFT and ev.qualifier is None) else ev.slots
                for s in slots:
                    if av.kind[s] == DUTY:
                        continue
                    if av.kind[s] == BUSY and k == SOFT:
                        continue
                    av.kind[s] = k
            out[(day, m)] = av
    return out


def assign(
    plan: Plan,
    skeleton: Roster,
    callers: list[str],
    aliases: dict[str, str] | None = None,
) -> tuple[Roster, AssignReport]:
    """skeleton (予定だけの roster) に 1st / 2nd を書き込んだ新しい Roster と、割り当てレポートを返す."""
    roster = Roster(
        skeleton.year, skeleton.month, list(skeleton.members), set(skeleton.holidays), skeleton.title, extra_days=skeleton.extra_days
    )
    for day in range(1, skeleton.last_day + 1):
        for m in skeleton.members:
            roster.days.setdefault(day, {})[m] = list(skeleton.slots(day, m))

    av = availability(plan, roster, callers, aliases)
    report = AssignReport()
    weighted = {m: 0.0 for m in callers}
    counts = {m: {"1st": 0, "2nd": 0, "1st_holiday": 0} for m in callers}
    night_duty_yesterday: set[str] = set()
    primary_yesterday: str | None = None

    for day in range(1, roster.last_day + 1):
        holiday = roster.is_holiday(day)
        w = HOLIDAY_WEIGHT if holiday else 1.0

        # ---- 1st の適性 (小さいほど良い). -1 = 強制, 0 = 良, 1 = 避けたい, 2 = 不可
        level: dict[tuple[str, int], int] = {}
        reason: dict[tuple[str, int], str] = {}
        for m in callers:
            a = av[(day, m)]
            for s in range(3):
                k = a.kind[s]
                if k == DUTY:
                    level[(m, s)] = -1
                elif k in (BUSY, SOFT) or a.no_first:
                    level[(m, s)] = 2
                elif s < 2 and m in night_duty_yesterday:
                    level[(m, s)] = 1
                    reason[(m, s)] = "当直翌日"
                elif s == 2 and a.avoid_night:
                    level[(m, s)] = 1
                    reason[(m, s)] = "翌日出張 (前日)"
                else:
                    level[(m, s)] = 0
        # 当直 (夜) の人は昼も、日直 (昼) の人は夜も 1st を兼務 (相手が当直で強制されていなければ)
        for m in callers:
            a = av[(day, m)]
            others = [o for o in callers if o != m]
            if a.kind[2] == DUTY:
                for s in (0, 1):
                    if level[(m, s)] <= 1 and not any(level[(o, s)] == -1 for o in others):
                        level[(m, s)] = -1
            if a.kind[0] == DUTY or a.kind[1] == DUTY:
                if level[(m, 2)] == 0 and not any(level[(o, 2)] == -1 for o in others):
                    level[(m, 2)] = -1

        # ---- 主担当 (その日の自由なコマを誰が 1st で受けるか)
        forced = {m: sum(1 for s in range(3) if level[(m, s)] == -1) for m in callers}
        if any(forced.values()):
            primary = max(callers, key=lambda m: (forced[m], -weighted[m]))
        else:

            def score(m: str) -> float:
                sc = weighted[m]
                if m in night_duty_yesterday:
                    sc += POST_DUTY_PENALTY
                if m == primary_yesterday:
                    sc += CONTINUITY_BONUS
                return sc

            primary = min(callers, key=score)

        firsts: dict[int, str | None] = {}
        prev: str | None = None  # 同じ日の直前のコマの 1st (続けて担当する)
        for s in range(3):
            cands = [m for m in callers if level[(m, s)] <= 1]
            if not cands:
                firsts[s] = None
                report.blanks.append((day, s))
                continue
            best = min(level[(m, s)] for m in cands)
            if best == -1:
                chosen = [m for m in cands if level[(m, s)] == -1][0]
            else:
                tier = [m for m in cands if level[(m, s)] == best]
                if prev in tier:
                    chosen = prev
                elif primary in tier:
                    chosen = primary
                else:
                    chosen = min(tier, key=lambda m: weighted[m])
                if best == 1:
                    report.discouraged.append((day, s, chosen, reason.get((chosen, s), "")))
            firsts[s] = chosen
            prev = chosen

        # ---- 書き込み
        for s in range(3):
            first = firsts[s]
            for m in callers:
                a = av[(day, m)]
                k = a.kind[s]
                if m == first:
                    label = a.duty_label[s] if k == DUTY else None
                    roster.set_slot(day, m, s, SlotSpec(role="1st", event=label))
                    weighted[m] += w
                    counts[m]["1st"] += 1
                    if holiday:
                        counts[m]["1st_holiday"] += 1
                elif k in (FREE, SOFT):
                    roster.set_slot(day, m, s, SlotSpec(role="2nd"))
                    counts[m]["2nd"] += 1
                # BUSY / DUTY (1st でない) は skeleton の予定表示のまま

        night_duty_yesterday = {m for m in callers if av[(day, m)].kind[2] == DUTY}
        tally = {m: sum(1 for s in range(3) if firsts[s] == m) for m in callers}
        primary_yesterday = max(callers, key=lambda m: tally[m]) if any(tally.values()) else primary_yesterday

    report.weighted = weighted
    report.counts = counts
    return roster, report


def format_report(roster: Roster, report: AssignReport, callers: list[str]) -> str:
    from .model import SLOT_NAMES

    lines = [f"== {roster.year}-{roster.month:02d} 1st/2nd 割り当て =="]
    lines.append("メンバー | 1st コマ数 | うち休日 | 休日1.3倍の重み | 2nd コマ数")
    for m in callers:
        c = report.counts[m]
        lines.append(f"{m} | {c['1st']} | {c['1st_holiday']} | {report.weighted[m]:.1f} | {c['2nd']}")
    if report.blanks:
        lines.append("")
        lines.append(f"1st が空白のコマ ({len(report.blanks)}): " + ", ".join(f"{roster.day_label(d)} {SLOT_NAMES[s]}" for d, s in report.blanks))
    if report.discouraged:
        lines.append("")
        lines.append("原則に反して 1st にしたコマ (相手が空いていないため):")
        for d, s, m, why in report.discouraged:
            lines.append(f"  {roster.day_label(d)} {SLOT_NAMES[s]}: {m} ({why})")
    return "\n".join(lines)


def apply_overrides(roster: Roster, path: str) -> list[str]:
    """手修正ファイル (overrides.yaml) を roster に適用する. 戻り値は適用内容の説明."""
    import yaml

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    applied: list[str] = []
    for key, per_member in (data.get("days") or {}).items():
        day = roster.parse_day_key(key)
        for member, text in (per_member or {}).items():
            parts = [t.strip() for t in str(text).split(",")]
            if len(parts) != 3:
                raise ValueError(f"overrides {key} {member}: コマは 3 つ必要です: {text!r}")
            for s, t in enumerate(parts):
                if t in ("=", ""):
                    continue
                roster.set_slot(day, member, s, SlotSpec.parse(t))
                applied.append(f"{roster.day_label(day)} {['AM', 'PM', '夜'][s]} {member} → {t}")
    return applied
