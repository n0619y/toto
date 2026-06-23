#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ウォークフォワード検証: パラメータ選択が時期/レジームに依存しない(=曲線適合でない)かを確認。

単一のIS/OOS分割は『たまたまその分け方で良かった』可能性を排除できない。
ここでは expanding(アンカー)窓で:
  1. 各テスト期間の『直前まで』のデータだけでパラメータを最適化(=その時点で知り得る情報のみ)
  2. 最適パラメータを『次の未知期間』に適用して成績を記録
  3. これを期間を進めながら繰り返し、全テスト期間を縫い合わせて通算成績を出す
VBOはブレイク幅(bo)、天底はピボットk を各時点で再選択する。
合成は推奨配分 VBO60/天底40 の日次リバランス。コストはportfolio_h1と共通($0.5)。
"""
import numpy as np, pandas as pd
from portfolio_h1 import h, eq_vbo, eq_tentei, INIT

def daily_ret(eq, dates):
    return pd.Series(eq,index=dates).resample("1D").last().dropna().pct_change().dropna()

def score(eq, dates):
    """学習期間でのパラメータ選択指標 = 日次Sharpe(取引が極端に少ない設定は除外)。"""
    dr=daily_ret(eq,dates)
    if dr.std()==0 or len(dr)<30: return -9
    return dr.mean()/dr.std()*np.sqrt(252)

def seg_metrics(dr):
    if len(dr)==0: return dict(cagr=0,dd=0,sh=0,n=0)
    eq=(1+dr).cumprod()
    yrs=max((dr.index[-1]-dr.index[0]).days/365.25,1e-9)
    return dict(cagr=eq.iloc[-1]**(1/yrs)-1, dd=(eq/eq.cummax()-1).min(),
                sh=dr.mean()/dr.std()*np.sqrt(252) if dr.std()>0 else 0, n=len(dr))

BO_GRID=[12,24,48,72,120]; K_GRID=[3,4,5]
W_VBO=0.6  # 推奨配分(VBO60/天底40)

n=len(h)
test_start=int(n*0.40)            # 最初の40%は最小学習期間として確保
folds=5
edges=np.linspace(test_start, n, folds+1).astype(int)

print("="*94)
print(f"■ ウォークフォワード検証 (expanding学習→次期間で検証, {folds}分割, 合成VBO{int(W_VBO*100)}/天底{int((1-W_VBO)*100)})")
print("="*94)
print(f"  全データ {h.Date.iloc[0].date()}〜{h.Date.iloc[-1].date()}  最小学習={h.Date.iloc[test_start].date()}まで\n")

wf_dr=[]   # 全テスト期間の合成日次リターンを縫い合わせ
rows=[]
for f in range(folds):
    a,b=edges[f],edges[f+1]
    train=h.iloc[:a].reset_index(drop=True)
    test =h.iloc[a:b].reset_index(drop=True)
    td=pd.DatetimeIndex(train.Date.values.astype("datetime64[ns]"))
    ed=pd.DatetimeIndex(test.Date.values.astype("datetime64[ns]"))
    # --- 学習期間で各戦略のパラメータを選択 ---
    best_bo=max(BO_GRID,key=lambda bo:score(eq_vbo(train,bo=bo),td))
    best_k =max(K_GRID, key=lambda k :score(eq_tentei(train,k=k),td))
    # --- 未知のテスト期間に適用 ---
    e1=eq_vbo(test,bo=best_bo); e2=eq_tentei(test,k=best_k)
    d1=daily_ret(e1,ed); d2=daily_ret(e2,ed)
    j=pd.concat([d1.rename("a"),d2.rename("b")],axis=1).dropna()
    port=W_VBO*j["a"]+(1-W_VBO)*j["b"]
    m1=seg_metrics(d1); m2=seg_metrics(d2); mp=seg_metrics(port)
    wf_dr.append(port)
    print(f"  Fold{f+1} {test.Date.iloc[0].date()}〜{test.Date.iloc[-1].date()}  "
          f"[学習で選択 bo={best_bo}, k={best_k}]")
    print(f"     VBO   : CAGR{m1['cagr']*100:+6.1f}% DD{m1['dd']*100:6.1f}% Sharpe{m1['sh']:+.2f}")
    print(f"     天底  : CAGR{m2['cagr']*100:+6.1f}% DD{m2['dd']*100:6.1f}% Sharpe{m2['sh']:+.2f}")
    print(f"     合成  : CAGR{mp['cagr']*100:+6.1f}% DD{mp['dd']*100:6.1f}% Sharpe{mp['sh']:+.2f}")
    rows.append(dict(fold=f+1,bo=best_bo,k=best_k,
                     vbo_sh=m1['sh'],ten_sh=m2['sh'],port_sh=mp['sh'],
                     port_cagr=mp['cagr'],port_dd=mp['dd']))

# --- 全テスト期間を縫い合わせた通算ウォークフォワード成績 ---
allp=pd.concat(wf_dr).sort_index()
M=seg_metrics(allp)
print("\n"+"="*94); print("■ 通算ウォークフォワード成績(全テスト期間を連結)"); print("="*94)
print(f"  合成 CAGR{M['cagr']*100:+.1f}%  最大DD{M['dd']*100:.1f}%  Sharpe{M['sh']:+.2f}  日数{M['n']}")
pos=sum(1 for r in rows if r['port_sh']>0)
print(f"  ★ 黒字(Sharpe>0)フォールド: {pos}/{folds}  "
      f"(選択bo={[r['bo'] for r in rows]}, k={[r['k'] for r in rows]})")
print("  → 各期で再選択しても全期間黒字なら、特定パラメータ/時期への依存は小さい。")

pd.DataFrame(rows).to_csv("/home/user/toto/gold-ea/backtest/walkforward_results.csv",index=False)
print("\n[saved] walkforward_results.csv")
