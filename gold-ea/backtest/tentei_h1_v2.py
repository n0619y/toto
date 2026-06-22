#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""天底ロジック v2: 反転の『事実』を待つエントリーに是正して再検証。

v1の負け要因 = エントリー条件が弱い(ゾーン到達+陽線1本で掴む) + ショート毀損。
v2の是正(資料に忠実):
  押し目ゾーン到達後、すぐ入らず『反転の事実』を待つ:
    - 直近 rev_bars 本の高値をブレイク(=小スイングの構造転換)
    - かつ Close > EMA_fast (MAが支持に転じた)
  → 「点まで待つ／反転サインまで待つ」の機械化。
  既定はロング偏重(ショートはオプション)。TPはN波動を伸ばし気味。
"""
import numpy as np, pandas as pd

h=pd.read_csv("/tmp/xau_h1.csv")
h["Date"]=pd.to_datetime(h["Date"])
for c in ["open","high","low","close"]: h[c]=h[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
h["ema_f"]=h.close.ewm(span=20,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean()
INIT=1000.0; RISK=0.01; SPREAD=0.35

def find_pivots(high, low, k):
    n=len(high); piv=[]
    for i in range(k, n-k):
        wh=high[i-k:i+k+1]; wl=low[i-k:i+k+1]
        if high[i]==wh.max() and wh.argmax()==k: piv.append((i,high[i],'H'))
        elif low[i]==wl.min() and wl.argmin()==k: piv.append((i,low[i],'L'))
    piv.sort(key=lambda x:x[0]); clean=[]
    for p in piv:
        if clean and clean[-1][2]==p[2]:
            if (p[2]=='H' and p[1]>clean[-1][1]) or (p[2]=='L' and p[1]<clean[-1][1]): clean[-1]=p
        else: clean.append(p)
    return clean

def backtest(df,k=4,fib_lo=0.382,fib_hi=0.618,Ntarget=1.618,sl_buf_atr=0.5,
             rev_bars=3,use_ema=True,use_emaf=True,allow_short=False,max_hold=120):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;emaf=df.ema_f.values;atr=df.atr.values;n=len(df)
    piv=find_pivots(hi,lo,k); pv_by_conf={}
    for (idx,price,t) in piv: pv_by_conf.setdefault(idx+k,[]).append((idx,price,t))
    known=[]; equity=INIT; pos=0; entry=stop=tp=lots=0.0; hold=0
    # アーム状態(ロング/ショート別の構えセットアップ)
    armL=None  # dict(L0,H1,zone_lo,zone_hi,touched, leg)
    armS=None
    eq=np.empty(n); trades=[]
    for i in range(n):
        if i in pv_by_conf:
            known.extend(pv_by_conf[i]); armL=None; armS=None  # 新ピボットで構え更新
        if np.isnan(atr[i]) or atr[i]<=0: eq[i]=equity; continue
        # ---- ポジ管理 ----
        if pos!=0:
            hold+=1
            if pos>0:
                if lo[i]<=stop: g=(stop-entry)*lots*100-SPREAD*100*lots;equity+=g;trades.append(g);pos=0;hold=0
                elif hi[i]>=tp: g=(tp-entry)*lots*100-SPREAD*100*lots;equity+=g;trades.append(g);pos=0;hold=0
            else:
                if hi[i]>=stop: g=(entry-stop)*lots*100-SPREAD*100*lots;equity+=g;trades.append(g);pos=0;hold=0
                elif lo[i]<=tp: g=(entry-tp)*lots*100-SPREAD*100*lots;equity+=g;trades.append(g);pos=0;hold=0
            if pos!=0 and max_hold>0 and hold>=max_hold:
                px=cl[i];g=((px-entry) if pos>0 else (entry-px))*lots*100-SPREAD*100*lots;equity+=g;trades.append(g);pos=0;hold=0
            eq[i]=equity; continue
        # ---- 構えの設定 ----
        highs=[p for p in known if p[2]=='H']; lows=[p for p in known if p[2]=='L']
        if len(highs)>=2 and len(lows)>=2:
            H1,H0=highs[-1],highs[-2]; L0,Lp0=lows[-1],lows[-2]
            up=H1[1]>H0[1] and L0[1]>Lp0[1]; dn=H1[1]<H0[1] and L0[1]<Lp0[1]
            if up and known[-1][2]=='H' and L0[0]<H1[0] and armL is None:
                leg=H1[1]-L0[1]
                if leg>0: armL=dict(L0=L0[1],H1=H1[1],zhi=H1[1]-fib_lo*leg,zlo=H1[1]-fib_hi*leg,leg=leg,touched=False)
            if allow_short and dn and known[-1][2]=='L' and H1[0]<L0[0] and armS is None:
                leg=H1[1]-L0[1]
                if leg>0: armS=dict(H1=H1[1],L0=L0[1],zlo=L0[1]+fib_lo*leg,zhi=L0[1]+fib_hi*leg,leg=leg,touched=False)
        # ---- ロング: ゾーン到達→反転の事実(直近高値ブレイク+EMA_f上)で参加 ----
        if armL is not None:
            if cl[i]<armL['L0']: armL=None                       # 押し安値割れ=無効
            else:
                if lo[i]<=armL['zhi']: armL['touched']=True
                macro=(not use_ema) or cl[i]>ema[i]
                maf=(not use_emaf) or cl[i]>emaf[i]
                brk = cl[i] > hi[max(i-rev_bars,0):i].max() if i>0 else False
                if armL['touched'] and macro and maf and brk:
                    Lp=lo[max(i-rev_bars,0):i+1].min()
                    sd=cl[i]-(Lp-sl_buf_atr*atr[i])
                    if sd>0:
                        lots=max(round(equity*RISK/(sd*100),2),0.0)
                        if lots>0:
                            pos=1;entry=cl[i];stop=Lp-sl_buf_atr*atr[i];tp=Lp+Ntarget*armL['leg'];hold=0;armL=None
        if pos==0 and armS is not None:
            if cl[i]>armS['H1']: armS=None
            else:
                if hi[i]>=armS['zlo']: armS['touched']=True
                macro=(not use_ema) or cl[i]<ema[i]
                maf=(not use_emaf) or cl[i]<emaf[i]
                brk = cl[i] < lo[max(i-rev_bars,0):i].min() if i>0 else False
                if armS['touched'] and macro and maf and brk:
                    Hp=hi[max(i-rev_bars,0):i+1].max()
                    sd=(Hp+sl_buf_atr*atr[i])-cl[i]
                    if sd>0:
                        lots=max(round(equity*RISK/(sd*100),2),0.0)
                        if lots>0:
                            pos=-1;entry=cl[i];stop=Hp+sl_buf_atr*atr[i];tp=Hp-Ntarget*armS['leg'];hold=0;armS=None
        eq[i]=equity
    eqs=pd.Series(eq); t=np.array(trades) if trades else np.array([0.0])
    w=t[t>0];l=t[t<0]; pf=w.sum()/(-l.sum()) if l.sum()<0 else np.inf
    dd=(eqs/eqs.cummax()-1).min(); days=(df.Date.iloc[-1]-df.Date.iloc[0]).days/365.25
    cagr=(equity/INIT)**(1/days)-1 if equity>0 and days>0 else 0
    rr=(w.mean()/-l.mean()) if len(w) and len(l) else 0
    return dict(final=equity,cagr=cagr,pf=pf,dd=dd,trades=len(trades),win=(t>0).mean() if len(trades) else 0,rr=rr)

def show(tag,r):
    print(f"  {tag:<26} 最終${r['final']:>6.0f} CAGR{r['cagr']*100:+6.1f}% PF{r['pf']:.2f} "
          f"DD{r['dd']*100:6.1f}% 勝率{r['win']*100:4.1f}% RR{r['rr']:.2f} 取引{r['trades']:>4}")

split=int(len(h)*0.6); IS=h.iloc[:split].reset_index(drop=True); OOS=h.iloc[split:].reset_index(drop=True)
print("="*84); print("■ v2 In-Sample: kスキャン(反転確認エントリー, ロング偏重)"); print("="*84)
isr={}
for k in [3,4,5,6]:
    r=backtest(IS,k=k); isr[k]=r; show(f"k={k}(IS)",r)
cand=[k for k in isr if isr[k]['trades']>=30]
best_k=max(cand,key=lambda k:isr[k]['pf']) if cand else 4
print(f"\n→ IS最良: k={best_k}")
print("\n"+"="*84); print("■ v2 Out-of-Sample ★本番★"); print("="*84)
show(f"k={best_k}(OOS)", backtest(OOS,k=best_k))
print("\n"+"="*84); print("■ v2 全kのOOS"); print("="*84)
for k in [3,4,5,6]: show(f"k={k}(OOS)", backtest(OOS,k=k))
print("\n"+"="*84); print(f"■ v2 アブレーション(OOS,k={best_k})"); print("="*84)
show("フル(ロングのみ)", backtest(OOS,k=best_k))
show("ショートも許可", backtest(OOS,k=best_k,allow_short=True))
show("反転確認なし(v1相当)", backtest(OOS,k=best_k,rev_bars=1,use_emaf=False))
show("TP=N波動1.0", backtest(OOS,k=best_k,Ntarget=1.0))
show("EMA200無し", backtest(OOS,k=best_k,use_ema=False))
