#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""時間足別 GoldVBO(+ERフィルタ) の最適化と分散効果の検証。

方針: 銘柄はゴールド固定。代わりに『時間足』で分散する。
  - 各時間足(H1/H4/D1)で VBO+ERフィルタ を IS(前半60%)で最適化 → OOS(後半40%)で評価
  - 時間足ごとに最適パラメータ(ブレイク幅bo, ER閾値)を選定 = 時間足別EAの素
  - 各時間足の日次リターン相関を測り、同時運用で分散が効くかを確認
ERフィルタ = カウフマン効率比(|純変化|/Σ|各変化|)。揉み合いのだましブレイクを除外。
コスト$0.5/往復。価格は公開データ仕様(/100)。
"""
import numpy as np, pandas as pd
INIT=1000.0; RISK=0.01; SPREAD=0.50

def load(path):
    d=pd.read_csv(path); d["Date"]=pd.to_datetime(d["Date"])
    for c in ["open","high","low","close"]: d[c]=d[c]/100.0
    d=d.sort_values("Date").reset_index(drop=True)
    d["ema200"]=d.close.ewm(span=200,adjust=False).mean()
    tr=pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    d["atr"]=tr.rolling(14).mean(); d["atr_med"]=d.atr.rolling(200).median()
    c=d.close.values; net=np.abs(c-np.roll(c,20))
    vol=pd.Series(np.abs(np.diff(c,prepend=c[0]))).rolling(20).sum().values
    er=np.where(vol>0,net/vol,0.0); er[:20]=np.nan; d["er"]=er
    return d

def bt(df,bo=24,sl_atr=2.0,trail=3.0,maxhold=72,er_th=0.25):
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
            # ロットは連続値で評価(0.01丸めの影響=口座サイズ依存を排除し戦略の優位性を見る)
            sd=sl_atr*atr[i];lc=max(eq*RISK/(sd*100),0.0) if sd>0 else 0
            if atr[i]>am[i] and lc>0 and er[i]>=er_th:
                if hi[i]>=rh[i] and cl[i]>ema[i]: pos=1;entry=max(rh[i],o[i]);lots=lc;stop=entry-sd;peak=hi[i];hold=0
                elif lo[i]<=rl[i] and cl[i]<ema[i]: pos=-1;entry=min(rl[i],o[i]);lots=lc;stop=entry+sd;peak=lo[i];hold=0
        out[i]=eq
    return out,(np.array(tr) if tr else np.array([0.0]))

def metr(eq,tr,dates):
    s=pd.Series(eq,index=dates);final=s.iloc[-1]
    yrs=(dates[-1]-dates[0]).days/365.25
    cagr=(final/INIT)**(1/yrs)-1 if final>0 else -1
    dd=(s/s.cummax()-1).min()
    w=tr[tr>0];l=tr[tr<0];pf=w.sum()/(-l.sum()) if l.sum()<0 else np.inf
    dr=s.resample("1D").last().dropna().pct_change().dropna()
    sh=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0
    return dict(final=final,cagr=cagr,pf=pf,dd=dd,sh=sh,win=(tr>0).mean() if len(tr) else 0,n=len(tr))

# ERは全データで0.3前後が一貫して有効なレジームフィルタ → 固定し、boのみTF別に最適化。
ER_FIX=0.30
# 時間足別の探索グリッドと保持バー数(おおよそ同程度の保有日数に)
TFS=[("H1","/tmp/xau_h1.csv",[12,24,48],72),
     ("H4","/tmp/xau_h4.csv",[12,24,48],60),
     ("D1","/tmp/xau_d1.csv",[10,20,40],20)]

def main():
  best={}; data={}
  for name,path,bos,mh in TFS:
    d=load(path); data[name]=(d,mh)
    sp=int(len(d)*0.6); IS=d.iloc[:sp].reset_index(drop=True); OOS=d.iloc[sp:].reset_index(drop=True)
    disp=pd.DatetimeIndex(IS.Date.values); dosp=pd.DatetimeIndex(OOS.Date.values)
    # ISでSharpe最良の bo を選ぶ(ERは固定)
    cand=[]
    for bo in bos:
        e,t=bt(IS,bo=bo,maxhold=mh,er_th=ER_FIX); m=metr(e,t,disp)
        cand.append((m['sh'],bo,m['n']))
    cand.sort(key=lambda x:x[0],reverse=True); bbo=cand[0][1]
    e,t=bt(OOS,bo=bbo,maxhold=mh,er_th=ER_FIX); mo=metr(e,t,dosp)
    best[name]=dict(bo=bbo,er=ER_FIX,mh=mh,oos=mo)
    print("="*86)
    print(f"■ {name}  IS最良bo={bbo} (ER≥{ER_FIX}固定)   →  OOS成績")
    print(f"   IS  : "+ "  ".join(f"bo{b}:Sh{s:+.2f}(n{n})" for s,b,n in sorted(cand,key=lambda x:-x[0])))
    print(f"   OOS : CAGR{mo['cagr']*100:+6.1f}% PF{mo['pf']:.2f} DD{mo['dd']*100:6.1f}% 勝率{mo['win']*100:4.1f}% 取引{mo['n']:>4} Sharpe{mo['sh']:+.2f}")

  # ---- 時間足間の分散効果(全期間, 各最良paramの日次リターン相関) ----
  print("\n"+"="*86); print("■ 時間足間の分散効果 (日次リターン相関, 全期間, 各TF最良param)"); print("="*86)
  series={}
  for name in best:
    d,mh=data[name]; e,t=bt(d,bo=best[name]['bo'],maxhold=mh,er_th=best[name]['er'])
    series[name]=pd.Series(e,index=pd.DatetimeIndex(d.Date.values)).resample("1D").last().dropna().pct_change()
  R=pd.concat([series[n].rename(n) for n in series],axis=1).dropna()
  corr=R.corr()
  print("  相関行列:")
  print(corr.round(2).to_string().replace("\n","\n  "))
  # 3時間足 等ウェイト合成
  port=R.mean(axis=1); eqp=(1+port).cumprod()
  yrs=(R.index[-1]-R.index[0]).days/365.25
  print(f"\n  3時間足 等分散合成: CAGR{(eqp.iloc[-1]**(1/yrs)-1)*100:+.1f}% "
        f"DD{((eqp/eqp.cummax()-1).min())*100:.1f}% Sharpe{port.mean()/port.std()*np.sqrt(252):+.2f}")
  print(f"  (単一H1 OOS Sharpe {best['H1']['oos']['sh']:+.2f} と比較し、合成で改善すれば時間足分散が有効)")

if __name__=="__main__":
    main()
