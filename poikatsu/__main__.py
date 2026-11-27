"""使い方:
  python -m poikatsu run [--demo] [--no-llm]   今日の朝報を作る
  python -m poikatsu done all | ID [ID ...]    完了を記録する
  python -m poikatsu stats                     今月の実績
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import report
from .agents import CEO, DayContext
from .llm import LLM
from .store import Store

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="poikatsu")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--demo", action="store_true", help="サンプル案件で流れを確認（台帳は汚さない）")
    run.add_argument("--no-llm", action="store_true", help="Claude を使わずルールだけで動かす")
    run.add_argument("--config", default=str(ROOT / "config" / "poikatsu.yaml"))
    done = sub.add_parser("done")
    done.add_argument("ids", nargs="+")
    done.add_argument("--yen", type=float, help="実際に得た円相当（省略時は見積り値）")
    sub.add_parser("stats")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    db_path = ROOT / "data" / "poikatsu.db"

    if args.cmd == "done":
        n = Store(db_path).mark_done(args.ids, today.isoformat(), args.yen)
        print(f"{n}件を完了として記録しました")
        return 0
    if args.cmd == "stats":
        store = Store(db_path)
        n, yen = store.month_total(today.strftime("%Y-%m"))
        gn, gyen = store.month_grants(today.strftime("%Y-%m"))
        print(f"{today:%Y-%m}: 完了 {n}件・約{yen:.0f}円相当 / メールで付与確認 {gn}件・約{gyen:.0f}円相当")
        return 0

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    ctx = DayContext(
        today=today, cfg=cfg, demo=args.demo,
        store=Store(":memory:" if args.demo else db_path),
        llm=LLM(enabled=not args.no_llm),
    )
    opps, _ = CEO().run_day(ctx)

    out_dir = ROOT / "output" / "poikatsu"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{today.isoformat()}{'_demo' if args.demo else ''}"
    md = report.to_markdown(ctx, opps)
    html_body = report.to_html(ctx, opps)
    (out_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    (out_dir / f"{stem}.html").write_text(html_body, encoding="utf-8")
    print(md)
    if not args.demo:
        try:
            if report.send_mail(f"ポイ活朝報 {today}", html_body):
                print("朝報をメール送信しました")
        except Exception as exc:
            print(f"警告: 朝報メールの送信に失敗しました ({exc})")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
