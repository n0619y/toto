#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2戦略ポートフォリオ検証: GoldVBO(ブレイク) + 天底v2(押し目) の合成効果。
各戦略を独立に$1000・リスク1%で回し、日次リターン系列を作って:
  - 相関(低いほど分散効果)
  - 50/50合成(日次リバランス)の PF/CAGR/DD/Sharpe を単体と比較
を確認する。コスト$0.50/往復。"""
import numpy as np, pandas as pd
h=pd.read_csv("/tmp/xau_h1.csv"); h["Date"]=pd.to_datetime(h["Date"])
for c in ["open","high","low","close"]: h[c]=h[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
h["ema_f"]=h.close.ewm(span=20,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean(); h["atr_med"]=h.atr.rolling(200).median()
# 上位足H4のEMA(100)を確定済みバー基準でH1にas-of結合(天底MTFフィルタ用)
h4=pd.read_csv("/tmp/xau_h4.csv"); h4["Date"]=pd.to_datetime(h4["Date"])
for c in ["open","high","low","close"]: h4[c]=h4[c]/100.0
h4=h4.sort_values("Date").reset_index(drop=True)
h4["h4_ema"]=h4.close.ewm(span=100,adjust=False).mean()
h4["avail"]=h4["Date"]+pd.Timedelta(hours=4)
h=pd.merge_asof(h.sort_values("Date"), h4[["avail","h4_ema"]].dropna().sort_values("avail"),
                left_on="Date", right_on="avail", direction="backward").drop(columns="avail")
INIT=1000.0; RISK=0.01; SPREAD=0.50

# ---------- 戦略1: GoldVBO (ブレイク) ----------
def eq_vbo(df,bo=24,sl_atr=2.0,trail=3.0,maxhold=72):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;atr=df.atr.values;am=df.atr_med.values
    rh=df.high.rolling(bo).max().shift(1).values; rl=df.low.rolling(bo).min().shift(1).values
    eq=INIT;pos=0;entry=stop=lots=0.0;peak=0.0;hold=0;out=np.empty(len(df))
    for i in range(len(df)):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(am[i]) or np.isnan(rh[i]): out[i]=eq;continue
        if pos!=0:
            hold+=1
            if pos>0:
                peak=max(peak,hi[i]);stop=max(stop,peak-trail*atr[i])
                if lo[i]<=stop: eq+=(stop-entry)*lots*100-SPREAD*100*lots;pos=0;hold=0
            else:
                peak=min(peak,lo[i]);stop=min(stop,peak+trail*atr[i])
                if hi[i]>=stop: eq+=(entry-stop)*lots*100-SPREAD*100*lots;pos=0;hold=0
            if pos!=0 and hold>=maxhold:
                px=cl[i];eq+=((px-entry) if pos>0 else (entry-px))*lots*100-SPREAD*100*lots;pos=0;hold=0
        if pos==0:
            sd=sl_atr*atr[i];lc=max(round(eq*RISK/(sd*100),2),0.0) if sd>0 else 0
            if atr[i]>am[i] and lc>0:
                if hi[i]>=rh[i] and cl[i]>ema[i]: pos=1;entry=max(rh[i],o[i]);lots=lc;stop=entry-sd;peak=hi[i];hold=0
                elif lo[i]<=rl[i] and cl[i]<ema[i]: pos=-1;entry=min(rl[i],o[i]);lots=lc;stop=entry+sd;peak=lo[i];hold=0
        out[i]=eq
    return out

# ---------- 戦略2: 天底v2 (押し目, ロングのみ) ----------
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
def eq_tentei(df,k=3,fib_lo=.382,fib_hi=.618,Nt=1.618,slb=.5,rev=3,maxhold=120,use_mtf=True):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;emaf=df.ema_f.values;atr=df.atr.values;n=len(df)
    h4e=df.h4_ema.values
    piv=find_pivots(hi,lo,k);conf={}
    for (idx,pr,t) in piv: conf.setdefault(idx+k,[]).append((idx,pr,t))
    known=[];eq=INIT;pos=0;entry=stop=tp=lots=0.0;hold=0;armL=None;out=np.empty(n)
    for i in range(n):
        if i in conf: known.extend(conf[i]);armL=None
        if np.isnan(atr[i]) or atr[i]<=0: out[i]=eq;continue
        if pos!=0:
            hold+=1
            if lo[i]<=stop: eq+=(stop-entry)*lots*100-SPREAD*100*lots;pos=0;hold=0
            elif hi[i]>=tp: eq+=(tp-entry)*lots*100-SPREAD*100*lots;pos=0;hold=0
            elif maxhold>0 and hold>=maxhold: eq+=(cl[i]-entry)*lots*100-SPREAD*100*lots;pos=0;hold=0
            out[i]=eq;continue
        H=[p for p in known if p[2]=='H'];L=[p for p in known if p[2]=='L']
        if len(H)>=2 and len(L)>=2:
            H1,H0=H[-1],H[-2];L0,Lp0=L[-1],L[-2]
            up=H1[1]>H0[1] and L0[1]>Lp0[1]
            if up and known[-1][2]=='H' and L0[0]<H1[0] and armL is None:
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
    return out

def metrics(eq_series, dates, label):
    s=pd.Series(eq_series,index=dates)
    daily=s.resample("1D").last().dropna()
    dr=daily.pct_change().dropna()
    final=s.iloc[-1]; yrs=(dates[-1]-dates[0]).days/365.25
    cagr=(final/INIT)**(1/yrs)-1 if final>0 else -1
    dd=(s/s.cummax()-1).min()
    sharpe=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    print(f"  {label:<22} 最終${final:>6.0f} CAGR{cagr*100:+6.1f}% 最大DD{dd*100:6.1f}% Sharpe(日次){sharpe:+.2f}")
    return dr

def weight_scan(e1,e2,d):
    """配分w(=GoldVBO比率)を0〜1でスキャンし、合成のCAGR/DD/Sharpeを出す。"""
    s1=pd.Series(e1,index=d).resample("1D").last().dropna().pct_change()
    s2=pd.Series(e2,index=d).resample("1D").last().dropna().pct_change()
    j=pd.concat([s1.rename("a"),s2.rename("b")],axis=1).dropna()
    yrs=(d[-1]-d[0]).days/365.25
    print(f"  {'VBO:Tentei':<12}{'CAGR':>8}{'最大DD':>9}{'Sharpe':>9}")
    best=None
    for w in [0.0,0.3,0.5,0.6,0.7,0.8,0.9,1.0]:
        p=w*j["a"]+(1-w)*j["b"]; eqp=(1+p).cumprod()
        cagr=eqp.iloc[-1]**(1/yrs)-1; dd=(eqp/eqp.cummax()-1).min()
        sh=p.mean()/p.std()*np.sqrt(252) if p.std()>0 else 0
        mark=""
        if best is None or sh>best[1]: best=(w,sh)
        print(f"  {int(w*100):>3}:{int((1-w)*100):<3}    {cagr*100:>+7.1f}%{dd*100:>8.1f}%{sh:>+9.2f}")
    # リスクパリティ(各戦略の日次ボラ逆数で配分)
    v1=j["a"].std(); v2=j["b"].std()
    wrp=(1/v1)/((1/v1)+(1/v2))
    print(f"  → Sharpe最大配分: VBO {int(best[0]*100)}%  / リスクパリティ配分: VBO {wrp*100:.0f}%")

if __name__=="__main__":
  for tag,seg in [("全期間",h),("OOS(2018-2022)",h.iloc[int(len(h)*0.6):].reset_index(drop=True))]:
    print("="*78);print(f"■ {tag}");print("="*78)
    e1=eq_vbo(seg); e2=eq_tentei(seg)
    d=seg.Date.values.astype("datetime64[ns]")
    r1=metrics(e1,pd.DatetimeIndex(d),"GoldVBO(ブレイク)")
    r2=metrics(e2,pd.DatetimeIndex(d),"天底v3(押し目+MTF)")
    # 50/50合成(日次リバランス)
    df1=pd.Series(e1,index=pd.DatetimeIndex(d)).resample("1D").last().dropna().pct_change()
    df2=pd.Series(e2,index=pd.DatetimeIndex(d)).resample("1D").last().dropna().pct_change()
    j=pd.concat([df1.rename("a"),df2.rename("b")],axis=1).dropna()
    corr=j["a"].corr(j["b"])
    port=(0.5*j["a"]+0.5*j["b"])
    eqp=(1+port).cumprod()*INIT
    cagrp=(eqp.iloc[-1]/INIT)**(365.25/ (d[-1].astype('datetime64[D]')-d[0].astype('datetime64[D]')).astype(int))-1
    ddp=(eqp/eqp.cummax()-1).min(); shp=port.mean()/port.std()*np.sqrt(252) if port.std()>0 else 0
    print(f"  {'→ 50/50 合成':<22} 最終${eqp.iloc[-1]:>6.0f} CAGR{cagrp*100:+6.1f}% 最大DD{ddp*100:6.1f}% Sharpe(日次){shp:+.2f}")
    print(f"  ★ 日次リターン相関: {corr:+.3f}  (低い/負ほど分散効果が大きい)")
    print("  --- 配分スキャン ---")
    weight_scan(e1,e2,pd.DatetimeIndex(d))
    print()
