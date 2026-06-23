#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XM実データ・全時間足での GoldVBO(+ERフィルタ) 横断検証。

各時間足でVBO+ER(0.30固定)を回し、ブレイク幅boをIS(前半60%)で最適化→OOS(後半40%)評価。
低時間足はスプレッド負けしやすいので、複数コストで感応度も見る。
XM CSV形式: date,time,O,H,L,C,V (実価格)。時間足ごとに取得期間が違う点に注意。
"""
import numpy as np, pandas as pd
INIT=1000.0; RISK=0.01

def load(path):
    d=pd.read_csv(path,header=None,names=["dd","tt","open","high","low","close","vol"])
    d["Date"]=pd.to_datetime(d["dd"]+" "+d["tt"],format="%Y.%m.%d %H:%M")
    d=d.sort_values("Date").reset_index(drop=True)
    d["ema200"]=d.close.ewm(span=200,adjust=False).mean()
    tr=pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    d["atr"]=tr.rolling(14).mean(); d["atr_med"]=d.atr.rolling(200).median()
    c=d.close.values; net=np.abs(c-np.roll(c,20))
    vol=pd.Series(np.abs(np.diff(c,prepend=c[0]))).rolling(20).sum().values
    er=np.where(vol>0,net/vol,0.0); er[:20]=np.nan; d["er"]=er
    return d

def bt(df,bo=24,sl_atr=2.0,trail=3.0,maxhold=72,er_th=0.30,SPREAD=0.30):
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;atr=df.atr.values;am=df.atr_med.values;er=df.er.values
    rh=df.high.rolling(bo).max().shift(1).values; rl=df.low.rolling(bo).min().shift(1).values
    eq=INIT;pos=0;entry=stop=lots=0.0;peak=0.0;hold=0;out=np.empty(len(df));tr=[]
    for i in range(len(df)):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(am[i]) or np.isnan(rh[i]) or np.isnan(er[i]): out[i]=eq;continue
        if pos!=0:
            hold+=1
            if pos>0:
                peak=max(peak,hi[i]);stop=max(stop,peak-trail*atr[i])
                if lo[i]<=stop: g=(stop-entry)*lots*100-SPREAD*100*lots;eq+=g;tr.append(g);pos=0;hold=0
            else:
                peak=min(peak,lo[i]);stop=min(stop,peak+trail*atr[i])
                if hi[i]>=stop: g=(entry-stop)*lots*100-SPREAD*100*lots;eq+=g;tr.append(g);pos=0;hold=0
            if pos!=0 and hold>=maxhold:
                px=cl[i];g=((px-entry) if pos>0 else (entry-px))*lots*100-SPREAD*100*lots;eq+=g;tr.append(g);pos=0;hold=0
        if pos==0:
            sd=sl_atr*atr[i];lc=max(eq*RISK/(sd*100),0.0) if sd>0 else 0  # 連続ロット(口座サイズ非依存)
            if atr[i]>am[i] and lc>0 and er[i]>=er_th:
                if hi[i]>=rh[i] and cl[i]>ema[i]: pos=1;entry=max(rh[i],o[i]);lots=lc;stop=entry-sd;peak=hi[i];hold=0
                elif lo[i]<=rl[i] and cl[i]<ema[i]: pos=-1;entry=min(rl[i],o[i]);lots=lc;stop=entry+sd;peak=lo[i];hold=0
        out[i]=eq
    return out,(np.array(tr) if tr else np.array([0.0]))

def metr(eq,tr,dates):
    s=pd.Series(eq,index=dates);final=s.iloc[-1]
    yrs=(dates[-1]-dates[0]).days/365.25 or 1e-9
    cagr=(final/INIT)**(1/yrs)-1 if final>0 else -1
    dd=(s/s.cummax()-1).min()
    w=tr[tr>0];l=tr[tr<0];pf=w.sum()/(-l.sum()) if l.sum()<0 else np.inf
    dr=s.resample("1D").last().dropna().pct_change().dropna()
    sh=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    return dict(cagr=cagr,pf=pf,dd=dd,sh=sh,win=(tr>0).mean() if len(tr) else 0,n=len(tr),yrs=yrs)

# (TF, path, boグリッド, maxhold, デフォルトスプレッド)
TFS=[("M5","/tmp/xm_m5.csv",[24,48,96],288),
     ("M15","/tmp/xm_m15.csv",[16,32,64],96),
     ("M30","/tmp/xm_m30.csv",[16,32,64],96),
     ("H1","/tmp/xm_h1.csv",[12,24,48],72),
     ("H4","/tmp/xm_h4.csv",[12,24,48],60),
     ("D1","/tmp/xm_d1.csv",[10,20,40],20)]
ER_FIX=0.30

if __name__=="__main__":
    summary={}
    for name,path,bos,mh in TFS:
        d=load(path); n=len(d)
        sp=int(n*0.6); IS=d.iloc[:sp].reset_index(drop=True); OOS=d.iloc[sp:].reset_index(drop=True)
        disp=pd.DatetimeIndex(IS.Date.values); dosp=pd.DatetimeIndex(OOS.Date.values)
        cand=[]
        for bo in bos:
            e,t=bt(IS,bo=bo,maxhold=mh,er_th=ER_FIX); m=metr(e,t,disp)
            cand.append((m['sh'],bo,m['n']))
        cand.sort(key=lambda x:x[0],reverse=True); bbo=cand[0][1]
        print("="*92)
        print(f"■ {name}  {d.Date.iloc[0].date()}〜{d.Date.iloc[-1].date()} ({n}本)  IS最良bo={bbo}")
        # OOSをスプレッド別に
        for SP in [0.20,0.30,0.45]:
            e,t=bt(OOS,bo=bbo,maxhold=mh,er_th=ER_FIX,SPREAD=SP); m=metr(e,t,dosp)
            tpy=m['n']/m['yrs']
            tag="  ←主コスト" if SP==0.30 else ""
            print(f"   OOS cost${SP:.2f}: CAGR{m['cagr']*100:+7.1f}% PF{m['pf']:.2f} DD{m['dd']*100:6.1f}% "
                  f"勝率{m['win']*100:4.1f}% 取引{m['n']:>4}({tpy:.0f}/年) Sharpe{m['sh']:+.2f}{tag}")
        summary[name]=bbo
    print("\n採用boまとめ:",summary)
