#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最重要の頑健性チェック: コスト感応度 と SL/トレール近傍の安定性(OOS)。
エッジが非現実的な低コストの中だけで生きていないかを確認する。"""
import numpy as np, pandas as pd

h=pd.read_csv("/tmp/xau_h1.csv")
h["Date"]=pd.to_datetime(h["Date"])
for c in ["open","high","low","close"]: h[c]=h[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean(); h["atr_med"]=h.atr.rolling(200).median()
OOS=h.iloc[int(len(h)*0.6):].reset_index(drop=True)
INIT=1000.0; RISK=0.01

def bt(df,bo=12,sl_atr=2.0,trail=3.0,spread=0.35,maxhold=72):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;atr=df.atr.values;am=df.atr_med.values
    rh=df.high.rolling(bo).max().shift(1).values; rl=df.low.rolling(bo).min().shift(1).values
    eq=INIT;pos=0;entry=stop=lots=0.0;peak=0.0;hold=0;tr_=[]
    for i in range(len(df)):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(am[i]) or np.isnan(rh[i]): continue
        if pos!=0:
            hold+=1
            if pos>0:
                peak=max(peak,hi[i]);stop=max(stop,peak-trail*atr[i])
                if lo[i]<=stop: g=(stop-entry)*lots*100-spread*100*lots;eq+=g;tr_.append(g);pos=0;hold=0
            else:
                peak=min(peak,lo[i]);stop=min(stop,peak+trail*atr[i])
                if hi[i]>=stop: g=(entry-stop)*lots*100-spread*100*lots;eq+=g;tr_.append(g);pos=0;hold=0
            if pos!=0 and hold>=maxhold:
                px=cl[i];g=((px-entry) if pos>0 else (entry-px))*lots*100-spread*100*lots;eq+=g;tr_.append(g);pos=0;hold=0
        if pos==0:
            sd=sl_atr*atr[i]; lc=max(round(eq*RISK/(sd*100),2),0.0) if sd>0 else 0
            if atr[i]>am[i] and lc>0:
                if hi[i]>=rh[i] and cl[i]>ema[i]: pos=1;entry=max(rh[i],o[i]);lots=lc;stop=entry-sd;peak=hi[i];hold=0
                elif lo[i]<=rl[i] and cl[i]<ema[i]: pos=-1;entry=min(rl[i],o[i]);lots=lc;stop=entry+sd;peak=lo[i];hold=0
    t=np.array(tr_) if tr_ else np.array([0.0]); w=t[t>0];l=t[t<0]
    pf=w.sum()/(-l.sum()) if l.sum()<0 else np.inf
    return eq,pf,len(tr_),(t>0).mean() if tr_ else 0

print("="*70); print("■ コスト感応度（OOS, BO=12）  XMゴールド実スプレッドは概ね$0.2〜0.5"); print("="*70)
print(f"  {'往復スプレッド':<16}{'最終資金':>10}{'PF':>7}{'取引':>7}{'勝率':>8}")
for sp in [0.20,0.35,0.50,0.80,1.20,2.00]:
    eq,pf,n,wr=bt(OOS,spread=sp)
    print(f"  ${sp:<15.2f}{eq:>10.0f}{pf:>7.2f}{n:>7}{wr*100:>7.1f}%")

print("\n"+"="*70); print("■ SL/トレール近傍の安定性（OOS, BO=12, spread=$0.50）"); print("="*70)
print(f"  {'SL×ATR':>7} {'Trail×ATR':>10}{'最終資金':>10}{'PF':>7}{'取引':>7}")
for sl in [1.5,2.0,2.5]:
    for tl in [2.5,3.0,4.0]:
        eq,pf,n,wr=bt(OOS,sl_atr=sl,trail=tl,spread=0.50)
        print(f"  {sl:>7.1f} {tl:>10.1f}{eq:>10.0f}{pf:>7.2f}{n:>7}")
