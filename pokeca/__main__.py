"""使い方:
  python -m pokeca prices import 買取表.csv          買取表を取り込む
  python -m pokeca recommend [--out 推奨.csv]        推奨仕入れ上限の一覧
  python -m pokeca stock add SET 番号 名前 仕入れ値 [--from 店] [--on 日付]
  python -m pokeca stock list [--status 在庫]
  python -m pokeca stock set ID [--status ..] [--grade PSA10] [--cert ..] [--sold-to 店 --sold-price 円]
  python -m pokeca psa-export [--out 依頼.csv] [--mark 注文番号]   鑑定に出す在庫の一覧
  python -m pokeca sell-plan                         在庫ごとの最高値の買取店
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .core import best_offers, per_card_costs, recommend, sell_plan
from .db import DB, STATUSES

ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: str | None, rows: list[dict]) -> None:
    if not rows:
        print("該当なし")
        return
    f = open(path, "w", encoding="utf-8-sig", newline="") if path else sys.stdout
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    if path:
        f.close()
        print(f"{len(rows)}件を {path} に書き出しました")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pokeca")
    p.add_argument("--db", default=str(ROOT / "data" / "pokeca.db"))
    p.add_argument("--config", default=str(ROOT / "config" / "pokeca.yaml"))
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("prices").add_subparsers(dest="sub", required=True).add_parser("import")
    pr.add_argument("csv")
    pr.add_argument("--day")

    rec = sub.add_parser("recommend")
    rec.add_argument("--out")

    st = sub.add_parser("stock").add_subparsers(dest="sub", required=True)
    add = st.add_parser("add")
    for a in ("set_code", "number", "name"):
        add.add_argument(a)
    add.add_argument("buy_price", type=float)
    add.add_argument("--from", dest="bought_from", default="")
    add.add_argument("--on")
    ls = st.add_parser("list")
    ls.add_argument("--status", choices=STATUSES)
    se = st.add_parser("set")
    se.add_argument("id", type=int)
    se.add_argument("--status", choices=STATUSES)
    for a in ("grade", "cert", "psa-order", "sold-to", "sold-on"):
        se.add_argument(f"--{a}")
    se.add_argument("--sold-price", type=float)

    ex = sub.add_parser("psa-export")
    ex.add_argument("--out")
    ex.add_argument("--mark", metavar="注文番号", help="書き出した在庫を「鑑定中」にし、費用を按分して記録する")

    sub.add_parser("sell-plan")
    args = p.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    db = DB(args.db)
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()

    if args.cmd == "prices":
        print(f"{db.import_prices(args.csv, args.day or today)}行を取り込みました")
    elif args.cmd == "recommend":
        best = best_offers(db.latest_prices())
        rows = [r for r in (recommend(c, best, cfg) for c in sorted({k[0] for k in best})) if r]
        rows.sort(key=lambda r: -r["max_buy"])
        write_csv(args.out, [{k: (round(v) if isinstance(v, float) else v) for k, v in r.items()} for r in rows])
    elif args.cmd == "stock" and args.sub == "add":
        i = db.add_stock(args.set_code, args.number, args.name, args.buy_price, args.on or today, args.bought_from)
        print(f"在庫ID {i} で登録しました")
    elif args.cmd == "stock" and args.sub == "list":
        write_csv(None, db.stock(args.status))
    elif args.cmd == "stock" and args.sub == "set":
        fields = {k: v for k, v in {
            "status": args.status, "grade": args.grade, "cert": args.cert, "psa_order": args.psa_order,
            "sold_to": args.sold_to, "sold_on": args.sold_on, "sold_price": args.sold_price}.items() if v is not None}
        if not fields:
            p.error("変更する項目を指定してください")
        db.update_stock(args.id, **fields)
        print(f"在庫ID {args.id} を更新しました")
    elif args.cmd == "psa-export":
        best = best_offers(db.latest_prices())
        items = [s for s in db.stock("在庫") if s["grade"] == "RAW"]
        rows = [{
            "stock_id": s["id"], "card_key": s["card_key"], "name": s["name"],
            # 申告価額の目安: PSA10 の最高買取（無ければ仕入れ値）をドル換算
            "declared_value_usd": round(best.get((s["card_key"], "PSA10"), {}).get("price", s["buy_price"]) / float(cfg["usd_jpy"])),
        } for s in items]
        write_csv(args.out, rows)
        if args.mark:
            cost = per_card_costs(cfg).total
            for s in items:
                db.update_stock(s["id"], status="鑑定中", psa_order=args.mark, extra_cost=s["extra_cost"] + cost)
            print(f"{len(items)}件を鑑定中（注文 {args.mark}）にしました")
    elif args.cmd == "sell-plan":
        best = best_offers(db.latest_prices())
        items = [s for s in db.stock() if s["status"] in ("在庫", "返却済")]
        plan = sell_plan(items, best)
        write_csv(None, [{k: r[k] for k in ("id", "name", "grade", "cost_basis", "shop", "price", "profit")} for r in plan])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
