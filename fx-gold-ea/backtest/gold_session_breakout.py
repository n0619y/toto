#!/usr/bin/env python3
"""GoldSessionBreakout (短期足EA) のバックテスター。

戦略: アジア時間のレンジを定義し、ロンドン/NY時間のブレイクアウトを取る。
  - レンジ: サーバー時間 [asia_start, asia_end) の高値/安値
  - エントリー: レンジ端 ± バッファ(レンジ幅の一定割合)のストップ注文相当
  - SL: レンジ反対側 or レンジ中央
  - TP: リスクのR倍 (0なら時間手仕舞いのみ)
  - 手仕舞い: eod_exit時にポジション強制クローズ (オーバーナイトなし)
  - 1日1トレード (最初にブレイクした方向のみ)
  - 資金管理/防御: GoldTrendRiderと同じ (リスク%、日次損失、DDブレーカー)

使い方:
  python3 gold_session_breakout.py --csv data/GOLD15.csv
  python3 gold_session_breakout.py --csv data/GOLD15.csv --sweep
"""
import argparse
import dataclasses
import os

import numpy as np
import pandas as pd

from gold_backtest import Trade, load_csv, plot_equity, summarize

@dataclasses.dataclass
class SBParams:
    """デフォルト値 = 採用構成 (IS 2023-10〜2024-12で選定、EAのinputと一致)。"""
    asia_start: int = 1        # レンジ計測開始時 (サーバー時間)
    asia_end: int = 15         # レンジ計測終了時 = エントリー解禁時 (NYブレイク版)
    trade_end: int = 20        # 新規エントリー最終時
    eod_exit: int = 23         # 全決済時刻 (オーバーナイトなし)
    buffer_frac: float = 0.10  # エントリーバッファ = レンジ幅 x この割合
    sl_mode: str = "range"     # "range"=レンジ反対側 / "half"=レンジ中央
    tp_r: float = 3.0          # TP = リスクのR倍 (0で時間手仕舞いのみ)
    long_only: bool = False
    one_per_day: bool = True   # 1日1トレード (最初のブレイクのみ)
    min_range: float = 0.0     # レンジ幅の下限 (ドル, 0で無効)
    max_range: float = 0.0     # レンジ幅の上限 (ドル, 0で無効)
    min_range_pct: float = 0.0 # レンジ幅の下限 (価格比%, 0で無効)
    max_range_pct: float = 0.0 # レンジ幅の上限 (価格比%, 0で無効)
    trend_filter: str = "h4"   # "none" / "h4": H4 EMA50/200と同方向のブレイクのみ
    # 資金管理・コスト (GoldTrendRiderと同一)
    risk_percent: float = 1.0
    max_daily_loss_pct: float = 5.0
    max_dd_pct: float = 30.0
    spread_usd: float = 0.35
    commission_per_lot: float = 7.0
    stop_slippage_usd: float = 0.15
    initial_balance: float = 10000.0
    contract_size: float = 100.0
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01

@dataclasses.dataclass
class SBPos:
    direction: int
    lots: float
    entry: float
    sl: float
    tp: float
    entry_time: pd.Timestamp

