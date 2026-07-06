#!/usr/bin/env python3
"""GoldTrendRider エンジン検証スイート。

合成データ(複数シード) x 両プリセットでバックテストを回し、
ロバスト性サマリーと感度分析を results/ に出力する。

※合成データはエンジンの動作検証用。実際の市場成績を示すものではない。
実データ検証は: python3 gold_backtest.py --csv <MT4エクスポートCSV> --preset aggressive
"""
import os

import pandas as pd

from gold_backtest import (Backtester, build_params, plot_equity,
                           summarize, synthetic_gold_h1)

OUTDIR = "results"
SEEDS = [7, 42, 123, 2024, 9999]
YEARS = 5.0

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    rows = []
    for preset in ("aggressive", "conservative"):
        for seed in SEEDS:
            df = synthetic_gold_h1(YEARS, seed)
            p = build_params(preset)
            bt = Backtester(df, p).run()
            s = summarize(bt)
            rows.append({
                "プリセット": preset, "シード": seed,
                "リターン%": s["リターン(%)"], "CAGR%": s["年率リターン(CAGR%)"],
                "PF": s["プロフィットファクター"], "勝率%": s["勝率(%)"],
                "最大DD%": s["最大ドローダウン(%)"], "取引数": s["取引回数"],
                "シャープ": s["シャープレシオ"], "DD停止": s["DD停止発動"],
            })
            if seed == SEEDS[1]:  # 代表シードのみ資金曲線を保存
                plot_equity(bt, os.path.join(OUTDIR, f"equity_{preset}_seed{seed}.png"),
                            f"GoldTrendRider [{preset}] synthetic {YEARS:.0f}y seed={seed} (validation only)")
            print(f"{preset} seed={seed}: return={s['リターン(%)']}% PF={s['プロフィットファクター']} "
                  f"DD={s['最大ドローダウン(%)']}% trades={s['取引回数']} halt={s['DD停止発動']}")

    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(OUTDIR, "validation_summary.csv"), index=False)
    print("\n=== サマリー ===")
    print(table.to_string(index=False))

    agg = table.groupby("プリセット")[["リターン%", "PF", "最大DD%", "勝率%", "取引数"]].agg(["median", "min", "max"])
    print("\n=== プリセット別 中央値/最小/最大 ===")
    print(agg.to_string())
    agg.to_csv(os.path.join(OUTDIR, "validation_agg.csv"))

if __name__ == "__main__":
    main()
