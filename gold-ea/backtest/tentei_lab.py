#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GoldTentei改善ラボ: 押し目戦略に部分利確/トレールを足して改善するか検証。
規律はlab.pyと同じ(公開2012-22でチューニング, XM2023-25はホールドアウト, 両改善のみ採用)。"""
import numpy as np, pandas as pd
INIT=1000.0; RISK=0.01; SPREAD=0.50

def _ind(d):
    d=d.sort_values("Date").reset_index(drop=True)
    d["ema200"]=d.close.ewm(span=200,adjust=False).mean()
    d["ema_f"]=d.close.ewm(span=20,adjust=False).mean()
    tr=pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    d["atr"]=tr.rolling(14).mean()
    return d
def _attach_h4(d):
    g=d.set_index("Date"); h4=g["close"].resample("4h").last().dropna()
    h4e=h4.ewm(span=100,adjust=False).mean()
    a=pd.DataFrame({"avail":h4e.index+pd.Timedelta(hours=4),"h4_ema":h4e.values}).sort_values("avail")
    return pd.merge_asof(d.sort_values("Date"),a,left_on="Date",right_on="avail",direction="backward").drop(columns="avail")
def load_pub(p):
    d=pd.read_csv(p); d["Date"]=pd.to_datetime(d["Date"])
    for c in ["open","high","low","close"]: d[c]=d[c]/100.0
    return _attach_h4(_ind(d))
def load_xm(p):
    d=pd.read_csv(p,header=None,names=["dd","tt","open","high","low","close","v"])
    d["Date"]=pd.to_datetime(d["dd"]+" "+d["tt"],format="%Y.%m.%d %H:%M")
    return _attach_h4(_ind(d))

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

def run(df,k=3,fib_lo=.382,Nt=1.618,slb=.5,rev=3,maxhold=120,
        tp1_R=0.0,tp1_frac=0.0,be_after=True,trail_rest=0.0):
    """部分利確: tp1_R*リスク幅で tp1_frac を利確→建値、残りは全TP or トレール(trail_rest*ATR)"""
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;emaf=df.ema_f.values;atr=df.atr.values;n=len(df);h4e=df.h4_ema.values
    piv=find_pivots(hi,lo,k);conf={}
    for (idx,pr,t) in piv: conf.setdefault(idx+k,[]).append((idx,pr,t))
    known=[];eq=INIT;pos=0;entry=stop=tp=lots=0.0;hold=0;armL=None;part=0.0;risk0=0.0;peak=0.0
    out=np.empty(n);tr=[]
    for i in range(n):
        if i in conf: known.extend(conf[i]);armL=None
        if np.isnan(atr[i]) or atr[i]<=0: out[i]=eq;continue
        if pos!=0:
            hold+=1
            # 部分利確
            if tp1_frac>0 and part==0.0:
                tp1=entry+tp1_R*risk0
                if hi[i]>=tp1:
                    g=(tp1-entry)*lots*tp1_frac*100-SPREAD*100*lots*tp1_frac
                    eq+=g;tr.append(g);part=tp1_frac
                    if be_after: stop=max(stop,entry)
            # 残りのトレール(指定時)
            if trail_rest>0 and part>0:
                peak=max(peak,hi[i]); stop=max(stop,peak-trail_rest*atr[i])
            rem=1.0-part
            ex=None
            if lo[i]<=stop: ex=stop
            elif hi[i]>=tp: ex=tp
            elif maxhold>0 and hold>=maxhold: ex=cl[i]
            if ex is not None:
                g=(ex-entry)*lots*rem*100-SPREAD*100*lots*rem
                eq+=g;tr.append(g);pos=0;hold=0;part=0.0
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
                mtf=(not np.isnan(h4e[i]) and cl[i]>h4e[i])
                if armL['touched'] and cl[i]>ema[i] and cl[i]>emaf[i] and brk and mtf:
                    Lp=lo[max(i-rev,0):i+1].min();sd=cl[i]-(Lp-slb*atr[i])
                    if sd>0:
                        lc=max(eq*RISK/(sd*100),0.0)
                        if lc>0:
                            pos=1;entry=cl[i];stop=Lp-slb*atr[i];tp=Lp+Nt*armL['leg'];lots=lc
                            risk0=entry-stop;peak=entry;hold=0;part=0.0;armL=None
        out[i]=eq
    return out,(np.array(tr) if tr else np.array([0.0])),pd.DatetimeIndex(df.Date.values)

def metr(eq,tr,dates):
    s=pd.Series(eq,index=dates);final=s.iloc[-1];yrs=(dates[-1]-dates[0]).days/365.25 or 1e-9
    cagr=(final/INIT)**(1/yrs)-1 if final>0 else -1; dd=(s/s.cummax()-1).min()
    w=tr[tr>0];l=tr[tr<0];pf=w.sum()/(-l.sum()) if l.sum()<0 else (99.9 if w.sum()>0 else 0)
    dr=s.resample("1D").last().dropna().pct_change().dropna()
    sh=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    return dict(cagr=cagr,pf=pf,dd=dd,sh=sh,win=(tr>0).mean() if len(tr) else 0,n=len(tr))

PUB=load_pub("/tmp/xau_h1.csv"); PUB_OOS=PUB.iloc[int(len(PUB)*0.6):].reset_index(drop=True)
XM=load_xm("/tmp/xm_h1.csv")
def evalboth(label,**p):
    m1=metr(*run(PUB_OOS,**p)); m2=metr(*run(XM,**p))
    print(f"  {label:<26} | 公開OOS PF{m1['pf']:.2f} DD{m1['dd']*100:5.1f}% Sh{m1['sh']:+.2f} n{m1['n']:>3}"
          f" | XM PF{m2['pf']:.2f} DD{m2['dd']*100:5.1f}% Sh{m2['sh']:+.2f} n{m2['n']:>3}")

if __name__=="__main__":
    print("■ baseline(固定TP=1.618leg)"); evalboth("baseline")
    print("■ 部分利確: 1.0Rで一部利確→建値, 残りは全TP")
    for fr in [0.3,0.5,0.7]: evalboth(f"TP1=1.0R x{fr}",tp1_R=1.0,tp1_frac=fr)
    print("■ 部分利確 1.5R")
    for fr in [0.3,0.5]: evalboth(f"TP1=1.5R x{fr}",tp1_R=1.5,tp1_frac=fr)
    print("■ 部分利確(1.0R x0.5)+残りトレール")
    for trr in [2.0,3.0]: evalboth(f"TP1=1.0Rx0.5+trail{trr}",tp1_R=1.0,tp1_frac=0.5,trail_rest=trr)
