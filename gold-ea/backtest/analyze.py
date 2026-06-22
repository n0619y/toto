#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XAUUSD ヒストリカルデータ分析: 戦略設計のための統計的性質の抽出。"""
import numpy as np, pandas as pd, json, sys

D1 = "/tmp/xau_d1.csv"; H1 = "/tmp/xau_h1.csv"

def load(path, scale=100.0):
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"])
    for c in ["open","high","low","close"]:
        df[c] = df[c]/scale
    return df.sort_values("Date").reset_index(drop=True)

d = load(D1); h = load(H1)
out = []
def p(*a):
    s=" ".join(str(x) for x in a); out.append(s); print(s)

p("="*64); p("■ データ概要"); p("="*64)
p(f"D1: {len(d)}本  {d.Date.min().date()} 〜 {d.Date.max().date()}")
p(f"H1: {len(h)}本  {h.Date.min()} 〜 {h.Date.max()}")
p(f"価格レンジ(D1 close): ${d.close.min():.1f} 〜 ${d.close.max():.1f}")

# ---- 日次リターン分布 ----
d["ret"] = d.close.pct_change()
r = d.ret.dropna()
p("\n"+"="*64); p("■ 日次リターン分布（ファットテール/非対称の確認）"); p("="*64)
p(f"平均日次: {r.mean()*100:.4f}%   年率換算: {r.mean()*252*100:.1f}%")
p(f"日次ボラ: {r.std()*100:.3f}%   年率ボラ: {r.std()*np.sqrt(252)*100:.1f}%")
p(f"歪度 skew: {r.skew():.3f}  （負=下落が急）")
p(f"尖度 kurtosis(超過): {r.kurtosis():.3f}  （>0=ファットテール=急変多い）")
p(f"最大上昇日: +{r.max()*100:.2f}%   最大下落日: {r.min()*100:.2f}%")

# ---- Buy&Hold のドローダウン ----
eq = (1+r).cumprod()
dd = (eq/eq.cummax()-1)
p(f"\nBuy&Hold 累積: {(eq.iloc[-1]-1)*100:.1f}%   最大DD: {dd.min()*100:.1f}%")

# ---- トレンド vs 平均回帰: 自己相関 & 分散比 ----
p("\n"+"="*64); p("■ トレンド性 vs 平均回帰性（戦略の根幹）"); p("="*64)
p("日次リターンの自己相関(ACF):")
for lag in [1,2,3,5,10]:
    ac = r.autocorr(lag)
    tag = "→モメンタム" if ac>0 else "→反転"
    p(f"  lag{lag:>2}: {ac:+.4f} {tag}")

def variance_ratio(series, q):
    x = np.log(series).diff().dropna().values
    n=len(x); mu=x.mean()
    va=((x-mu)**2).sum()/n
    y=np.cumsum(x);
    # q期リターンの分散
    z=[]
    for i in range(q, n+1):
        z.append((y[i-1]-y[i-q]) if i-q>=0 else np.nan)
    rq = np.log(series).diff(q).dropna().values
    vq = ((rq-q*mu)**2).sum()/(len(rq))
    return (vq/q)/va
p("\n分散比 VR(q)  （>1=トレンド傾向, <1=平均回帰傾向, =1=ランダム）:")
for q in [2,5,10,20]:
    vr=variance_ratio(d.close.dropna(), q)
    p(f"  q={q:>2}日: VR={vr:.3f}")

# ---- ボラティリティ・クラスタリング ----
p("\nボラのクラスタリング（|ret|の自己相関; 高い=GARCH的, ブレイク戦略に有利）:")
ar=r.abs()
for lag in [1,5,10]:
    p(f"  lag{lag:>2}: {ar.autocorr(lag):+.4f}")

