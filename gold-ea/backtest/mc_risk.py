#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""モンテカルロ・リスク分析: GoldVBO(H1,+ER) の現実的な最悪DDとリスク許容量を定量化。

バックテストは『起きた一本の歴史』に過ぎず、最悪DDを過小評価しがち。
ここでは各取引の R倍数(= 損益 / その時のリスク額) を取引プールにし、順序をシャッフル+
復元抽出して数千通りの資産曲線を生成。固定比率(リスク%)で複利運用したときの:
  - 最大ドローダウンの分布(中央値/95%点/最悪)
  - 破産確率(資産が半減する確率)
  - 最終リターンの分布
を リスク% 別に出す。

取引プールは『全レジーム』にするため、公開データ2012-2022(2018チョップ含む)と
XM実データ2023-2025 の両方の取引を合算。コスト$0.35。
"""
import numpy as np, pandas as pd
INIT=1000.0; RISK_BASE=0.01

def _prep(d):
    d=d.sort_values("Date").reset_index(drop=True)
    d["ema200"]=d.close.ewm(span=200,adjust=False).mean()
    tr=pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    d["atr"]=tr.rolling(14).mean(); d["atr_med"]=d.atr.rolling(200).median()
    c=d.close.values; net=np.abs(c-np.roll(c,20))
    vol=pd.Series(np.abs(np.diff(c,prepend=c[0]))).rolling(20).sum().values
    er=np.where(vol>0,net/vol,0.0); er[:20]=np.nan; d["er"]=er
    return d
def load_pub(path):
    d=pd.read_csv(path); d["Date"]=pd.to_datetime(d["Date"])
    for c in ["open","high","low","close"]: d[c]=d[c]/100.0
    return _prep(d)
def load_xm(path):
    d=pd.read_csv(path,header=None,names=["dd","tt","open","high","low","close","vol"])
    d["Date"]=pd.to_datetime(d["dd"]+" "+d["tt"],format="%Y.%m.%d %H:%M")
    return _prep(d)

def trade_Rs(df,bo=12,sl_atr=2.0,trail=3.0,maxhold=72,er_th=0.30,SPREAD=0.35):
    """各取引の R倍数(損益/エントリー時リスク額)を返す。リスク額=eq*RISK_BASE。"""
    o=df.open.values;hi=df.high.values;lo=df.low.values;cl=df.close.values
    ema=df.ema200.values;atr=df.atr.values;am=df.atr_med.values;er=df.er.values
    rh=df.high.rolling(bo).max().shift(1).values; rl=df.low.rolling(bo).min().shift(1).values
    eq=INIT;pos=0;entry=stop=lots=0.0;peak=0.0;hold=0;risk0=0.0;Rs=[]
    for i in range(len(df)):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(am[i]) or np.isnan(rh[i]) or np.isnan(er[i]): continue
        if pos!=0:
            hold+=1; g=None
            if pos>0:
                peak=max(peak,hi[i]);stop=max(stop,peak-trail*atr[i])
                if lo[i]<=stop: g=(stop-entry)*lots*100-SPREAD*100*lots
            else:
                peak=min(peak,lo[i]);stop=min(stop,peak+trail*atr[i])
                if hi[i]>=stop: g=(entry-stop)*lots*100-SPREAD*100*lots
            if g is None and hold>=maxhold:
                g=((cl[i]-entry) if pos>0 else (entry-cl[i]))*lots*100-SPREAD*100*lots
            if g is not None:
                eq+=g; Rs.append(g/risk0 if risk0>0 else 0.0); pos=0;hold=0
        if pos==0:
            sd=sl_atr*atr[i];lc=max(eq*RISK_BASE/(sd*100),0.0) if sd>0 else 0
            if atr[i]>am[i] and lc>0 and er[i]>=er_th:
                if hi[i]>=rh[i] and cl[i]>ema[i]: pos=1;entry=max(rh[i],o[i]);lots=lc;stop=entry-sd;peak=hi[i];hold=0;risk0=eq*RISK_BASE
                elif lo[i]<=rl[i] and cl[i]<ema[i]: pos=-1;entry=min(rl[i],o[i]);lots=lc;stop=entry+sd;peak=lo[i];hold=0;risk0=eq*RISK_BASE
    return np.array(Rs)

# 全レジームの取引プールを構築
pool=np.concatenate([
    trade_Rs(load_pub("/tmp/xau_h1.csv"),bo=12),   # 2012-2022(2018チョップ/2013暴落 含む)
    trade_Rs(load_xm("/tmp/xm_h1.csv"),bo=12),      # 2023-2025(強気)
])
wins=pool[pool>0]; losses=pool[pool<=0]
print("="*78)
print(f"■ 取引プール(全レジーム H1+ER): {len(pool)}取引  勝率{(pool>0).mean()*100:.1f}%")
print(f"  平均R {pool.mean():+.2f}  勝ち平均{wins.mean():+.2f}R  負け平均{losses.mean():+.2f}R  期待値{pool.mean():+.3f}R/取引")
print("="*78)

def simulate(pool,risk,n_trades,n_sims=5000,seed=1,block=1):
    """block=1: iid復元抽出。block>1: 連続ブロック抽出(連敗のクラスタリングを保持)。"""
    rng=np.random.default_rng(seed)
    maxdd=np.empty(n_sims); finalr=np.empty(n_sims); N=len(pool)
    for s in range(n_sims):
        if block<=1:
            draw=rng.choice(pool,size=n_trades,replace=True)
        else:
            chunks=[]
            while sum(len(c) for c in chunks)<n_trades:
                st=rng.integers(0,N); chunks.append(pool[st:st+block])
            draw=np.concatenate(chunks)[:n_trades]
        eq=1.0;peak=1.0;mdd=0.0
        for R in draw:
            eq*= (1.0 + risk*R)
            if eq>peak: peak=eq
            dd=eq/peak-1.0
            if dd<mdd: mdd=dd
            if eq<=0: eq=1e-9
        maxdd[s]=mdd; finalr[s]=eq-1.0
    return maxdd,finalr

YEARS=3; per_year=int(len(pool)/((2022-2012)+ (2025-2023)))  # おおよその年間取引数
n_tr=max(per_year*YEARS,150)
print(f"想定運用 {YEARS}年(≈{n_tr}取引) / {5000}シミュレーション\n")
print("【A. iid抽出(取引は独立と仮定)】")
print(f"  {'リスク%':>6}{'最終(中央)':>11}{'最終(5%)':>10}{'最大DD中央':>11}{'最大DD95%':>11}{'最悪DD':>9}{'破産率':>8}")
for risk in [0.005,0.01,0.015,0.02,0.03]:
    mdd,fr=simulate(pool,risk,n_tr,block=1)
    ruin=(fr<=-0.5).mean()
    print(f"  {risk*100:>5.1f}%{np.median(fr)*100:>+10.0f}%{np.percentile(fr,5)*100:>+9.0f}%"
          f"{np.median(mdd)*100:>10.0f}%{np.percentile(mdd,5)*100:>10.0f}%{mdd.min()*100:>8.0f}%{ruin*100:>7.1f}%")
print("\n【B. ブロック抽出(連敗のクラスタリングを保持=より現実的で厳しい)】 block=20取引")
print(f"  {'リスク%':>6}{'最終(中央)':>11}{'最終(5%)':>10}{'最大DD中央':>11}{'最大DD95%':>11}{'最悪DD':>9}{'破産率':>8}")
for risk in [0.005,0.01,0.015,0.02,0.03]:
    mdd,fr=simulate(pool,risk,n_tr,block=20)
    ruin=(fr<=-0.5).mean()
    print(f"  {risk*100:>5.1f}%{np.median(fr)*100:>+10.0f}%{np.percentile(fr,5)*100:>+9.0f}%"
          f"{np.median(mdd)*100:>10.0f}%{np.percentile(mdd,5)*100:>10.0f}%{mdd.min()*100:>8.0f}%{ruin*100:>7.1f}%")
print("\n  ※最大DD95%=95%のケースがこれより浅い(=20回に1回はこれ以上沈む)。最悪DD=全シミュ中最悪。")
print("  ※破産率=3年で資産が半減(-50%)以下になった割合。")
