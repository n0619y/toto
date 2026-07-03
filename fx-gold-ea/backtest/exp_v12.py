#!/usr/bin/env python3
"""v1.2改善フィルターの効果測定実験。

balanced_long をベースに、各フィルターの単独/組み合わせ効果を
In-Sample (〜2024-12) / Out-of-Sample (2025〜) / 全期間 で比較する。
採用判断はIS改善を主基準とし、OOSが崩れないことを確認する。
"""
import pandas as pd

from gold_backtest import Backtester, build_params, load_csv, summarize

FEATURES = {
    "baseline":    {},
    "+MTF":        dict(use_mtf=True),
    "+ATRexp":     dict(use_atr_expansion=True),
    "+BE":         dict(use_breakeven=True),
    "+MTF+BE":     dict(use_mtf=True, use_breakeven=True),
    "+MTF+ATRexp": dict(use_mtf=True, use_atr_expansion=True),
    "+ALL":        dict(use_mtf=True, use_atr_expansion=True, use_breakeven=True),
}
SPLIT = pd.Timestamp("2025-01-01")

def run(df, **feat):
    p = build_params("balanced_long")
    for k, v in feat.items():
        setattr(p, k, v)
    return summarize(Backtester(df, p).run())

def main():
    for tf, path in [("H4", "data/GOLD240.csv"), ("H1", "data/GOLD60.csv")]:
        df = load_csv(path)
        segments = {"IS": df[df.index < SPLIT], "OOS": df[df.index >= SPLIT], "FULL": df}
        rows = []
        for name, feat in FEATURES.items():
            row = {"構成": name}
            for seg, d in segments.items():
                s = run(d, **feat)
                row[f"{seg}リターン%"] = s["リターン(%)"]
                row[f"{seg}PF"] = s["プロフィットファクター"]
                row[f"{seg}DD%"] = s["最大ドローダウン(%)"]
                if seg == "FULL":
                    row["FULL取引数"] = s["取引回数"]
                    row["FULLシャープ"] = s["シャープレシオ"]
            rows.append(row)
        table = pd.DataFrame(rows)
        print(f"\n########## {tf} (balanced_longベース) ##########")
        print(table.to_string(index=False))
        table.to_csv(f"results/exp_v12_{tf}.csv", index=False)

if __name__ == "__main__":
    main()
