#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""データ分析の結論に基づく『オリジナル戦略』の設計と建玉ベース検証。

設計仮説(分析の事実から):
  事実1: 日次方向は予測困難だが、ボラはクラスタリングする(予測可能)。
  事実2: 分布はファットテール+下方歪み → 必ずハード損切り、リスク連動サイズ。
  事実3: 短期は弱い順張り、長期は平均回帰 → 長期トレンドに『逆らわない』フィルタ。
→ 戦略: 『トレンド整合ボラティリティ・ブレイクアウト』
   - 長期トレンドフィルタ(EMA200)で方向を制限(順張りのみ)
   - 直近N日レンジのブレイクで初動を取る(Donchian)
   - ボラ拡大ゲート(ATR>ATR中央値)でダマシ局面を回避
   - ATRチャンデリア(トレーリング)で利を伸ばし、ハード初期SL
   - リスク1%でサイズを自動調整(ボラ連動)
比較対象: Buy&Hold / MAクロス(現MVP) / フィルタ無しDonchian
"""
import numpy as np, pandas as pd

d = pd.read_csv("/tmp/xau_d1.csv")
d["Date"]=pd.to_datetime(d["Date"])
for c in ["open","high","low","close"]: d[c]=d[c]/100.0
d=d.sort_values("Date").reset_index(drop=True)

# 指標
def ema(s,n): return s.ewm(span=n,adjust=False).mean()
d["ema200"]=ema(d.close,200)
tr=pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
d["atr"]=tr.rolling(14).mean()
d["atr_med"]=d.atr.rolling(100).median()

INIT=1000.0; RISK=0.01; SPREAD=0.35  # 往復コスト($), XMゴールド想定

def run(donchian=20, sl_atr=2.0, trail_atr=3.0, use_trend=True, use_volgate=True,
        allow_short=True, name="strategy"):
    hh=d.close.rolling(donchian).max().shift(1)
    ll=d.close.rolling(donchian).min().shift(1)
    equity=INIT; pos=0; entry=0.0; stop=0.0; lots=0.0; peak=0.0
    eq_curve=[]; trades=[]; bars_in=0; hold=0
    for i in range(len(d)):
        row=d.iloc[i]
        if np.isnan(row.ema200) or np.isnan(row.atr) or np.isnan(row.atr_med) or np.isnan(hh.iloc[i]):
            eq_curve.append(equity); continue
        # --- 保有中: ストップ/トレーリング判定(高安でintrabar) ---
        if pos!=0:
            hold+=1
            if pos>0:
                peak=max(peak,row.high)
                stop=max(stop, peak-trail_atr*row.atr)   # チャンデリア(切り上げのみ)
                if row.low<=stop:
                    exitp=stop; pnl=(exitp-entry)*lots*100 - SPREAD*lots
                    equity+=pnl; trades.append((pnl,hold)); pos=0; hold=0
            else:
                peak=min(peak,row.low)
                stop=min(stop, peak+trail_atr*row.atr)
                if row.high>=stop:
                    exitp=stop; pnl=(entry-exitp)*lots*100 - SPREAD*lots
                    equity+=pnl; trades.append((pnl,hold)); pos=0; hold=0
        # --- 無ポジ: エントリー判定(終値ベース→当日終値で建てる簡略) ---
        if pos==0:
            volok = (row.atr>row.atr_med) if use_volgate else True
            up = row.close>=hh.iloc[i]; dn=row.close<=ll.iloc[i]
            trend_long = (row.close>row.ema200) if use_trend else True
            trend_short= (row.close<row.ema200) if use_trend else True
            sl_dist=sl_atr*row.atr
            risk_money=equity*RISK
            lots_calc=risk_money/(sl_dist*100) if sl_dist>0 else 0   # 1lot=100oz
            lots_calc=max(round(lots_calc,2),0.0)
            if volok and up and trend_long and lots_calc>0:
                pos=1; entry=row.close; lots=lots_calc; stop=entry-sl_dist; peak=row.high
            elif volok and dn and trend_short and allow_short and lots_calc>0:
                pos=-1; entry=row.close; lots=lots_calc; stop=entry+sl_dist; peak=row.low
        if pos!=0: bars_in+=1
        eq_curve.append(equity)
    eq=pd.Series(eq_curve)
    tr_pnl=np.array([t[0] for t in trades]) if trades else np.array([0.0])
    wins=tr_pnl[tr_pnl>0]; losses=tr_pnl[tr_pnl<0]
    pf=wins.sum()/(-losses.sum()) if losses.sum()<0 else np.inf
    dd=(eq/eq.cummax()-1).min()
    years=(d.Date.iloc[-1]-d.Date.iloc[0]).days/365.25
    cagr=(eq.iloc[-1]/INIT)**(1/years)-1 if eq.iloc[-1]>0 else -1
    rets=eq.pct_change().dropna()
    sharpe=rets.mean()/rets.std()*np.sqrt(252) if rets.std()>0 else 0
    print(f"[{name}]")
    print(f"   最終資金: ${eq.iloc[-1]:.0f}  CAGR:{cagr*100:+.1f}%  総リターン:{(eq.iloc[-1]/INIT-1)*100:+.0f}%")
    print(f"   取引数:{len(trades)}  勝率:{(tr_pnl>0).mean()*100:.1f}%  PF:{pf:.2f}  最大DD:{dd*100:.1f}%  Sharpe:{sharpe:.2f}")
    if len(trades):
        avgw=wins.mean() if len(wins) else 0; avgl=losses.mean() if len(losses) else 0
        print(f"   平均利益:${avgw:.1f}  平均損失:${avgl:.1f}  RR:{(avgw/-avgl if avgl<0 else 0):.2f}  平均保有:{np.mean([t[1] for t in trades]):.1f}日  建玉率:{bars_in/len(d)*100:.0f}%")
    return dict(name=name,final=float(eq.iloc[-1]),cagr=float(cagr),pf=float(pf),dd=float(dd),sharpe=float(sharpe),trades=len(trades),eq=eq)

print("="*64); print("■ 戦略比較（建玉ベース, コスト$0.35/往復込み, 初期$1000, リスク1%）"); print("="*64)
results=[]
results.append(run(use_trend=True, use_volgate=True, allow_short=True,  name="本命: トレンド整合ボラブレイク(L/S)"))
print()
results.append(run(use_trend=True, use_volgate=True, allow_short=False, name="本命の派生: ロングのみ"))
print()
results.append(run(use_trend=True, use_volgate=False, allow_short=True, name="アブレーション: ボラゲート無し"))
print()
results.append(run(use_trend=False,use_volgate=True, allow_short=True,  name="アブレーション: トレンドフィルタ無し"))
print()
results.append(run(donchian=10, use_trend=True, use_volgate=True, allow_short=True, name="感度: Donchian10"))
print()
results.append(run(donchian=40, use_trend=True, use_volgate=True, allow_short=True, name="感度: Donchian40"))

# 期間別ロバストネス(本命)
print("\n"+"="*64); print("■ 本命戦略の年別リターン（ロバストネス確認）"); print("="*64)
best=results[0]["eq"]; d["eq"]=best.values
d["year"]=d.Date.dt.year
yr=d.groupby("year")["eq"].agg(["first","last"])
for y,row in yr.iterrows():
    r=(row["last"]/row["first"]-1)*100
    bar="█"*int(abs(r)/3)
    print(f"  {y}: {r:+6.1f}%  {bar}")

pd.DataFrame([{k:v for k,v in r.items() if k!='eq'} for r in results]).to_csv(
    "/home/user/toto/gold-ea/backtest/design_results.csv",index=False)
best.to_csv("/home/user/toto/gold-ea/backtest/equity_curve.csv")
print("\n[saved] design_results.csv / equity_curve.csv")
