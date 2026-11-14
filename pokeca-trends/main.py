"""ポケカ話題まとめ — コマンドライン

使い方:
  python main.py run                 # 今日の 収集→分析→相場→サイト生成 を一括実行
  python main.py demo                # APIキー無しでデモサイトを作る（架空データ・過去14日分）
  python main.py collect [--only x reddit]
  python main.py analyze [--date 2026-11-14] [--offline]
  python main.py market  [--date ...]
  python main.py build
"""
from __future__ import annotations

import argparse
from datetime import date as Date, datetime, timedelta, timezone

from pokeca import pipeline
from pokeca.config import ROOT, get_logger
from pokeca.site import builder

log = get_logger()
JST = timezone(timedelta(hours=9))


def today() -> str:
    return datetime.now(JST).date().isoformat()


def main() -> None:
    ap = argparse.ArgumentParser(description="国内・海外のポケカ話題を自動収集・要約するサイト生成ツール")
    ap.add_argument("command", choices=["run", "collect", "analyze", "market", "build", "demo"])
    ap.add_argument("--date", default=today(), help="対象日 (YYYY-MM-DD、既定は今日 JST)")
    ap.add_argument("--only", nargs="*", help="収集する媒体を限定 (x threads instagram reddit)")
    ap.add_argument("--offline", action="store_true", help="Claude を使わず簡易分析で実行")
    ap.add_argument("--days", type=int, default=14, help="demo で生成する日数")
    a = ap.parse_args()

    if a.command == "collect":
        pipeline.collect(a.date, only=a.only)
    elif a.command == "analyze":
        pipeline.analyze(a.date, force_offline=a.offline)
    elif a.command == "market":
        pipeline.market(a.date, force_offline=a.offline)
    elif a.command == "build":
        builder.build()
    elif a.command == "run":
        pipeline.collect(a.date, only=a.only)
        pipeline.analyze(a.date, force_offline=a.offline)
        pipeline.market(a.date, force_offline=a.offline)
        builder.build()
    elif a.command == "demo":
        from pokeca import db
        db.DB_PATH = ROOT / "data" / "demo.db"   # 本番DBを汚さない
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        end = Date.fromisoformat(a.date)
        # 相場は30日分、話題は --days 日分を古い順に生成
        for i in range(30, -1, -1):
            d = (end - timedelta(days=i)).isoformat()
            if i < a.days:
                pipeline.collect(d, use_demo=True)
                pipeline.analyze(d, force_offline=a.offline)
            pipeline.market(d, use_demo=True, force_offline=True)
        builder.build(demo=True)


if __name__ == "__main__":
    main()
