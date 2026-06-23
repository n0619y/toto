#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""エントリーモデル整合性チェック: バックテストとMQL4 EAの約定モデル差を定量化。

検証(eq_vbo)は『ブレイク足の最中に水準(前N本高値)で約定』= 指値/逆指値の即時約定を仮定。
一方MQL4 GoldVBOは『足が確定してから次足の成行』= 1バー遅れ・次足始値約定。
この差がOOS成績をどれだけ動かすかを測り、EA実装の妥当性(or要改善)を判断する。

  ModelA(検証どおり) : ブレイク足iで fill = max(rollHigh, open_i)
  ModelB(EA相当)     : ブレイク足iを検知→ open_{i+1}(次足始値)で成行 fill
他(SL/トレール/フィルタ/コスト)は完全に同一。
"""
import numpy as np, pandas as pd
h=pd.read_csv("/tmp/xau_h1.csv"); h["Date"]=pd.to_datetime(h["Date"])
for c in ["open","high","low","close"]: h[c]=h[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean(); h["atr_med"]=h.atr.rolling(200).median()
INIT=1000.0; RISK=0.01; SPREAD=0.50

def run(df,bo=24,sl_atr=2.0,trail=3.0,maxhold=72,entry_model="A"):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;atr=df.atr.values;am=df.atr_med.values
    rh=df.high.rolling(bo).max().shift(1).values; rl=df.low.rolling(bo).min().shift(1).values
    eq=INIT;pos=0;entry=stop=lots=0.0;peak=0.0;hold=0;out=np.empty(len(df));trades=[]
    pend=0  # ModelB用: 次足始値で約定する待ち(1=買い,-1=売り)
    for i in range(len(df)):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(am[i]) or np.isnan(rh[i]): out[i]=eq;continue
        # ModelB: 前足で出たシグナルを今足始値で約定
        if entry_model=="B" and pos==0 and pend!=0:
            sd=sl_atr*atr[i-1]; lc=max(round(eq*RISK/(sd*100),2),0.0) if sd>0 else 0
            if lc>0:
                if pend>0: pos=1;entry=o[i];lots=lc;stop=entry-sd;peak=hi[i];hold=0
                else: pos=-1;entry=o[i];lots=lc;stop=entry+sd;peak=lo[i];hold=0
            pend=0
        if pos!=0:
            hold+=1
            if pos>0:
                peak=max(peak,hi[i]);stop=max(stop,peak-trail*atr[i])
                if lo[i]<=stop: eq+=(stop-entry)*lots*100-SPREAD*100*lots;trades.append(1);pos=0;hold=0
            else:
                peak=min(peak,lo[i]);stop=min(stop,peak+trail*atr[i])
                if hi[i]>=stop: eq+=(entry-stop)*lots*100-SPREAD*100*lots;trades.append(1);pos=0;hold=0
            if pos!=0 and hold>=maxhold:
                px=cl[i];eq+=((px-entry) if pos>0 else (entry-px))*lots*100-SPREAD*100*lots;trades.append(1);pos=0;hold=0
        if pos==0:
            sd=sl_atr*atr[i];lc=max(round(eq*RISK/(sd*100),2),0.0) if sd>0 else 0
            volok=atr[i]>am[i]
            if volok and lc>0:
                if entry_model=="A":
                    if hi[i]>=rh[i] and cl[i]>ema[i]: pos=1;entry=max(rh[i],o[i]);lots=lc;stop=entry-sd;peak=hi[i];hold=0
                    elif lo[i]<=rl[i] and cl[i]<ema[i]: pos=-1;entry=min(rl[i],o[i]);lots=lc;stop=entry+sd;peak=lo[i];hold=0
                elif entry_model=="B" and pend==0:
                    # ブレイク足を検知 → 次足始値で約定予約(トレンドはbrk足の確定closeで判定)
                    if hi[i]>=rh[i] and cl[i]>ema[i]: pend=1
                    elif lo[i]<=rl[i] and cl[i]<ema[i]: pend=-1
        out[i]=eq
    eqs=pd.Series(eq if False else out)
    days=(df.Date.iloc[-1]-df.Date.iloc[0]).days/365.25
    cagr=(eq/INIT)**(1/days)-1 if eq>0 else -1
    dd=(eqs/eqs.cummax()-1).min()
    return dict(final=eq,cagr=cagr,dd=dd,trades=len(trades))

OOS=h.iloc[int(len(h)*0.6):].reset_index(drop=True)
print("="*72); print("■ エントリー約定モデルの差 (OOS 2018-2022, bo=24)"); print("="*72)
for bo in [12,24,48]:
    a=run(OOS,bo=bo,entry_model="A"); b=run(OOS,bo=bo,entry_model="B")
    print(f"  bo={bo:>3}")
    print(f"    A 検証(水準で即約定): 最終${a['final']:>6.0f} CAGR{a['cagr']*100:+6.1f}% DD{a['dd']*100:6.1f}% 取引{a['trades']}")
    print(f"    B EA相当(次足始値)  : 最終${b['final']:>6.0f} CAGR{b['cagr']*100:+6.1f}% DD{b['dd']*100:6.1f}% 取引{b['trades']}")
    if a['cagr']!=0:
        print(f"    → CAGR差 {(b['cagr']-a['cagr'])*100:+.1f}pt  (EAが検証より{'劣化' if b['cagr']<a['cagr'] else '改善'})")