class SessionBacktester:
    """summarize()/plot_equity()と互換のインターフェースを持つ。"""
    def __init__(self, df: pd.DataFrame, p: SBParams):
        self.df = df
        self.p = p
        self.balance = p.initial_balance
        self.trades: list[Trade] = []
        self.equity_curve = []
        self.positions: list[SBPos] = []  # 常に0or1個
        self.peak_equity = p.initial_balance
        self.halted_dd = False

    def _calc_lots(self, sl_dist, equity):
        p = self.p
        loss_per_lot = sl_dist * p.contract_size
        if loss_per_lot <= 0:
            return 0.0
        lots = equity * p.risk_percent / 100.0 / loss_per_lot
        lots = np.floor(lots / p.lot_step) * p.lot_step
        return float(np.clip(lots, p.min_lot, p.max_lot))

    def _close(self, pos, price, t, reason):
        pnl = pos.direction * (price - pos.entry) * pos.lots * self.p.contract_size \
              - self.p.commission_per_lot * pos.lots
        self.balance += pnl
        self.trades.append(Trade(pos.direction, pos.lots, pos.entry, price,
                                 pos.entry_time, t, pnl, reason))
        self.positions.remove(pos)

    def run(self):
        p = self.p
        df = self.df
        o = df["open"].values; h = df["high"].values
        l = df["low"].values; c = df["close"].values
        times = df.index
        hours = df.index.hour.values
        dates = df.index.date

        # H4トレンドフィルター: M15をH4に集約しEMA50/200を計算、確定H4バーのみ使用
        if p.trend_filter == "h4":
            h4 = df["close"].resample("4h").last().dropna()
            f_ema = h4.ewm(span=50, adjust=False).mean()
            s_ema = h4.ewm(span=200, adjust=False).mean()
            bull_h4 = (f_ema > s_ema).shift(1)
            bear_h4 = (f_ema < s_ema).shift(1)
            # 各M15バーに対し直近の確定H4バーの値を割当 (ルックアヘッド防止)
            tf_bull = bull_h4.reindex(df.index, method="ffill").fillna(False).values
            tf_bear = bear_h4.reindex(df.index, method="ffill").fillna(False).values
        else:
            tf_bull = np.ones(len(df), dtype=bool)
            tf_bear = np.ones(len(df), dtype=bool)

        cur_day = None
        rng_hi = rng_lo = np.nan
        fired = False           # 本日エントリー済み
        halted_day = False
        day_start_balance = self.balance

        for i in range(len(df)):
            t = times[i]
            if dates[i] != cur_day:
                cur_day = dates[i]
                rng_hi = rng_lo = np.nan
                fired = False
                halted_day = False
                day_start_balance = self.balance

            pos = self.positions[0] if self.positions else None
            equity = self.balance + (pos.direction * (o[i] - pos.entry) * pos.lots * p.contract_size if pos else 0.0)
            self.peak_equity = max(self.peak_equity, equity)

            # --- DDブレーカー ---
            if not self.halted_dd and (self.peak_equity - equity) / self.peak_equity * 100 >= p.max_dd_pct:
                self.halted_dd = True
                if pos:
                    self._close(pos, o[i], t, "最大DD停止")
                    pos = None
            if self.halted_dd:
                self.equity_curve.append((t, self.balance))
                continue

            # --- 日次損失上限 ---
            if not halted_day and day_start_balance > 0 and \
               (day_start_balance - equity) / day_start_balance * 100 >= p.max_daily_loss_pct:
                halted_day = True
                if pos:
                    self._close(pos, o[i], t, "日次損失上限")
                    pos = None

            hr = hours[i]

            # --- アジアレンジ構築 ---
            if p.asia_start <= hr < p.asia_end:
                rng_hi = h[i] if np.isnan(rng_hi) else max(rng_hi, h[i])
                rng_lo = l[i] if np.isnan(rng_lo) else min(rng_lo, l[i])

            # --- ポジション管理 (SL優先 -> TP -> 時間手仕舞い) ---
            if pos:
                if pos.direction > 0:
                    if o[i] <= pos.sl:
                        self._close(pos, o[i], t, "SL(ギャップ)"); pos = None
                    elif l[i] <= pos.sl:
                        self._close(pos, pos.sl - p.stop_slippage_usd, t, "SL"); pos = None
                    elif pos.tp > 0 and h[i] >= pos.tp:
                        self._close(pos, pos.tp, t, "TP"); pos = None
                else:
                    ask_h = h[i] + p.spread_usd
                    if o[i] + p.spread_usd >= pos.sl:
                        self._close(pos, o[i] + p.spread_usd, t, "SL(ギャップ)"); pos = None
                    elif ask_h >= pos.sl:
                        self._close(pos, pos.sl + p.stop_slippage_usd, t, "SL"); pos = None
                    elif pos.tp > 0 and (l[i] + p.spread_usd) <= pos.tp:
                        self._close(pos, pos.tp, t, "TP"); pos = None
                if pos and hr >= p.eod_exit:
                    px = o[i] if pos.direction > 0 else o[i] + p.spread_usd
                    self._close(pos, px, t, "時間手仕舞い"); pos = None

            # --- エントリー判定 ---
            can_enter = (pos is None and not halted_day and not fired
                         and p.asia_end <= hr < p.trade_end
                         and np.isfinite(rng_hi) and np.isfinite(rng_lo))
            if can_enter:
                rng = rng_hi - rng_lo
                rng_pct = rng / rng_lo * 100 if rng_lo > 0 else 0.0
                range_ok = rng > 0 \
                    and (p.min_range <= 0 or rng >= p.min_range) \
                    and (p.max_range <= 0 or rng <= p.max_range) \
                    and (p.min_range_pct <= 0 or rng_pct >= p.min_range_pct) \
                    and (p.max_range_pct <= 0 or rng_pct <= p.max_range_pct)
                if range_ok:
                    buf = p.buffer_frac * rng
                    long_lvl = rng_hi + buf
                    short_lvl = rng_lo - buf
                    hit_long = h[i] >= long_lvl and tf_bull[i]
                    hit_short = (l[i] <= short_lvl) and not p.long_only and tf_bear[i]
                    if hit_long and hit_short:
                        fired = True  # 同一バーで両方向 -> 方向不明なので見送り
                    elif hit_long or hit_short:
                        direction = 1 if hit_long else -1
                        # 始値が既にレベルを超えていたら始値で約定 (ギャップ)
                        if direction > 0:
                            fill = max(long_lvl, o[i]) + p.spread_usd
                            sl = rng_lo if p.sl_mode == "range" else (rng_hi + rng_lo) / 2
                        else:
                            fill = min(short_lvl, o[i])
                            sl = (rng_hi + p.spread_usd) if p.sl_mode == "range" \
                                 else (rng_hi + rng_lo) / 2 + p.spread_usd
                        sl_dist = abs(fill - sl)
                        if sl_dist > 0.5:  # SL幅が狭すぎる日はスキップ (コスト負け防止)
                            lots = self._calc_lots(sl_dist, equity)
                            if lots > 0:
                                tp = fill + direction * p.tp_r * sl_dist if p.tp_r > 0 else 0.0
                                self.positions.append(SBPos(direction, lots, fill, sl, tp, t))
                        fired = True if p.one_per_day else fired

            self.equity_curve.append((t, self.balance if not self.positions else
                                      self.balance + self.positions[0].direction *
                                      (c[i] - self.positions[0].entry) *
                                      self.positions[0].lots * p.contract_size))

        if self.positions:
            self._close(self.positions[0], c[-1], times[-1], "テスト終了")
        return self

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--risk", type=float, default=None)
    ap.add_argument("--tag", default="sb")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    df = load_csv(args.csv)
    if args.start: df = df[df.index >= pd.Timestamp(args.start)]
    if args.end: df = df[df.index < pd.Timestamp(args.end)]
    os.makedirs(args.outdir, exist_ok=True)
    print(f"期間: {df.index[0]} 〜 {df.index[-1]} ({len(df)}本)\n")

    if args.sweep:
        rows = []
        for buf in (0.0, 0.1, 0.2):
            for slm in ("range", "half"):
                for tpr in (1.5, 2.0, 3.0, 0.0):
                    for lo in (False, True):
                        p = SBParams(buffer_frac=buf, sl_mode=slm, tp_r=tpr, long_only=lo)
                        if args.risk: p.risk_percent = args.risk
                        s = summarize(SessionBacktester(df, p).run())
                        rows.append({"buf": buf, "sl": slm, "tpR": tpr,
                                     "LO": int(lo), "リターン%": s["リターン(%)"],
                                     "PF": s["プロフィットファクター"], "DD%": s["最大ドローダウン(%)"],
                                     "取引": s["取引回数"], "勝率%": s["勝率(%)"],
                                     "シャープ": s["シャープレシオ"]})
        t = pd.DataFrame(rows).sort_values("PF", ascending=False)
        print(t.to_string(index=False))
        t.to_csv(os.path.join(args.outdir, f"sweep_{args.tag}.csv"), index=False)
        return

    p = SBParams(long_only=args.long_only)
    if args.risk: p.risk_percent = args.risk
    bt = SessionBacktester(df, p).run()
    for k, v in summarize(bt).items():
        print(f"  {k}: {v}")
    plot_equity(bt, os.path.join(args.outdir, f"equity_{args.tag}.png"),
                f"GoldSessionBreakout {os.path.basename(args.csv)}")
    pd.DataFrame([dataclasses.asdict(t) for t in bt.trades]).to_csv(
        os.path.join(args.outdir, f"trades_{args.tag}.csv"), index=False)

if __name__ == "__main__":
    main()
