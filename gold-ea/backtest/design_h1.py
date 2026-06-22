#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H1(時間足)での日中ブレイクアウト戦略の設計・検証。

分析の最強エッジ = (1)セッション効果(15-17時サーバーが突出して活発)
                   (2)ボラのクラスタリング(拡大は持続しやすい)
→ オリジナル戦略『セッション・オープニングレンジ・ブレイクアウト(ORB)』:
   - 静穏帯(早朝)に作られた値幅 = "基準レンジ" を計測
   - 活発化する時間帯にレンジ上抜け→買い / 下抜け→売り (ボラ拡大の初動)
   - 損切り = レンジ反対側 / 利確 = R倍 + 時間切れ(終盤に強制決済=オーバーナイト回避)
   多数のトレードが出るため統計的に検証可能。コスト(往復スプレッド)込み。
"""
import numpy as np, pandas as pd

h=pd.read_csv("/tmp/xau_h1.csv")
h["Date"]=pd.to_datetime(h["Date"])
for c in ["open","high","low","close"]: h[c]=h[c]/100.0
h=h.sort_values("Date").reset_index(drop=True)
h["day"]=h.Date.dt.date; h["hour"]=h.Date.dt.hour
# ATR(H1, 14) for sizing
tr=pd.concat([(h.high-h.low),(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1)
h["atr"]=tr.rolling(14).mean()

INIT=1000.0; RISK=0.01; SPREAD=0.35  # 往復$ (1lot=100ozなのでコスト=SPREAD*100*lots)

def backtest(range_hours, entry_start, entry_end, exit_hour, tp_R=1.5,
             allow_short=True, min_range_atr=0.5, name="ORB"):
    equity=INIT; eq_curve=[]; trades=[]
    for day,g in h.groupby("day"):
        g=g.sort_values("hour")
        rng=g[g.hour.isin(range_hours)]
        if len(rng)<len(range_hours): continue
        rhi=rng.high.max(); rlo=rng.low.min(); rwidth=rhi-rlo
        atr=g.atr.iloc[0]
        if np.isnan(atr) or rwidth<=0: continue
        # レンジが狭すぎ(=ボラ枯れ)はスキップ。広すぎ(既に動いた)もスキップ
        if rwidth < min_range_atr*atr: continue
        sess=g[(g.hour>entry_start)&(g.hour<=entry_end)].sort_values("hour")
        pos=0; entry=0; stop=0; lots=0; tp=0
        for _,bar in sess.iterrows():
            if pos==0:
                # ブレイク判定(高安でタッチ)
                long_sig = bar.high>=rhi; short_sig=bar.low<=rlo
                sl_dist=rwidth  # 損切りはレンジ反対側=rwidth
                lots=max(round(equity*RISK/(sl_dist*100),2),0.0)
                if lots<=0: continue
                if long_sig:
                    pos=1; entry=rhi; stop=rhi-sl_dist; tp=rhi+tp_R*sl_dist
                elif short_sig and allow_short:
                    pos=-1; entry=rlo; stop=rlo+sl_dist; tp=rlo-tp_R*sl_dist
            else:
                # 同一バー内で先にSL/TPどちらに触れたか(保守的にSL優先)
                if pos>0:
                    if bar.low<=stop: pnl=(stop-entry); pos2=0
                    elif bar.high>=tp: pnl=(tp-entry); pos2=0
                    else: pos2=pos; pnl=None
                else:
                    if bar.high>=stop: pnl=(entry-stop); pos2=0
                    elif bar.low<=tp: pnl=(entry-tp); pos2=0
                    else: pos2=pos; pnl=None
                if pnl is not None:
                    gross=pnl*lots*100 - SPREAD*100*lots
                    equity+=gross; trades.append(gross); pos=0
            if bar.hour>=exit_hour and pos!=0:
                # 時間切れ強制決済(そのバー終値)
                px=bar.close
                pnl=(px-entry) if pos>0 else (entry-px)
                gross=pnl*lots*100 - SPREAD*100*lots
                equity+=gross; trades.append(gross); pos=0
        if pos!=0:  # 念のため日跨ぎ前にクローズ
            px=sess.close.iloc[-1]; pnl=(px-entry) if pos>0 else (entry-px)
            equity+=pnl*lots*100 - SPREAD*100*lots; trades.append(pnl*lots*100); pos=0
        eq_curve.append((day,equity))
    eq=pd.Series([e for _,e in eq_curve])
    t=np.array(trades) if trades else np.array([0.0])
    wins=t[t>0]; losses=t[t<0]
    pf=wins.sum()/(-losses.sum()) if losses.sum()<0 else np.inf
    dd=(eq/eq.cummax()-1).min() if len(eq) else 0
    years=(h.Date.iloc[-1]-h.Date.iloc[0]).days/365.25
    cagr=(equity/INIT)**(1/years)-1 if equity>0 else -1
    print(f"[{name}] レンジ{range_hours} entry({entry_start}-{entry_end}] exit{exit_hour} TP={tp_R}R")
    print(f"   最終:${equity:.0f} CAGR:{cagr*100:+.1f}% 取引:{len(trades)} 勝率:{(t>0).mean()*100:.1f}% PF:{pf:.2f} 最大DD:{dd*100:.1f}%")
    if len(t)>1:
        print(f"   平均利益:${wins.mean() if len(wins) else 0:.2f} 平均損失:${losses.mean() if len(losses) else 0:.2f} 期待値:${t.mean():+.3f}/トレード")
    return dict(name=name,final=float(equity),cagr=float(cagr),pf=float(pf),dd=float(dd),trades=len(trades),eq=eq,years=years)

print("="*70); print("■ H1 セッションORB 戦略スクリーニング（コスト込, $1000, リスク1%）"); print("="*70)
R=[]
# 静穏帯(早朝0-7)でレンジ→活発帯(8-18)でブレイク→22時手仕舞い
R.append(backtest([1,2,3,4,5,6,7], 7, 18, 22, tp_R=1.5, name="ORB-A 早朝レンジ→日中ブレイク"))
print()
R.append(backtest([1,2,3,4,5,6,7], 7, 18, 22, tp_R=2.0, name="ORB-A TP2.0R"))
print()
R.append(backtest([5,6,7,8], 8, 17, 21, tp_R=1.5, name="ORB-B ロンドン前レンジ"))
print()
R.append(backtest([1,2,3,4,5,6,7], 7, 18, 22, tp_R=1.5, allow_short=False, name="ORB-A ロングのみ"))
print()
R.append(backtest([1,2,3,4,5,6,7], 7, 18, 22, tp_R=1.0, name="ORB-A TP1.0R"))
print()
R.append(backtest([1,2,3,4,5,6,7], 7, 18, 22, tp_R=3.0, name="ORB-A TP3.0R"))

# 最良の年別
best=max(R,key=lambda x:x["cagr"])
print("\n"+"="*70); print(f"■ 最良戦略 [{best['name']}] の年別リターン"); print("="*70)
# 再計算でエクイティと日付を紐付け
print(f"  CAGR {best['cagr']*100:.1f}% / PF {best['pf']:.2f} / DD {best['dd']*100:.1f}% / {best['trades']}トレード")

pd.DataFrame([{k:v for k,v in r.items() if k!='eq'} for r in R]).to_csv(
    "/home/user/toto/gold-ea/backtest/h1_results.csv",index=False)
print("\n[saved] h1_results.csv")
