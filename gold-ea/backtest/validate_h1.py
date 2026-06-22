#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""タイムゾーン非依存・少パラメータ・OOS検証 の頑健バックテスト。

設計(分析の頑健な結論のみ採用):
  - 方向は予測困難 → 長期トレンドフィルタ(H1 EMA)で『逆らわない』だけ
  - ボラはクラスタリング(頑健) → ボラ拡大時のみ参加(ATR>ローリング中央値)
  - 価格はローリングNバーのレンジをブレイクで初動を取る(★絶対時刻に非依存★)
  - ファットテール/下方歪み → 必ずATRハード損切り + リスク連動サイズ
  - 利はATRチャンデリア(トレーリング)で伸ばす。利確固定はしない。
検証:
  - In-Sample(前半60%)でブレイク幅のみ粗くスキャン → 1つ選ぶ
  - その設定の Out-of-Sample(後半40%) 成績を報告(未最適化期間)
  - 全パラメータのOOSも並べ、成績が一点依存(=過剰最適化)でないか確認
  - 往復スプレッドコスト込み(1lot=100oz → cost=SPREAD*100*lots)
"""
import numpy as np, pandas as pd

h=pd.read_csv("/tmp/xau_h1.csv")
h["Date"]=pd.to_datetime(h["Date"])
for c in ["open","high","low","close"]: h[c]=h[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h["ema200"]=h.close.ewm(span=200,adjust=False).mean()
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean()
h["atr_med"]=h.atr.rolling(200).median()

INIT=1000.0; RISK=0.01; SPREAD=0.35

def backtest(df, bo_window=24, sl_atr=2.0, trail_atr=3.0, ema_col="ema200",
             use_trend=True, use_volgate=True, allow_short=True, max_hold=72):
    o=df.open.values; hi=df.high.values; lo=df.low.values; cl=df.close.values
    ema=df[ema_col].values; atr=df.atr.values; atrmed=df.atr_med.values
    n=len(df)
    roll_hi=df.high.rolling(bo_window).max().shift(1).values
    roll_lo=df.low.rolling(bo_window).min().shift(1).values
    equity=INIT; pos=0; entry=stop=lots=0.0; peak=0.0; hold=0
    eq=np.empty(n); trades=[]; bars_in=0
    for i in range(n):
        if np.isnan(ema[i]) or np.isnan(atr[i]) or np.isnan(atrmed[i]) or np.isnan(roll_hi[i]):
            eq[i]=equity; continue
        # 保有中: トレーリング/損切り(intrabar, 保守的にSL優先)
        if pos!=0:
            hold+=1
            if pos>0:
                peak=max(peak,hi[i]); stop=max(stop,peak-trail_atr*atr[i])
                if lo[i]<=stop:
                    g=(stop-entry)*lots*100 - SPREAD*100*lots; equity+=g; trades.append(g); pos=0; hold=0
            else:
                peak=min(peak,lo[i]); stop=min(stop,peak+trail_atr*atr[i])
                if hi[i]>=stop:
                    g=(entry-stop)*lots*100 - SPREAD*100*lots; equity+=g; trades.append(g); pos=0; hold=0
            if pos!=0 and hold>=max_hold:   # 時間切れ
                px=cl[i]; g=((px-entry) if pos>0 else (entry-px))*lots*100 - SPREAD*100*lots
                equity+=g; trades.append(g); pos=0; hold=0
        # 無ポジ: エントリー
        if pos==0:
            volok = (atr[i]>atrmed[i]) if use_volgate else True
            tl = (cl[i]>ema[i]) if use_trend else True
            ts = (cl[i]<ema[i]) if use_trend else True
            sl_dist=sl_atr*atr[i]
            lots_c=max(round(equity*RISK/(sl_dist*100),2),0.0) if sl_dist>0 else 0
            if volok and lots_c>0:
                if hi[i]>=roll_hi[i] and tl:
                    pos=1; entry=max(roll_hi[i],o[i]); lots=lots_c; stop=entry-sl_dist; peak=hi[i]; hold=0
                elif lo[i]<=roll_lo[i] and ts and allow_short:
                    pos=-1; entry=min(roll_lo[i],o[i]); lots=lots_c; stop=entry+sl_dist; peak=lo[i]; hold=0
        if pos!=0: bars_in+=1
        eq[i]=equity
    eqs=pd.Series(eq)
    t=np.array(trades) if trades else np.array([0.0])
    wins=t[t>0]; loss=t[t<0]
    pf=wins.sum()/(-loss.sum()) if loss.sum()<0 else np.inf
    dd=(eqs/eqs.cummax()-1).min()
    days=(df.Date.iloc[-1]-df.Date.iloc[0]).days/365.25
    cagr=(equity/INIT)**(1/days)-1 if equity>0 and days>0 else 0
    rets=eqs.pct_change().replace([np.inf,-np.inf],0).dropna()
    sharpe=rets.mean()/rets.std()*np.sqrt(252*24) if rets.std()>0 else 0
    return dict(final=equity,cagr=cagr,pf=pf,dd=dd,sharpe=sharpe,trades=len(trades),
                win=(t>0).mean() if len(trades) else 0, expo=bars_in/n)

def show(tag,r):
    print(f"  {tag:<22} 最終${r['final']:>6.0f} CAGR{r['cagr']*100:+6.1f}% PF{r['pf']:.2f} "
          f"DD{r['dd']*100:6.1f}% 勝率{r['win']*100:4.1f}% 取引{r['trades']:>4} Sharpe{r['sharpe']:+.2f}")

# IS/OOS分割
split=int(len(h)*0.6)
IS=h.iloc[:split].reset_index(drop=True)
OOS=h.iloc[split:].reset_index(drop=True)
print(f"データ: {h.Date.iloc[0].date()}〜{h.Date.iloc[-1].date()}  ({len(h)}本)")
print(f"In-Sample : {IS.Date.iloc[0].date()}〜{IS.Date.iloc[-1].date()} ({len(IS)})")
print(f"Out-Sample: {OOS.Date.iloc[0].date()}〜{OOS.Date.iloc[-1].date()} ({len(OOS)})\n")

print("="*78); print("■ ステップ1: In-Sampleでブレイク幅のみスキャン（他は事前固定）"); print("="*78)
grid=[12,24,48,72,120]
is_res={}
for bw in grid:
    r=backtest(IS, bo_window=bw); is_res[bw]=r; show(f"BO={bw:>3}本(IS)", r)
best_bw=max(grid, key=lambda bw: is_res[bw]['sharpe'])
print(f"\n→ In-Sample最良(Sharpe基準): BO={best_bw}本")

print("\n"+"="*78); print("■ ステップ2: Out-of-Sample（未最適化期間）で検証 ★本番★"); print("="*78)
oos_best=backtest(OOS, bo_window=best_bw); show(f"BO={best_bw}本(OOS最良)", oos_best)
bh=(OOS.close.iloc[-1]/OOS.close.iloc[0]-1)
print(f"  {'Buy&Hold(OOS基準)':<22} 総リターン{bh*100:+.1f}%")

print("\n"+"="*78); print("■ ステップ3: 全パラメータのOOS成績（一点依存=過剰最適化でないか確認）"); print("="*78)
for bw in grid:
    r=backtest(OOS, bo_window=bw); show(f"BO={bw:>3}本(OOS)", r)

print("\n"+"="*78); print("■ ステップ4: アブレーション（OOS, BO={}）".format(best_bw)); print("="*78)
show("フル戦略",            backtest(OOS,bo_window=best_bw))
show("トレンドフィルタ無し", backtest(OOS,bo_window=best_bw,use_trend=False))
show("ボラゲート無し",      backtest(OOS,bo_window=best_bw,use_volgate=False))
show("ロングのみ",          backtest(OOS,bo_window=best_bw,allow_short=False))

# 結果保存
rows=[]
for label,df,bw in [("IS_best",IS,best_bw),("OOS_best",OOS,best_bw)]:
    r=backtest(df,bo_window=bw); r["set"]=label; r["bo_window"]=bw; rows.append(r)
pd.DataFrame(rows).to_csv("/home/user/toto/gold-ea/backtest/validate_results.csv",index=False)
print("\n[saved] validate_results.csv")