# ---- ATR(14) 水準 ----
tr = pd.concat([(d.high-d.low),(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
atr=tr.rolling(14).mean()
p(f"\nATR(14) 中央値: ${atr.median():.2f}  （SL/TP幅・ロット計算の目安）")
p(f"ATR/price 中央値: {(atr/d.close).median()*100:.2f}%")

# ---- 曜日効果 ----
p("\n"+"="*64); p("■ 曜日効果"); p("="*64)
d["dow"]=d.Date.dt.dayofweek
for name,g in [("月",0),("火",1),("水",2),("木",3),("金",4)]:
    sub=d[d.dow==g].ret.dropna()
    p(f"  {name}: 平均{sub.mean()*100:+.3f}%  勝率{(sub>0).mean()*100:.1f}%  n={len(sub)}")

# ---- 時間帯(セッション)効果: H1 ----
p("\n"+"="*64); p("■ 時間帯(セッション)効果  ※H1のサーバー時間ベース"); p("="*64)
h["ret"]=h.close.pct_change()
h["hour"]=h.Date.dt.hour
hr=h.groupby("hour").agg(absret=("ret",lambda x:x.abs().mean()),
                          meanret=("ret","mean"), n=("ret","size"))
hr["absret_bp"]=hr.absret*1e4; hr["meanret_bp"]=hr.meanret*1e4
p("時(サーバー) | 平均|変動|(bp) | 平均方向(bp) | 本数")
for hh,row in hr.iterrows():
    bar="█"*int(row.absret_bp/ hr.absret_bp.max()*30)
    p(f"  {hh:>2}時 | {row.absret_bp:6.1f} | {row.meanret_bp:+6.2f} | {bar}")
peak=hr.absret_bp.idxmax(); quiet=hr.absret_bp.idxmin()
p(f"\n最も活発: {peak}時台   最も静穏: {quiet}時台")

# ---- 戦略仮説の簡易検定（コスト無視のエッジ確認） ----
p("\n"+"="*64); p("■ 戦略仮説のエッジ検定（D1, 翌日リターンで評価, コスト未考慮）"); p("="*64)
def evaluate(signal, ret, name):
    # signal: +1 long / -1 short / 0 flat  (当日終値で判断→翌日リターン取得)
    pos=signal.shift(1).fillna(0)
    pnl=pos*ret
    pnl=pnl.dropna()
    act=pnl[pos.shift(0).reindex(pnl.index).fillna(0)!=0]
    trades=(pos.diff().abs()>0).sum()
    gross_p=pnl[pnl>0].sum(); gross_l=-pnl[pnl<0].sum()
    pf=gross_p/gross_l if gross_l>0 else np.inf
    sharpe=pnl.mean()/pnl.std()*np.sqrt(252) if pnl.std()>0 else 0
    eq=(1+pnl).cumprod(); mdd=(eq/eq.cummax()-1).min()
    expo=(pos!=0).mean()
    p(f"  [{name}]")
    p(f"     年率: {pnl.mean()*252*100:+6.1f}%  Sharpe:{sharpe:+.2f}  PF:{pf:.2f}  最大DD:{mdd*100:.1f}%  建玉率:{expo*100:.0f}%  転換:{trades}")
    return dict(name=name,ann=pnl.mean()*252,sharpe=float(sharpe),pf=float(pf),mdd=float(mdd))

c=d.close
res=[]
# 1) 単純Buy&Hold
res.append(evaluate(pd.Series(1,index=d.index), d.ret, "Buy&Hold(基準)"))
# 2) MAクロス 20/50 (現MVP相当)
ma_f=c.rolling(20).mean(); ma_s=c.rolling(50).mean()
res.append(evaluate(np.sign(ma_f-ma_s), d.ret, "MAクロス20/50(現MVP)"))
# 3) ドンチャン20ブレイク（順張り, ロングのみ→ショートも）
hh=c.rolling(20).max().shift(1); ll=c.rolling(20).min().shift(1)
sig=pd.Series(0,index=d.index); sig[c>=hh]=1; sig[c<=ll]=-1; sig=sig.replace(0,np.nan).ffill().fillna(0)
res.append(evaluate(sig, d.ret, "ドンチャン20ブレイク(順張り)"))
# 4) タイムシリーズ・モメンタム: 過去Nリターン符号
for N in [5,10,20,40]:
    mom=np.sign(c.pct_change(N))
    res.append(evaluate(mom, d.ret, f"TSモメンタム{N}日"))
# 5) 平均回帰: RSI2風（前日比zスコア逆張り）
z=(c-c.rolling(10).mean())/c.rolling(10).std()
mr=pd.Series(0,index=d.index); mr[z<-1]=1; mr[z>1]=-1
res.append(evaluate(mr, d.ret, "平均回帰(zスコア±1逆張り)"))
# 6) ボラ・ブレイク: 当日が直近ATRの1.0倍超ブレイクで翌日方向継続
res.append(evaluate(np.where(d.ret>0,1,-1)*0, d.ret, "（予約）"))

pd.DataFrame(res).to_csv("/home/user/toto/gold-ea/backtest/strategy_screen.csv",index=False)

# 保存
with open("/home/user/toto/gold-ea/backtest/analysis_report.txt","w") as f:
    f.write("\n".join(out))
hr.to_csv("/home/user/toto/gold-ea/backtest/hourly_profile.csv")
print("\n[saved] analysis_report.txt / hourly_profile.csv / strategy_screen.csv")
