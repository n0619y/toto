#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XM実データ(GOLD H1, 2023-2025)での最終検証 = 答え合わせ。

開発は公開データ(2012-2022)で行い、パラメータは確定済み。ここでは『再最適化せず』
確定パラメータのまま、完全に未知のXM実データ(2023.07-2025.11)で2EAが通用するかを見る。
  - GoldVBO  : ブレイク。約定は検証どおり『水準で即約定』(=逆指値ストップ, ModelA)
  - GoldTentei: 押し目+H4トレンドMTF。H4はH1から再サンプルしてEMA(100)を作る
  - 合成: 推奨 VBO60/天底40 の日次リバランス
コストは複数のスプレッドで感応度も確認(XMのGOLDは概ね$0.2〜0.4/往復)。
"""
import numpy as np, pandas as pd, sys

CSV=sys.argv[1] if len(sys.argv)>1 else "/home/user/toto/gold-ea/data/GOLD_H1_xm.csv"
h=pd.read_csv(CSV,header=None,
              names=["d","t","open","high","low","close","vol"])
h["Date"]=pd.to_datetime(h["d"]+" "+h["t"],format="%Y.%m.%d %H:%M")
h=h.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
h["ema_f"]=h.close.ewm(span=20,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean(); h["atr_med"]=h.atr.rolling(200).median()
# H4トレンド(MTF)用: H1→H4再サンプル, EMA100, 確定足基準でas-of結合
g=h.set_index("Date")
h4=g["close"].resample("4h").last().dropna()
h4e=h4.ewm(span=100,adjust=False).mean()
h4df=pd.DataFrame({"avail":h4e.index+pd.Timedelta(hours=4),"h4_ema":h4e.values}).sort_values("avail")
h=pd.merge_asof(h.sort_values("Date"),h4df,left_on="Date",right_on="avail",direction="backward").drop(columns="avail")

INIT=1000.0; RISK=0.01

def eq_vbo(df,bo=12,sl_atr=2.0,trail=3.0,maxhold=72,SPREAD=0.35):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;atr=df.atr.values;am=df.atr_med.values
    rh=df.high.rolling(bo).max().shift(1).values; rl=df.low.rolling(bo).min().shift(1).values
    eq=INIT;pos=0;entry=stop=lots=0.0;peak=0.0;hold=0;out=np.empty(len(df));trades=[]
    for i in range(len(df)):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(am[i]) or np.isnan(rh[i]): out[i]=eq;continue
        if pos!=0:
            hold+=1
            if pos>0:
                peak=max(peak,hi[i]);stop=max(stop,peak-trail*atr[i])
                if lo[i]<=stop: g=(stop-entry)*lots*100-SPREAD*100*lots;eq+=g;trades.append(g);pos=0;hold=0
            else:
                peak=min(peak,lo[i]);stop=min(stop,peak+trail*atr[i])
                if hi[i]>=stop: g=(entry-stop)*lots*100-SPREAD*100*lots;eq+=g;trades.append(g);pos=0;hold=0
            if pos!=0 and hold>=maxhold:
                px=cl[i];g=((px-entry) if pos>0 else (entry-px))*lots*100-SPREAD*100*lots;eq+=g;trades.append(g);pos=0;hold=0
        if pos==0:
            sd=sl_atr*atr[i];lc=max(round(eq*RISK/(sd*100),2),0.0) if sd>0 else 0
            if atr[i]>am[i] and lc>0:
                if hi[i]>=rh[i] and cl[i]>ema[i]: pos=1;entry=max(rh[i],o[i]);lots=lc;stop=entry-sd;peak=hi[i];hold=0
                elif lo[i]<=rl[i] and cl[i]<ema[i]: pos=-1;entry=min(rl[i],o[i]);lots=lc;stop=entry+sd;peak=lo[i];hold=0
        out[i]=eq
    return out,np.array(trades) if trades else np.array([0.0])

def find_pivots(high,low,k):
    n=len(high);piv=[]
    for i in range(k,n-k):
        wh=high[i-k:i+k+1];wl=low[i-k:i+k+1]
        if high[i]==wh.max() and wh.argmax()==k: piv.append((i,high[i],'H'))
        elif low[i]==wl.min() and wl.argmin()==k: piv.append((i,low[i],'L'))
    piv.sort(key=lambda x:x[0]);clean=[]
    for p in piv:
        if clean and clean[-1][2]==p[2]:
            if (p[2]=='H' and p[1]>clean[-1][1]) or (p[2]=='L' and p[1]<clean[-1][1]): clean[-1]=p
        else: clean.append(p)
    return clean

def eq_tentei(df,k=3,fib_lo=.382,Nt=1.618,slb=.5,rev=3,maxhold=120,use_mtf=True,SPREAD=0.35):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;emaf=df.ema_f.values;atr=df.atr.values;n=len(df);h4e=df.h4_ema.values
    piv=find_pivots(hi,lo,k);conf={}
    for (idx,pr,t) in piv: conf.setdefault(idx+k,[]).append((idx,pr,t))
    known=[];eq=INIT;pos=0;entry=stop=tp=lots=0.0;hold=0;armL=None;out=np.empty(n);trades=[]
    for i in range(n):
        if i in conf: known.extend(conf[i]);armL=None
        if np.isnan(atr[i]) or atr[i]<=0: out[i]=eq;continue
        if pos!=0:
            hold+=1
            if lo[i]<=stop: g=(stop-entry)*lots*100-SPREAD*100*lots;eq+=g;trades.append(g);pos=0;hold=0
            elif hi[i]>=tp: g=(tp-entry)*lots*100-SPREAD*100*lots;eq+=g;trades.append(g);pos=0;hold=0
            elif maxhold>0 and hold>=maxhold: g=(cl[i]-entry)*lots*100-SPREAD*100*lots;eq+=g;trades.append(g);pos=0;hold=0
            out[i]=eq;continue
        H=[p for p in known if p[2]=='H'];L=[p for p in known if p[2]=='L']
        if len(H)>=2 and len(L)>=2:
            H1,H0=H[-1],H[-2];L0,Lp0=L[-1],L[-2]
            if H1[1]>H0[1] and L0[1]>Lp0[1] and known[-1][2]=='H' and L0[0]<H1[0] and armL is None:
                leg=H1[1]-L0[1]
                if leg>0: armL=dict(L0=L0[1],zhi=H1[1]-fib_lo*leg,leg=leg,touched=False)
        if armL is not None:
            if cl[i]<armL['L0']: armL=None
            else:
                if lo[i]<=armL['zhi']: armL['touched']=True
                brk=cl[i]>hi[max(i-rev,0):i].max() if i>0 else False
                mtf=(not use_mtf) or (not np.isnan(h4e[i]) and cl[i]>h4e[i])
                if armL['touched'] and cl[i]>ema[i] and cl[i]>emaf[i] and brk and mtf:
                    Lp=lo[max(i-rev,0):i+1].min();sd=cl[i]-(Lp-slb*atr[i])
                    if sd>0:
                        lc=max(round(eq*RISK/(sd*100),2),0.0)
                        if lc>0: pos=1;entry=cl[i];stop=Lp-slb*atr[i];tp=Lp+Nt*armL['leg'];lots=lc;hold=0;armL=None
        out[i]=eq
    return out,np.array(trades) if trades else np.array([0.0])

def stats(eq,trades,dates):
    s=pd.Series(eq,index=dates);final=s.iloc[-1]
    yrs=(dates[-1]-dates[0]).days/365.25
    cagr=(final/INIT)**(1/yrs)-1 if final>0 else -1
    dd=(s/s.cummax()-1).min()
    w=trades[trades>0];l=trades[trades<0];pf=w.sum()/(-l.sum()) if l.sum()<0 else np.inf
    dr=s.resample("1D").last().dropna().pct_change().dropna()
    sh=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    win=(trades>0).mean() if len(trades) else 0
    return final,cagr,pf,dd,sh,win,len(trades)

dates=pd.DatetimeIndex(h.Date.values)
print("="*82)
print(f"■ XM実データ最終検証  GOLD H1  {h.Date.iloc[0].date()}〜{h.Date.iloc[-1].date()}  ({len(h)}本)")
print("  ※開発(2012-2022)で確定したパラメータのまま, 再最適化なし")
print("="*82)
for SP in [0.25,0.35,0.50]:
    e1,t1=eq_vbo(h,bo=12,SPREAD=SP)
    e2,t2=eq_tentei(h,k=3,SPREAD=SP)
    f1,c1,p1,d1,s1,w1,n1=stats(e1,t1,dates)
    f2,c2,p2,d2,s2,w2,n2=stats(e2,t2,dates)
    # 合成 VBO60/天底40
    r1=pd.Series(e1,index=dates).resample("1D").last().dropna().pct_change()
    r2=pd.Series(e2,index=dates).resample("1D").last().dropna().pct_change()
    j=pd.concat([r1.rename("a"),r2.rename("b")],axis=1).dropna();corr=j.a.corr(j.b)
    port=0.6*j.a+0.4*j.b;eqp=(1+port).cumprod()
    yrs=(dates[-1]-dates[0]).days/365.25
    cp=eqp.iloc[-1]**(1/yrs)-1;dp=(eqp/eqp.cummax()-1).min();sp_=port.mean()/port.std()*np.sqrt(252)
    print(f"\n--- 往復コスト ${SP:.2f} ---")
    print(f"  GoldVBO(bo12)  : 最終${f1:>6.0f} CAGR{c1*100:+6.1f}% PF{p1:.2f} DD{d1*100:6.1f}% 勝率{w1*100:4.1f}% 取引{n1:>4} Sharpe{s1:+.2f}")
    print(f"  GoldTentei(k3) : 最終${f2:>6.0f} CAGR{c2*100:+6.1f}% PF{p2:.2f} DD{d2*100:6.1f}% 勝率{w2*100:4.1f}% 取引{n2:>4} Sharpe{s2:+.2f}")
    print(f"  → 合成60/40    : CAGR{cp*100:+6.1f}% DD{dp*100:6.1f}% Sharpe{sp_:+.2f}  (相関{corr:+.2f})")
