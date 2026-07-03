#!/usr/bin/env python3
"""GoldTrendRider EA (MQL4) のロジックを忠実に再現したPythonバックテスター。

EAと同じタイミングモデルで動作する:
  - シグナル判定は「確定足」のみ (EAの新バー処理と同じ)
  - ドンチャン/EMA/ATR/ADXはシフト1 (確定足基準) で計算
  - トレーリングはバー開始時点の値をバー内で適用 (EAのiHighest(shift=1)と同じ)
  - SLヒットはバー内の高安で判定、窓開けはオープン価格で約定
  - 日次損失上限・最大DD停止・セッションフィルター・スプレッドコストも再現

使い方:
  # MT4からエクスポートしたCSVで実行 (History Center -> Export)
  python3 gold_backtest.py --csv XAUUSD60.csv --preset aggressive

  # 検証用合成データで実行 (エンジン動作確認用。実際の市場成績ではない)
  python3 gold_backtest.py --synthetic --years 5 --preset aggressive

  # パラメータ感度チェック
  python3 gold_backtest.py --synthetic --years 5 --sweep
"""
import argparse
import dataclasses
import os
import sys

import numpy as np
import pandas as pd

# ============================================================
# パラメータ (EAのinputと1対1対応)
# ============================================================
@dataclasses.dataclass
class Params:
    ema_fast: int = 50
    ema_slow: int = 200
    donchian: int = 20
    use_adx: bool = True
    adx_period: int = 14
    adx_threshold: float = 20.0
    atr_period: int = 14
    sl_atr_mult: float = 2.0
    trail_atr_mult: float = 3.0
    trail_lookback: int = 22
    use_tp: bool = False
    tp_atr_mult: float = 6.0
    risk_percent: float = 3.0
    max_pyramids: int = 3
    pyramid_spacing_atr: float = 1.0
    max_daily_loss_pct: float = 8.0
    max_dd_pct: float = 35.0
    session_start: int = 7
    session_end: int = 21
    use_session: bool = True
    # 執行コスト (バックテスト固有)
    spread_usd: float = 0.35       # 平均スプレッド (XAUUSDで35ポイント=0.35ドル)
    commission_per_lot: float = 7.0  # 往復手数料 (ドル/ロット)
    stop_slippage_usd: float = 0.15  # SL約定時の平均スリッページ
    # 口座
    initial_balance: float = 10000.0
    contract_size: float = 100.0   # 1ロット=100oz -> 1ドル動くと100ドル
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01


PRESETS = {
    "aggressive": {},  # デフォルト値がそのまま攻め設定
    "conservative": dict(risk_percent=1.0, max_pyramids=1,
                         max_daily_loss_pct=4.0, max_dd_pct=20.0,
                         adx_threshold=25.0),
    # 検証結果から導いた仮説プリセット: リスクを下げてトレールを広げ、
    # 複利を長く効かせる (実データでの検証が必要)
    "balanced": dict(risk_percent=1.5, max_pyramids=2, trail_atr_mult=4.0,
                     max_daily_loss_pct=5.0, max_dd_pct=30.0),
}

# ============================================================
# インジケーター (MT4互換)
# ============================================================
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def atr_mt4(df: pd.DataFrame, n: int) -> pd.Series:
    """MT4のiATRはTrue RangeのSMA。"""
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def adx_wilder(df: pd.DataFrame, n: int) -> pd.Series:
    """Wilder方式ADX (MT4のiADXの近似。判定しきい値用途では実用上同等)。"""
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    alpha = 1.0 / n
    atr_w = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr_w
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / atr_w
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False).mean()

# ============================================================
# バックテストエンジン
# ============================================================
@dataclasses.dataclass
class Position:
    direction: int      # +1 買い / -1 売り
    lots: float
    entry: float        # 約定価格 (コスト込み)
    sl: float
    tp: float
    entry_time: pd.Timestamp

@dataclasses.dataclass
class Trade:
    direction: int
    lots: float
    entry: float
    exit: float
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    pnl: float
    reason: str

