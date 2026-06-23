#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""天底ロジック v3: 上位足(H4)トレンド一致フィルタ(MTF)を追加して精度向上を検証。

v2の弱点 = 押し目反転を待っても、上位足が下向き/横ばいの局面で拾うと失敗しやすい。
v3の是正:
  H1のエントリー判定に、上位足H4のトレンド方向ゲートを追加。
    - H4 Close > H4 EMA(h4_span) かつ H4 EMA が上向き(slope>0) のときだけロング許可
  M15は公開データが無いため、保有しているH4を上位足に採用(H4トレンド→H1エントリー)。
  v2の反転確認(直近高値ブレイク+EMA_f)はそのまま踏襲。

検証は v2 と同一の IS/OOS 分割・同一コストで、MTFゲートの有無を比較する。
"""
import numpy as np, pandas as pd

h=pd.read_csv("/tmp/xau_h1.csv"); h["Date"]=pd.to_datetime(h["Date"])
h4=pd.read_csv("/tmp/xau_h4.csv"); h4["Date"]=pd.to_datetime(h4["Date"])
for c in ["open","high","low","close"]:
    h[c]=h[c]/100.0; h4[c]=h4[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h4=h4.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
h["ema_f"]=h.close.ewm(span=20,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean()

def attach_h4(df, h4_span):
    """H4 EMA とその傾きを、確定済みH4バー基準で H1 に as-of 結合(先読み防止)。"""
    g=h4.copy()
    g["h4_ema"]=g.close.ewm(span=h4_span,adjust=False).mean()
    g["h4_slope"]=g["h4_ema"]-g["h4_ema"].shift(1)
    # H4バーは終値時刻=Date+4h で確定 → その時刻以降のH1だけが参照可能
    g["avail"]=g["Date"]+pd.Timedelta(hours=4)
    g=g[["avail","h4_ema","h4_slope"]].dropna().sort_values("avail")
    m=pd.merge_asof(df.sort_values("Date"), g, left_on="Date", right_on="avail", direction="backward")
    return m.sort_index()

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
             rev_bars=3,use_ema=True,use_emaf=True,allow_short=False,max_hold=120,
             use_mtf=True,need_slope=True):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;emaf=df.ema_f.values;atr=df.atr.values;n=len(df)
    h4e=df.h4_ema.values; h4s=df.h4_slope.values
    piv=find_pivots(hi,lo,k); pv_by_conf={}
    for (idx,price,t) in piv: pv_by_conf.setdefault(idx+k,[]).append((idx,price,t))
    known=[]; equity=INIT; pos=0; entry=stop=tp=lots=0.0; hold=0
    armL=None; armS=None
    eq=np.empty(n); trades=[]
    for i in range(n):
        if i in pv_by_conf:
            known.extend(pv_by_conf[i]); armL=None; armS=None
        if np.isnan(atr[i]) or atr[i]<=0: eq[i]=equity; continue
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
        # 上位足ゲート
        h4_up = (not use_mtf) or (not np.isnan(h4e[i]) and cl[i]>h4e[i] and ((not need_slope) or h4s[i]>0))
        h4_dn = (not use_mtf) or (not np.isnan(h4e[i]) and cl[i]<h4e[i] and ((not need_slope) or h4s[i]<0))
        if armL is not None:
            if cl[i]<armL['L0']: armL=None
            else:
                if lo[i]<=armL['zhi']: armL['touched']=True
                macro=(not use_ema) or cl[i]>ema[i]
                maf=(not use_emaf) or cl[i]>emaf[i]
                brk = cl[i] > hi[max(i-rev_bars,0):i].max() if i>0 else False
                if armL['touched'] and macro and maf and brk and h4_up:
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
                if armS['touched'] and macro and maf and brk and h4_dn:
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
    print(f"  {tag:<30} 最終${r['final']:>6.0f} CAGR{r['cagr']*100:+6.1f}% PF{r['pf']:.2f} "
          f"DD{r['dd']*100:6.1f}% 勝率{r['win']*100:4.1f}% RR{r['rr']:.2f} 取引{r['trades']:>4}")

if __name__=="__main__":
    # H4 span をいくつか比較(全期間でゲート効果の方向性を見る)
    print("="*92); print("■ v3 MTFゲート効果: H4 EMA span スキャン (OOS, k=4)"); print("="*92)
    base=None
    for span in [20,50,100]:
        m=attach_h4(h, span)
        split=int(len(m)*0.6); OOS=m.iloc[split:].reset_index(drop=True)
        if base is None:
            base=backtest(OOS,k=4,use_mtf=False); show("MTFなし(v2相当)", base)
        show(f"H4ema{span} slope要", backtest(OOS,k=4,use_mtf=True,need_slope=True))
        show(f"H4ema{span} 位置のみ", backtest(OOS,k=4,use_mtf=True,need_slope=False))

    print("\n"+"="*92); print("■ v3 IS/OOS 一貫性 (H4ema50, slope要, kスキャン)"); print("="*92)
    m=attach_h4(h,50); split=int(len(m)*0.6)
    IS=m.iloc[:split].reset_index(drop=True); OOS=m.iloc[split:].reset_index(drop=True)
    for k in [3,4,5,6]:
        ri=backtest(IS,k=k); ro=backtest(OOS,k=k)
        print(f"  k={k}: IS PF{ri['pf']:.2f} DD{ri['dd']*100:5.1f}% 取引{ri['trades']:>3} | "
              f"OOS PF{ro['pf']:.2f} CAGR{ro['cagr']*100:+5.1f}% DD{ro['dd']*100:5.1f}% 取引{ro['trades']:>3}")
