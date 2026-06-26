#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EA改善ラボ: 柔軟なVBO系バックテストで改善案を高速検証する共通ハーネス。

評価規律(過剰最適化を避ける):
  - チューニングは公開データ2012-2022(2018チョップ/2013暴落を含む)で行う
  - XM実データ2023-2025は『完全ホールドアウト』= 確認専用、ここでは最適化しない
  - 両データで改善した案のみ採用
全機能はトグルで、既定値は現行ベースライン(H1: bo12, ER0.30, EMA200, SL2.0, Trail3.0)。
"""
import numpy as np, pandas as pd
INIT=1000.0; RISK=0.01

def _prep(d):
    d=d.sort_values("Date").reset_index(drop=True)
    d["ema200"]=d.close.ewm(span=200,adjust=False).mean()
    d["hour"]=pd.DatetimeIndex(d.Date).hour
    tr=pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    d["atr"]=tr.rolling(14).mean(); d["atr_med"]=d.atr.rolling(200).median()
    # ADX(14)
    up=d.high.diff(); dn=-d.low.diff()
    plus=np.where((up>dn)&(up>0),up,0.0); minus=np.where((dn>up)&(dn>0),dn,0.0)
    atr1=tr.ewm(alpha=1/14,adjust=False).mean()
    pdi=100*pd.Series(plus,index=d.index).ewm(alpha=1/14,adjust=False).mean()/atr1
    mdi=100*pd.Series(minus,index=d.index).ewm(alpha=1/14,adjust=False).mean()/atr1
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    d["adx"]=dx.ewm(alpha=1/14,adjust=False).mean()
    return d

def load_pub(path):
    d=pd.read_csv(path); d["Date"]=pd.to_datetime(d["Date"])
    for c in ["open","high","low","close"]: d[c]=d[c]/100.0
    return _prep(d)
def load_xm(path):
    d=pd.read_csv(path,header=None,names=["dd","tt","open","high","low","close","vol"])
    d["Date"]=pd.to_datetime(d["dd"]+" "+d["tt"],format="%Y.%m.%d %H:%M")
    return _prep(d)

def add_er(d,n):
    c=d.close.values; net=np.abs(c-np.roll(c,n))
    vol=pd.Series(np.abs(np.diff(c,prepend=c[0]))).rolling(n).sum().values
    er=np.where(vol>0,net/vol,0.0); er[:n]=np.nan; return er

def run(df,bo=12,sl_atr=2.0,trail=3.0,maxhold=72,er_th=0.30,er_n=20,
        ema_on=True,volgate=True,adx_th=0.0,buf_atr=0.0,
        be_trig=0.0,be_lock=0.0,trail_act=0.0,
        tp1_atr=0.0,tp1_frac=0.0,trail_after=0.0,
        tp2_atr=0.0,tp2_frac=0.0,SPREAD=0.50):
    """戻り: (equity配列, trades配列[R/取引でなく$], dates)
    機能トグル:
      buf_atr   : ブレイク水準+buf*ATRでエントリー(だまし回避)
      adx_th    : ADXがこの値以上のみ参加(0=無効)
      be_trig/be_lock: be_trig*ATR含み益で SL=entry+be_lock*ATR(建値/微益ロック)
      trail_act : trail_act*ATR動くまでトレール開始を遅らせる
      tp1_atr/tp1_frac: tp1_atr*ATRで tp1_frac を利確(部分利確)、残りトレール
    """
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;atr=df.atr.values;am=df.atr_med.values;adx=df.adx.values
    er=add_er(df,er_n)
    rh=df.high.rolling(bo).max().shift(1).values; rl=df.low.rolling(bo).min().shift(1).values
    eq=INIT;pos=0;entry=stop=lots=0.0;peak=0.0;hold=0;part=0.0;init_stop=0.0
    out=np.empty(len(df));tr=[]
    for i in range(len(df)):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(am[i]) or np.isnan(rh[i]) or np.isnan(er[i]) or np.isnan(adx[i]):
            out[i]=eq;continue
        if pos!=0:
            hold+=1; a=atr[i]
            move=(hi[i]-entry) if pos>0 else (entry-lo[i])   # その足での最大含み益方向
            # 部分利確(第1段)
            if tp1_frac>0 and part==0.0:
                tp1=entry+pos*tp1_atr*a
                if (pos>0 and hi[i]>=tp1) or (pos<0 and lo[i]<=tp1):
                    g=pos*(tp1-entry)*lots*tp1_frac*100 - SPREAD*100*lots*tp1_frac
                    eq+=g;tr.append(g);part+=tp1_frac
                    if be_lock==0: stop=max(stop,entry) if pos>0 else min(stop,entry)  # 残りは建値以上
            # 部分利確(第2段)
            if tp2_frac>0 and 0.0<part<(tp1_frac+tp2_frac):
                tp2=entry+pos*tp2_atr*a
                if (pos>0 and hi[i]>=tp2) or (pos<0 and lo[i]<=tp2):
                    g=pos*(tp2-entry)*lots*tp2_frac*100 - SPREAD*100*lots*tp2_frac
                    eq+=g;tr.append(g);part+=tp2_frac
            # ブレイクイーブン
            if be_trig>0 and move>=be_trig*a:
                bestop=entry+pos*be_lock*a
                stop=max(stop,bestop) if pos>0 else min(stop,bestop)
            # トレール(発動遅延あり)。部分利確後は trail_after(指定時)で残りを伸ばす
            tmult=trail_after if (part>0.0 and trail_after>0.0) else trail
            if move>=trail_act*a:
                if pos>0: peak=max(peak,hi[i]);stop=max(stop,peak-tmult*a)
                else: peak=min(peak,lo[i]);stop=min(stop,peak+tmult*a)
            # 約定判定(残量)
            rem=1.0-part
            exit_px=None
            if pos>0 and lo[i]<=stop: exit_px=stop
            elif pos<0 and hi[i]>=stop: exit_px=stop
            if exit_px is None and maxhold>0 and hold>=maxhold: exit_px=cl[i]
            if exit_px is not None:
                g=pos*(exit_px-entry)*lots*rem*100 - SPREAD*100*lots*rem
                eq+=g;tr.append(g);pos=0;hold=0;part=0.0
        if pos==0:
            sd=sl_atr*atr[i];lc=max(eq*RISK/(sd*100),0.0) if sd>0 else 0
            gate=(atr[i]>am[i] or not volgate) and lc>0 and er[i]>=er_th and (adx[i]>=adx_th)
            if gate:
                lvlH=rh[i]+buf_atr*atr[i]; lvlL=rl[i]-buf_atr*atr[i]
                tl=(cl[i]>ema[i]) or (not ema_on); ts=(cl[i]<ema[i]) or (not ema_on)
                if hi[i]>=lvlH and tl:
                    pos=1;entry=max(lvlH,o[i]);lots=lc;stop=entry-sd;init_stop=stop;peak=hi[i];hold=0;part=0.0
                elif lo[i]<=lvlL and ts:
                    pos=-1;entry=min(lvlL,o[i]);lots=lc;stop=entry+sd;init_stop=stop;peak=lo[i];hold=0;part=0.0
        out[i]=eq
    return out,(np.array(tr) if tr else np.array([0.0])),pd.DatetimeIndex(df.Date.values)

def metr(eq,tr,dates):
    s=pd.Series(eq,index=dates);final=s.iloc[-1]
    yrs=(dates[-1]-dates[0]).days/365.25 or 1e-9
    cagr=(final/INIT)**(1/yrs)-1 if final>0 else -1
    dd=(s/s.cummax()-1).min()
    w=tr[tr>0];l=tr[tr<0];pf=w.sum()/(-l.sum()) if l.sum()<0 else (99.9 if w.sum()>0 else 0)
    dr=s.resample("1D").last().dropna().pct_change().dropna()
    sh=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    return dict(cagr=cagr,pf=pf,dd=dd,sh=sh,win=(tr>0).mean() if len(tr) else 0,n=len(tr))

# データ(モジュールロード時に1回)
PUB=load_pub("/tmp/xau_h1.csv")          # 2012-2022 (開発/チューニング用)
PUB_OOS=PUB.iloc[int(len(PUB)*0.6):].reset_index(drop=True)
XM=load_xm("/tmp/xm_h1.csv")             # 2023-2025 (完全ホールドアウト)

def evalboth(label,**p):
    """公開OOS と XMホールドアウト の両方で評価して1行表示。"""
    e1,t1,d1=run(PUB_OOS,**p); m1=metr(e1,t1,d1)
    e2,t2,d2=run(XM,**p); m2=metr(e2,t2,d2)
    print(f"  {label:<26} | 公開OOS PF{m1['pf']:.2f} DD{m1['dd']*100:5.1f}% Sh{m1['sh']:+.2f} n{m1['n']:>3}"
          f" | XM PF{m2['pf']:.2f} DD{m2['dd']*100:5.1f}% Sh{m2['sh']:+.2f} n{m2['n']:>3}")
    return m1,m2

if __name__=="__main__":
    print("="*112); print("■ ベースライン (現行: bo12, ER0.30, EMA200, SL2.0, Trail3.0, maxhold72)"); print("="*112)
    evalboth("baseline")