class Backtester:
    def __init__(self, df: pd.DataFrame, p: Params):
        self.df = df
        self.p = p
        self.balance = p.initial_balance
        self.positions: list[Position] = []
        self.trades: list[Trade] = []
        self.equity_curve = []          # (time, equity)
        self.peak_equity = p.initial_balance
        self.halted_dd = False
        self.halted_day = False
        self.current_day = None
        self.day_start_balance = p.initial_balance

    # ---- 損益ヘルパー ----
    def _pnl(self, pos: Position, price: float) -> float:
        return pos.direction * (price - pos.entry) * pos.lots * self.p.contract_size

    def _equity(self, price: float) -> float:
        return self.balance + sum(self._pnl(pos, price) for pos in self.positions)

    def _close(self, pos: Position, price: float, t, reason: str):
        pnl = self._pnl(pos, price) - self.p.commission_per_lot * pos.lots
        self.balance += pnl
        self.trades.append(Trade(pos.direction, pos.lots, pos.entry, price,
                                 pos.entry_time, t, pnl, reason))
        self.positions.remove(pos)

    def _close_all(self, price: float, t, reason: str):
        for pos in list(self.positions):
            self._close(pos, price, t, reason)

    def _calc_lots(self, sl_dist: float, equity: float) -> float:
        p = self.p
        risk_money = equity * p.risk_percent / 100.0
        loss_per_lot = sl_dist * p.contract_size
        if loss_per_lot <= 0:
            return 0.0
        lots = risk_money / loss_per_lot
        lots = np.floor(lots / p.lot_step) * p.lot_step
        return float(np.clip(lots, p.min_lot, p.max_lot))

    def _open(self, direction: int, price_mid: float, atr: float, t):
        p = self.p
        # 買いはAsk(=mid+スプレッド分上), 売りはBidで約定
        entry = price_mid + (p.spread_usd if direction > 0 else 0.0)
        exit_ref = price_mid if direction > 0 else price_mid + p.spread_usd
        sl_dist = p.sl_atr_mult * atr
        sl = entry - direction * sl_dist
        tp = entry + direction * p.tp_atr_mult * atr if p.use_tp else 0.0
        lots = self._calc_lots(sl_dist, self._equity(exit_ref))
        if lots <= 0:
            return
        self.positions.append(Position(direction, lots, entry, sl, tp, t))

    # ---- メインループ ----
    def run(self):
        df, p = self.df, self.p
        o = df["open"].values; h = df["high"].values
        l = df["low"].values; c = df["close"].values
        times = df.index

        ema_f = ema(df["close"], p.ema_fast).values
        ema_s = ema(df["close"], p.ema_slow).values
        atr = atr_mt4(df, p.atr_period).values
        adx = adx_wilder(df, p.adx_period).values if p.use_adx else None
        # シフト1基準のドンチャン: バーiのオープン時点 = 確定足(i-1)を除く過去N本
        dc_hi = df["high"].rolling(p.donchian).max().shift(2).values
        dc_lo = df["low"].rolling(p.donchian).min().shift(2).values
        # トレーリング基準: 直近N本(確定足まで)の高安
        tr_hi = df["high"].rolling(p.trail_lookback).max().shift(1).values
        tr_lo = df["low"].rolling(p.trail_lookback).min().shift(1).values

        warmup = max(p.ema_slow, p.donchian + 2, p.trail_lookback + 1,
                     p.atr_period + 1, p.adx_period * 3) + 5

        for i in range(warmup, len(df)):
            t = times[i]
            atr1 = atr[i - 1]
            if not np.isfinite(atr1) or atr1 <= 0:
                continue

            # --- 日付変化: 日次停止のリセット ---
            day = t.date()
            if day != self.current_day:
                self.current_day = day
                self.day_start_balance = self.balance
                self.halted_day = False

            equity_open = self._equity(o[i])
            self.peak_equity = max(self.peak_equity, equity_open)

            # --- 最大DD停止 (完全停止) ---
            if not self.halted_dd:
                dd = (self.peak_equity - equity_open) / self.peak_equity * 100
                if dd >= p.max_dd_pct:
                    self.halted_dd = True
                    self._close_all(o[i], t, "最大DD停止")
            if self.halted_dd:
                self.equity_curve.append((t, self.balance))
                continue

            # --- 日次損失上限 ---
            if not self.halted_day and self.day_start_balance > 0:
                day_loss = (self.day_start_balance - equity_open) / self.day_start_balance * 100
                if day_loss >= p.max_daily_loss_pct:
                    self.halted_day = True
                    self._close_all(o[i], t, "日次損失上限")

            # --- トレーリング更新 (バー開始時点の値、EAのshift=1と同じ) ---
            if np.isfinite(tr_hi[i]) and np.isfinite(tr_lo[i]):
                buy_trail = tr_hi[i] - p.trail_atr_mult * atr1
                sell_trail = tr_lo[i] + p.trail_atr_mult * atr1
                for pos in self.positions:
                    if pos.direction > 0 and buy_trail > pos.sl:
                        pos.sl = buy_trail
                    elif pos.direction < 0 and sell_trail < pos.sl:
                        pos.sl = sell_trail

            # --- バー内のSL/TPヒット判定 (Bid=データ価格とみなす) ---
            for pos in list(self.positions):
                if pos.direction > 0:
                    if o[i] <= pos.sl:                       # 窓開け
                        self._close(pos, o[i], t, "SL(ギャップ)")
                    elif l[i] <= pos.sl:
                        self._close(pos, pos.sl - p.stop_slippage_usd, t, "SL")
                    elif p.use_tp and pos.tp > 0 and h[i] >= pos.tp:
                        self._close(pos, pos.tp, t, "TP")
                else:
                    ask_o = o[i] + p.spread_usd
                    ask_h = h[i] + p.spread_usd
                    if ask_o >= pos.sl:
                        self._close(pos, ask_o, t, "SL(ギャップ)")
                    elif ask_h >= pos.sl:
                        self._close(pos, pos.sl + p.stop_slippage_usd, t, "SL")
                    elif p.use_tp and pos.tp > 0 and (l[i] + p.spread_usd) <= pos.tp:
                        self._close(pos, pos.tp, t, "TP")

            # --- エントリー判定 (確定足i-1のシグナル、バーiのオープンで執行) ---
            entry_allowed = not self.halted_day
            if p.use_session:
                hh = t.hour
                if p.session_start <= p.session_end:
                    entry_allowed &= (p.session_start <= hh < p.session_end)
                else:
                    entry_allowed &= (hh >= p.session_start or hh < p.session_end)

            if entry_allowed and np.isfinite(dc_hi[i]) and np.isfinite(dc_lo[i]):
                bull = ema_f[i - 1] > ema_s[i - 1]
                bear = ema_f[i - 1] < ema_s[i - 1]
                adx_ok = True if adx is None else (np.isfinite(adx[i - 1]) and adx[i - 1] >= p.adx_threshold)
                buy_break = c[i - 1] > dc_hi[i]
                sell_break = c[i - 1] < dc_lo[i]

                buys = [x for x in self.positions if x.direction > 0]
                sells = [x for x in self.positions if x.direction < 0]

                # ドテン: 逆方向ブレイクで既存を決済
                if bear and sell_break and buys:
                    for pos in list(buys):
                        self._close(pos, o[i], t, "ドテン")
                    buys = []
                if bull and buy_break and sells:
                    for pos in list(sells):
                        self._close(pos, o[i] + p.spread_usd, t, "ドテン")
                    sells = []

                if bull and adx_ok and not sells:
                    if not buys and buy_break:
                        self._open(+1, o[i], atr1, t)
                    elif buys and len(buys) < p.max_pyramids:
                        last_e = max(buys, key=lambda x: x.entry_time).entry
                        if c[i - 1] >= last_e + p.pyramid_spacing_atr * atr1:
                            self._open(+1, o[i], atr1, t)

                if bear and adx_ok and not buys:
                    if not sells and sell_break:
                        self._open(-1, o[i], atr1, t)
                    elif sells and len(sells) < p.max_pyramids:
                        last_e = max(sells, key=lambda x: x.entry_time).entry
                        if c[i - 1] <= last_e - p.pyramid_spacing_atr * atr1:
                            self._open(-1, o[i], atr1, t)

            self.equity_curve.append((t, self._equity(c[i])))

        # 終了時に全決済
        if self.positions:
            self._close_all(c[-1], times[-1], "テスト終了")
        return self

