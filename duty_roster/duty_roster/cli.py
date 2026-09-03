"""コマンドラインインターフェース.

    python -m duty_roster parse-plan samples/Schedule_202609_plan.pdf --month 2026-09 -o data/2026-09/plan.yaml
    python -m duty_roster skeleton data/2026-09/plan.yaml -o data/2026-09/roster_skeleton.yaml
    python -m duty_roster extract samples/Sep_2026_1_calendar.pdf --month 2026-09 -o data/2026-09/roster.yaml
    python -m duty_roster render data/2026-09/roster.yaml -o output/2026-09/Schedule_2026-09   (.pdf と .xlsx)
    python -m duty_roster verify output/2026-09/Schedule_2026-09.pdf samples/Sep_2026_1_calendar.pdf
    python -m duty_roster check data/2026-09/roster.yaml
"""

from __future__ import annotations

import argparse
import sys

from .check import analyze, format_stats
from .compare import compare_calendars, compare_roster_to_calendar, roster_from_calendar
from .extract_calendar import extract_calendar
from .model import Roster
from .parse_plan import load_plan
from .render_pdf import PdfStyle, render_pdf
from .render_xlsx import save_xlsx, xlsx_to_pdf
from .skeleton import build_skeleton, skeleton_yaml


def _month(s: str) -> tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


def cmd_parse_plan(a: argparse.Namespace) -> int:
    y, m = _month(a.month) if a.month else (None, None)
    plan = load_plan(a.input, y, m)
    plan.save(a.output)
    print(f"予定一覧を読み込みました: {len(plan.members)} 名, 休日 {sorted(plan.holidays)} → {a.output}")
    return 0


def cmd_skeleton(a: argparse.Namespace) -> int:
    y, m = _month(a.month) if a.month else (None, None)
    plan = load_plan(a.input, y, m)
    roster, comments = build_skeleton(plan)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(skeleton_yaml(roster, comments))
    print(f"雛形を書き出しました: {a.output}  (予定だけ入っています。1st / 2nd を埋めてください)")
    return 0


def cmd_extract(a: argparse.Namespace) -> int:
    y, m = _month(a.month)
    cal = extract_calendar(a.input)
    roster = roster_from_calendar(cal, y, m)
    roster.save(a.output)
    print(f"カレンダー PDF から roster を起こしました: {a.output}")
    return 0


def cmd_render(a: argparse.Namespace) -> int:
    roster = Roster.load(a.roster)
    base = a.output
    for ext in (".pdf", ".xlsx"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
    made = []
    if not a.no_pdf:
        style = PdfStyle(font_file=a.font) if a.font else None
        made.append(render_pdf(roster, base + ".pdf", style))
    if not a.no_xlsx:
        made.append(save_xlsx(roster, base + ".xlsx"))
        if a.xlsx_pdf:
            made.append(xlsx_to_pdf(base + ".xlsx", base + "_xlsx.pdf"))
    print("出力:", *made, sep="\n  ")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    expected = extract_calendar(a.expected)
    if a.generated.lower().endswith((".yaml", ".yml")):
        diffs = compare_roster_to_calendar(Roster.load(a.generated), expected)
    else:
        diffs = compare_calendars(expected, extract_calendar(a.generated))
    if diffs:
        print(f"差分 {len(diffs)} 件:")
        for d in diffs:
            print("  " + str(d))
        return 1
    print("差分なし: 全コマの色・文字が一致しました")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    roster = Roster.load(a.roster)
    st = analyze(roster)
    print(format_stats(roster, st))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="duty_roster", description="グループ当番表 (月間スケジュール) 作成ツール")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("parse-plan", help="予定一覧 (PDF/xlsx) → plan.yaml")
    s.add_argument("input")
    s.add_argument("--month", help="YYYY-MM (PDF/xlsx のとき必須)")
    s.add_argument("-o", "--output", required=True)
    s.set_defaults(func=cmd_parse_plan)

    s = sub.add_parser("skeleton", help="plan → 予定だけ入れた roster 雛形")
    s.add_argument("input", help="plan.yaml または予定一覧 PDF/xlsx")
    s.add_argument("--month")
    s.add_argument("-o", "--output", required=True)
    s.set_defaults(func=cmd_skeleton)

    s = sub.add_parser("extract", help="カレンダー PDF → roster.yaml")
    s.add_argument("input")
    s.add_argument("--month", required=True)
    s.add_argument("-o", "--output", required=True)
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("render", help="roster.yaml → PDF / xlsx")
    s.add_argument("roster")
    s.add_argument("-o", "--output", required=True, help="出力ファイル名 (拡張子なし可)")
    s.add_argument("--no-pdf", action="store_true")
    s.add_argument("--no-xlsx", action="store_true")
    s.add_argument("--xlsx-pdf", action="store_true", help="LibreOffice で xlsx からも PDF を作る")
    s.add_argument("--font", help="PDF 用日本語フォントファイル (.ttf)")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("verify", help="生成物 (PDF または roster.yaml) を元カレンダー PDF と比較")
    s.add_argument("generated")
    s.add_argument("expected")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("check", help="roster の集計と整合性チェック")
    s.add_argument("roster")
    s.set_defaults(func=cmd_check)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
