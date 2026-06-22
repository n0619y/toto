#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""天底ロジック(スイング/デイ)の客観化版を H1 で IS/OOS 検証。

機械化ルール(資料に忠実):
  ダウ構造: スイング(ピボット)検出 → HH/HL=上昇, LH/LL=下降。押し安値/戻り高値を定義。
  環境認識: トレンド方向のみ順張り(任意でEMA200のマクロ整合も併用)。
  エントリー(押し目買い/戻り売り):
     直近インパルス[L0→H1]に対し、価格がフィボ38.2-61.8へ押したら、
     確定足の反転(陽線/陰線確定)で参加。
  TP: N波動=FE100(押し目の安値 + インパルス値幅)。
  SL: 構造(押し安値=L0 の少し外)。
  → 高RRのスイング。コスト込み・リスク1%。
比較: GoldVBO(ベンチマーク, validate_h1.py 参照)。
"""
import numpy as np, pandas as pd

h=pd.read_csv("/tmp/xau_h1.csv")
h["Date"]=pd.to_datetime(h["Date"])
for c in ["open","high","low","close"]: h[c]=h[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean()

INIT=1000.0; RISK=0.01; SPREAD=0.35

def find_pivots(high, low, k):
    """因果的ピボット。idx i が ±k で極値なら i のピボット。確認時刻は i+k。"""
    n=len(high); piv=[]  # (idx, price, 'H'/'L')
    for i in range(k, n-k):
        wh=high[i-k:i+k+1]; wl=low[i-k:i+k+1]
        if high[i]==wh.max() and (wh.argmax()==k): piv.append((i, high[i], 'H'))
        elif low[i]==wl.min() and (wl.argmin()==k): piv.append((i, low[i], 'L'))
    piv.sort(key=lambda x:x[0])
    # 同種連続は極値側を残す(交互化)
    clean=[]
    for p in piv:
        if clean and clean[-1][2]==p[2]:
            if (p[2]=='H' and p[1]>clean[-1][1]) or (p[2]=='L' and p[1]<clean[-1][1]):
                clean[-1]=p
        else: clean.append(p)
    return clean

def backtest(df, k=4, fib_lo=0.382, fib_hi=0.618, Ntarget=1.0,
             sl_buf_atr=0.5, use_ema=True, allow_short=True, max_hold=120):
    o=df.open.values; hi=df.high.values; lo=df.low.values; cl=df.close.values
    ema=df.ema200.values; atr=df.atr.values; n=len(df)
    piv=find_pivots(hi, lo, k)
    # 確認時刻(idx+k)→そのバーで利用可能になるピボット
    pv_by_conf={}
    for (idx,price,t) in piv: pv_by_conf.setdefault(idx+k,[]).append((idx,price,t))
    known=[]  # 確認済みピボット(時系列)
    equity=INIT; pos=0; entry=stop=tp=lots=0.0; hold=0; pull_ext=0.0
    eq=np.empty(n); trades=[]
    for i in range(n):
        if i in pv_by_conf: known.extend(pv_by_conf[i])
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
        # ---- エントリー判定(無ポジ・確定足) ----
        if pos==0 and len(known)>=3:
            # 直近の確認済みピボット
            last=known[-1]
            highs=[p for p in known if p[2]=='H']; lows=[p for p in known if p[2]=='L']
            if len(highs)>=2 and len(lows)>=2:
                H1=highs[-1]; H0=highs[-2]; L0=lows[-1]; Lp0=lows[-2]
                up = H1[1]>H0[1] and L0[1]>Lp0[1]      # HH & HL
                dn = H1[1]<H0[1] and L0[1]<Lp0[1]      # LH & LL
                macro_up = (not use_ema) or cl[i]>ema[i]
                macro_dn = (not use_ema) or cl[i]<ema[i]
                # 上昇: 直近確認が High(=高値更新後の押し), L0<...<H1
                if up and macro_up and last[2]=='H' and L0[0]<H1[0]:
                    leg=H1[1]-L0[1]
                    if leg>0:
                        zone_hi=H1[1]-fib_lo*leg; zone_lo=H1[1]-fib_hi*leg
                        # 押し目が現バーでゾーン内に入り、陽線確定で参加
                        if lo[i]<=zone_hi and cl[i]>=zone_lo and cl[i]>o[i]:
                            Lp=min(lo[max(H1[0],0):i+1].min(), lo[i])
                            sd=cl[i]-(Lp-sl_buf_atr*atr[i])
                            if sd>0:
                                lots=max(round(equity*RISK/(sd*100),2),0.0)
                                if lots>0:
                                    pos=1;entry=cl[i];stop=Lp-sl_buf_atr*atr[i];tp=Lp+Ntarget*leg;hold=0
                elif dn and macro_dn and allow_short and last[2]=='L' and H1[0]<L0[0] if False else (dn and macro_dn and allow_short and last[2]=='L'):
                    # 下降: 直近確認が Low(=安値更新後の戻り)
                    H1d=highs[-1]; L0d=lows[-1]
                    leg=H1d[1]-L0d[1]
                    if leg>0 and H1d[0]<L0d[0]:
                        zone_lo=L0d[1]+fib_lo*leg; zone_hi=L0d[1]+fib_hi*leg
                        if hi[i]>=zone_lo and cl[i]<=zone_hi and cl[i]<o[i]:
                            Hp=max(hi[max(L0d[0],0):i+1].max(), hi[i])
                            sd=(Hp+sl_buf_atr*atr[i])-cl[i]
                            if sd>0:
                                lots=max(round(equity*RISK/(sd*100),2),0.0)
                                if lots>0:
                                    pos=-1;entry=cl[i];stop=Hp+sl_buf_atr*atr[i];tp=Hp-Ntarget*leg;hold=0
        eq[i]=equity
    eqs=pd.Series(eq); t=np.array(trades) if trades else np.array([0.0])
    w=t[t>0]; l=t[t<0]; pf=w.sum()/(-l.sum()) if l.sum()<0 else np.inf
    dd=(eqs/eqs.cummax()-1).min(); days=(df.Date.iloc[-1]-df.Date.iloc[0]).days/365.25
    cagr=(equity/INIT)**(1/days)-1 if equity>0 and days>0 else 0
    rr=(w.mean()/-l.mean()) if len(w) and len(l) else 0
    return dict(final=equity,cagr=cagr,pf=pf,dd=dd,trades=len(trades),
                win=(t>0).mean() if len(trades) else 0, rr=rr)

def show(tag,r):
    print(f"  {tag:<24} 最終${r['final']:>6.0f} CAGR{r['cagr']*100:+6.1f}% PF{r['pf']:.2f} "
          f"DD{r['dd']*100:6.1f}% 勝率{r['win']*100:4.1f}% RR{r['rr']:.2f} 取引{r['trades']:>4}")

split=int(len(h)*0.6); IS=h.iloc[:split].reset_index(drop=True); OOS=h.iloc[split:].reset_index(drop=True)
print(f"IS {IS.Date.iloc[0].date()}〜{IS.Date.iloc[-1].date()} / OOS {OOS.Date.iloc[0].date()}〜{OOS.Date.iloc[-1].date()}\n")

print("="*82); print("■ In-Sample: ピボット幅kのスキャン(他は事前固定)"); print("="*82)
isr={}
for k in [3,4,5,6,8]:
    r=backtest(IS,k=k); isr[k]=r; show(f"k={k}(IS)",r)
best_k=max(isr,key=lambda k:isr[k]['pf'] if isr[k]['trades']>=30 else -1)
print(f"\n→ IS最良(PF, 取引数30以上): k={best_k}")

print("\n"+"="*82); print("■ Out-of-Sample ★本番★"); print("="*82)
show(f"k={best_k}(OOS)", backtest(OOS,k=best_k))

print("\n"+"="*82); print("■ 全kのOOS(過剰最適化でないか)"); print("="*82)
for k in [3,4,5,6,8]: show(f"k={k}(OOS)", backtest(OOS,k=k))

print("\n"+"="*82); print(f"■ アブレーション(OOS, k={best_k})"); print("="*82)
show("フル", backtest(OOS,k=best_k))
show("EMAマクロ無し", backtest(OOS,k=best_k,use_ema=False))
show("ロングのみ", backtest(OOS,k=best_k,allow_short=False))
show("TP=N波動1.618", backtest(OOS,k=best_k,Ntarget=1.618))
