#!/usr/bin/env python3
"""v1.3候補の改善レバー検証 + 頑健性検査。

v12_h4_long (H4/買い専用/ATR拡大) をベースに:
  A. セッションフィルター有無
  B. リスク% 引き上げ余地
  C. 増し玉リスク逓減
  D. ADXしきい値の頑健性
  E. ドンチャン期間の頑健性
  F. コスト(スプレッド)感度
  G. モンテカルロDD分析 (トレード順序リシャッフル)
"""
import numpy as np
import pandas as pd

from gold_backtest import Backtester, build_params, load_csv, summarize

SPLIT = pd.Timestamp("2025-01-01")
df = load_csv("data/GOLD240.csv")
SEGS = {"IS": df[df.index < SPLIT], "OOS": df[df.index >= SPLIT], "FULL": df}

def run(seg, **over):
    p = build_params("v12_h4_long")
    for k, v in over.items():
        setattr(p, k, v)
    bt = Backtester(SEGS[seg], p).run()
    return summarize(bt), bt

def line(label, **over):
    parts = [f"{label:<28}"]
    for seg in ("IS", "OOS", "FULL"):
        s, _ = run(seg, **over)
        parts.append(f"{seg}: {s['リターン(%)']:>7}% PF{s['プロフィットファクター']:<5} DD{s['最大ドローダウン(%)']:>5}%")
    print(" | ".join(parts))

print("=== A. セッションフィルター (H4) ===")
line("session 7-21 (現行)")
line("session なし", use_session=False)

print("\n=== B. リスク% (現行1.5) ===")
for r in (1.5, 2.0, 2.5):
    line(f"risk={r}", risk_percent=r)

print("\n=== C. 増し玉リスク逓減 (現行1.0=等倍) ===")
for s in (1.0, 0.7, 0.5):
    line(f"pyramid_scale={s}", pyramid_risk_scale=s)

print("\n=== D. ADXしきい値の頑健性 (現行20) ===")
for a in (15, 20, 25, 30):
    line(f"adx>={a}", adx_threshold=float(a))

print("\n=== E. ドンチャン期間の頑健性 (現行20) ===")
for d in (15, 20, 25, 30):
    line(f"donchian={d}", donchian=d)

print("\n=== F. コスト感度 (現行スプレッド$0.35) ===")
for sp in (0.35, 0.50, 0.70, 1.00):
    line(f"spread=${sp}", spread_usd=sp)

print("\n=== G. モンテカルロDD分析 (FULL, トレード順序10000回リシャッフル) ===")
s, bt = run("FULL")
rets = np.array([t.pnl for t in bt.trades], dtype=float)
rng = np.random.default_rng(0)
max_dds = []
for _ in range(10000):
    seq = rng.permutation(rets)
    # 定率リスクの近似としてPnLを資金比に変換して複利適用
    eq = 10000 * np.cumprod(1 + seq / 10000)
    peak = np.maximum.accumulate(eq)
    max_dds.append(((peak - eq) / peak).max() * 100)
max_dds = np.array(max_dds)
print(f"  実測DD: {s['最大ドローダウン(%)']}%")
print(f"  モンテカルロDD分布: 中央値 {np.median(max_dds):.1f}% / 90%タイル {np.percentile(max_dds, 90):.1f}% / 99%タイル {np.percentile(max_dds, 99):.1f}%")
print(f"  (同じトレード群でも並び順次第でここまでのDDは覚悟が必要)")