# ============================================================
# 成績集計
# ============================================================
def summarize(bt: Backtester) -> dict:
    p = bt.p
    eq = pd.Series(dict(bt.equity_curve))
    trades = bt.trades
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    peak = eq.cummax()
    dd = (peak - eq) / peak * 100
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9) if len(eq) else 0
    final = bt.balance
    daily = eq.resample("1D").last().dropna().pct_change().dropna()
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if len(daily) > 2 and daily.std() > 0 else 0.0
    return {
        "初期資金": p.initial_balance,
        "最終資金": round(final, 2),
        "純損益": round(final - p.initial_balance, 2),
        "リターン(%)": round((final / p.initial_balance - 1) * 100, 1),
        "年率リターン(CAGR%)": round(((final / p.initial_balance) ** (1 / years) - 1) * 100, 1) if years > 0 and final > 0 else float("nan"),
        "取引回数": len(trades),
        "勝率(%)": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "プロフィットファクター": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "平均利益": round(gross_win / len(wins), 2) if wins else 0,
        "平均損失": round(-gross_loss / len(losses), 2) if losses else 0,
        "最大ドローダウン(%)": round(dd.max(), 1) if len(dd) else 0,
        "シャープレシオ": round(sharpe, 2),
        "DD停止発動": bt.halted_dd,
    }

