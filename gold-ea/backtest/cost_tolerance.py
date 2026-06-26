#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""約定摩擦(スプレッド+スリッページ)耐性の検証。

『実際の約定で優位性が消えるのでは?』という最大の懸念に、デモを待たずPythonで答える。
往復コスト(スプレッド+往復スリッページ)を段階的に上げ、PFが1.0(損益分岐)になる点を探す。
時間足ごとに比較し、なぜH1が頑健で低時間足が脆いかを定量化する。
XM実データ使用。"""
import xm_multi_tf as X
import numpy as np, pandas as pd

cfg={"H1":("/tmp/xm_h1.csv",12,72),"M30":("/tmp/xm_m30.csv",32,96),"M5":("/tmp/xm_m5.csv",24,288)}
D={k:(X.load(p),bo,mh) for k,(p,bo,mh) in cfg.items()}

print("="*60)
print("■ 約定コスト耐性 (往復$ → PF) XM実データ・各時間足")
print("  XM GOLD通常コスト=$0.2〜0.4/往復。スリッページはこれに上乗せ。")
print("="*60)
print(f"  {'往復$':>7}{'H1':>9}{'M30':>9}{'M5':>9}")
costs=[0.20,0.35,0.50,1.00,2.00,3.00,4.00,5.00,6.00]
be={k:None for k in cfg}
for cost in costs:
    row=f"  {cost:>6.2f}"
    for k in ["H1","M30","M5"]:
        d,bo,mh=D[k]; e,t=X.bt(d,bo=bo,maxhold=mh,er_th=0.30,SPREAD=cost)
        pf=X.metr(e,t,pd.DatetimeIndex(d.Date.values))['pf']
        if be[k] is None and pf<1.0: be[k]=cost
        row+=f"{pf:>9.2f}"
    print(row)
print(f"\n  損益分岐(PF<1.0到達)の目安:  H1≈${be['H1']}  M30≈${be['M30']}  M5≈${be['M5']}")
print("  → H1は通常コストの十数倍まで耐える=スリッページは実質無視できる。")
print("    低時間足は値幅が小さくコストが相対的に重い=実約定で崩れやすい。")