def plot_equity(bt: Backtester, path: str, title: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    eq = pd.Series(dict(bt.equity_curve))
    peak = eq.cummax()
    dd = (peak - eq) / peak * 100
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(eq.index, eq.values, lw=0.9)
    ax1.set_ylabel("Equity ($)")
    ax1.set_title(title)
    ax1.grid(alpha=0.3)
    ax2.fill_between(dd.index, dd.values, color="tomato", alpha=0.6)
    ax2.set_ylabel("Drawdown (%)")
    ax2.invert_yaxis()
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)

# ============================================================
# データ読み込み / 合成データ生成
# ============================================================
def load_csv(path: str) -> pd.DataFrame:
    """MT4 History Centerエクスポート形式または汎用OHLC CSVを読み込む。"""
    with open(path) as f:
        first = f.readline()
    if first.lower().startswith(("date", "time", "datetime")):  # ヘッダーあり汎用形式
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]
        tcol = "datetime" if "datetime" in df.columns else ("date" if "date" in df.columns else df.columns[0])
        if "date" in df.columns and "time" in df.columns and "datetime" not in df.columns:
            df["datetime"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
        else:
            df["datetime"] = pd.to_datetime(df[tcol])
        df = df.set_index("datetime")[["open", "high", "low", "close"]].astype(float)
    else:  # MT4形式: 2024.01.02,00:00,O,H,L,C,V
        df = pd.read_csv(path, header=None,
                         names=["date", "time", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["date"].str.replace(".", "-", regex=False) + " " + df["time"])
        df = df.set_index("datetime")[["open", "high", "low", "close"]].astype(float)
    return df.sort_index()

def synthetic_gold_h1(years: float = 5.0, seed: int = 42, start_price: float = 1800.0) -> pd.DataFrame:
    """検証用の合成XAUUSD H1データ。

    実際のゴールドの統計特性に合わせたレジームスイッチングモデル:
      - 年率ボラティリティ ~16% + ボラクラスタリング
      - ブル/ベア/レンジのマルコフレジーム (ゴールドの長期上昇バイアス込み)
      - 時間帯別ボラ (アジア静か、ロンドン/NY活発)
    ※エンジン動作確認用。実際の市場成績を示すものではない。
    """
    rng = np.random.default_rng(seed)
    hours_per_year = 24 * 5 * 52
    n = int(years * hours_per_year)
    ann_vol = 0.16
    base_sig = ann_vol / np.sqrt(hours_per_year)

    # レジーム: 0=ブル 1=ベア 2=レンジ (推移確率は粘着的)
    trans = np.array([[0.9990, 0.0004, 0.0006],
                      [0.0006, 0.9988, 0.0006],
                      [0.0008, 0.0004, 0.9988]])
    drift = {0: 2.5 * base_sig * 0.06, 1: -2.0 * base_sig * 0.06, 2: 0.0}
    vol_m = {0: 1.1, 1: 1.35, 2: 0.75}
    hour_vol = np.array([0.55, 0.5, 0.5, 0.55, 0.6, 0.65, 0.8, 1.0, 1.15, 1.2, 1.15, 1.1,
                         1.05, 1.3, 1.45, 1.5, 1.4, 1.25, 1.1, 0.95, 0.85, 0.75, 0.65, 0.6])

    idx = pd.date_range("2021-01-04", periods=int(n * 7 / 5) + 10, freq="1h")
    idx = idx[idx.dayofweek < 5][:n]  # 週末除外

    state = 0
    garch = 1.0
    log_p = np.log(start_price)
    rows = np.empty((n, 4))
    sub = 8  # バー内サブステップでOHLC生成
    for k in range(n):
        state = rng.choice(3, p=trans[state])
        garch = 0.94 * garch + 0.06 * (1.0 + 2.5 * rng.random() ** 4)
        sig = base_sig * vol_m[state] * hour_vol[idx[k].hour] * garch
        steps = drift[state] / sub + sig / np.sqrt(sub) * rng.standard_normal(sub)
        path = log_p + np.cumsum(steps)
        o = log_p
        log_p = path[-1]
        rows[k] = (np.exp(o), np.exp(max(path.max(), o)), np.exp(min(path.min(), o)), np.exp(log_p))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)

# ============================================================
# CLI
# ============================================================
def build_params(preset: str, **overrides) -> Params:
    kw = dict(PRESETS.get(preset, {}))
    kw.update({k: v for k, v in overrides.items() if v is not None})
    return Params(**kw)

def main():
    ap = argparse.ArgumentParser(description="GoldTrendRider backtester")
    ap.add_argument("--csv", help="OHLC CSVパス (MT4エクスポート or datetime,open,high,low,close)")
    ap.add_argument("--synthetic", action="store_true", help="検証用合成データを使う")
    ap.add_argument("--years", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--preset", default="aggressive", choices=list(PRESETS))
    ap.add_argument("--risk", type=float, default=None, help="RiskPercent上書き")
    ap.add_argument("--sweep", action="store_true", help="パラメータ感度チェックを実行")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    if args.csv:
        df = load_csv(args.csv)
        src = f"実データ: {os.path.basename(args.csv)}"
    elif args.synthetic:
        df = synthetic_gold_h1(args.years, args.seed)
        src = f"合成データ ({args.years}年, seed={args.seed}) ※エンジン検証用"
    else:
        ap.error("--csv か --synthetic を指定してください")

    os.makedirs(args.outdir, exist_ok=True)
    print(f"データ: {src}\n期間: {df.index[0]} 〜 {df.index[-1]} ({len(df)}本)\n")

    if args.sweep:
        rows = []
        for dc in (15, 20, 30):
            for trail in (2.5, 3.0, 4.0):
                for risk in (1.0, 2.0, 3.0):
                    p = build_params(args.preset, risk_percent=risk)
                    p.donchian = dc
                    p.trail_atr_mult = trail
                    s = summarize(Backtester(df, p).run())
                    rows.append({"Donchian": dc, "Trail": trail, "Risk%": risk,
                                 "リターン%": s["リターン(%)"], "PF": s["プロフィットファクター"],
                                 "最大DD%": s["最大ドローダウン(%)"], "取引数": s["取引回数"],
                                 "勝率%": s["勝率(%)"], "DD停止": s["DD停止発動"]})
        table = pd.DataFrame(rows)
        print(table.to_string(index=False))
        table.to_csv(os.path.join(args.outdir, "sweep.csv"), index=False)
        return

    p = build_params(args.preset, risk_percent=args.risk)
    bt = Backtester(df, p).run()
    stats = summarize(bt)
    print(f"=== プリセット: {args.preset} ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    png = os.path.join(args.outdir, f"equity_{args.preset}.png")
    # プロットタイトルはフォント都合でASCIIのみ
    src_ascii = os.path.basename(args.csv) if args.csv else f"synthetic {args.years}y seed={args.seed} (validation only)"
    plot_equity(bt, png, f"GoldTrendRider [{args.preset}] {src_ascii}")
    pd.DataFrame([dataclasses.asdict(t) for t in bt.trades]).to_csv(
        os.path.join(args.outdir, f"trades_{args.preset}.csv"), index=False)
    print(f"\n出力: {png}, trades_{args.preset}.csv")

if __name__ == "__main__":
    main()
