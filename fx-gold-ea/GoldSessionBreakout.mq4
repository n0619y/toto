//+------------------------------------------------------------------+
//|                                          GoldSessionBreakout.mq4 |
//|  XAUUSD 短期セッションブレイクアウトEA (M5/M15チャート用)         |
//|                                                                  |
//|  戦略 (backtest/gold_session_breakout.py で検証済み):            |
//|   - アジア〜ロンドン時間 [RangeStart, RangeEnd) のレンジを計測    |
//|   - NY時間にレンジ±バッファのストップ注文でブレイクを捕捉        |
//|   - H4 EMA50/200と同方向のブレイクのみ (トレンド整合フィルター)   |
//|   - SL=レンジ反対側 / TP=リスクのR倍 / EOD強制手仕舞い            |
//|   - 1日1トレード。オーバーナイトなし                              |
//|                                                                  |
//|  防御: リスク%ロット / 日次損失停止 / 最大DD完全停止 /            |
//|        スプレッドフィルター (GoldTrendRiderと同一思想)            |
//+------------------------------------------------------------------+
#property copyright "toto project"
#property version   "1.00"
#property strict

//=== セッション時刻 (サーバー時間) ===
input int    RangeStartHour    = 1;         // レンジ計測開始時
input int    RangeEndHour      = 15;        // レンジ計測終了時 = 注文設置開始
input int    TradeEndHour      = 20;        // 未約定注文の取消時刻
input int    EodExitHour       = 23;        // 全ポジション強制手仕舞い時刻

//=== エントリー・手仕舞い ===
input double BufferFrac        = 0.10;      // ブレイクバッファ = レンジ幅 x この割合
input bool   SlAtRangeMid      = false;     // true=SLをレンジ中央に (falseでレンジ反対側)
input double TpRMultiple       = 3.0;       // TP = リスクのR倍 (0で時間手仕舞いのみ)
input bool   UseH4TrendFilter  = true;      // H4 EMA50/200と同方向のみエントリー
input int    TrendFastEma      = 50;        // H4短期EMA
input int    TrendSlowEma      = 200;       // H4長期EMA
input bool   LongOnly          = false;     // 買い専用
input double MinSlDistance     = 0.5;       // 最小SL幅(ドル)。狭すぎる日はコスト負けするため見送り
input double MinRangePct       = 0.0;       // レンジ幅下限 (価格比%, 0で無効)
input double MaxRangePct       = 0.0;       // レンジ幅上限 (価格比%, 0で無効)

//=== 資金管理・防御 ===
input double RiskPercent       = 1.5;       // 1トレードのリスク (口座残高%)
input double MaxDailyLossPct   = 5.0;       // 日次損失上限%
input double MaxDrawdownPct    = 30.0;      // 最大DD% (到達で完全停止)
input int    MaxSpreadPoints   = 60;        // 許容最大スプレッド(ポイント)
input int    SlippagePoints    = 30;        // 許容スリッページ(ポイント)
input int    MagicNumber       = 20260704;  // マジックナンバー (GoldTrendRiderと変えること)
input string TradeComment      = "GoldSessionBO";

//=== 内部状態 ===
datetime g_currentDay      = 0;
double   g_dayStartBalance = 0.0;
double   g_peakEquity      = 0.0;
bool     g_haltedForDay    = false;
bool     g_haltedMaxDD     = false;
bool     g_placedToday     = false;   // 本日ペンディング設置済み
bool     g_firedToday      = false;   // 本日約定済み (1日1トレード制御)

//+------------------------------------------------------------------+
int OnInit()
{
   string sym = Symbol();
   if(StringFind(sym, "XAU") < 0 && StringFind(sym, "GOLD") < 0)
      Print("警告: このEAはXAUUSD(ゴールド)向けです。現在: ", sym);
   if(Period() > PERIOD_M15)
      Print("警告: M5またはM15チャートでの使用を推奨します (現在: M", Period(), ")");

   g_currentDay      = 0;
   g_dayStartBalance = AccountBalance();
   g_peakEquity      = AccountEquity();
   g_haltedForDay    = false;
   g_haltedMaxDD     = false;
   g_placedToday     = false;
   g_firedToday      = HasTradedToday();  // 再起動時に本日の約定履歴を復元
   Print("GoldSessionBreakout 起動: リスク", DoubleToString(RiskPercent,1),
         "%, レンジ", RangeStartHour, "-", RangeEndHour, "時, 取引〜", TradeEndHour,
         "時, 手仕舞い", EodExitHour, "時");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnTick()
{
   UpdateDayTracking();

   double eq = AccountEquity();
   if(eq > g_peakEquity) g_peakEquity = eq;

   // --- 最大DD完全停止 ---
   if(g_haltedMaxDD)
      return;
   if(g_peakEquity > 0 && (g_peakEquity - eq) / g_peakEquity * 100.0 >= MaxDrawdownPct)
   {
      g_haltedMaxDD = true;
      Print("最大DD到達。全決済し完全停止します。");
      CloseAllAndDeletePendings("最大DD停止");
      return;
   }

   // --- 日次損失上限 ---
   if(!g_haltedForDay && g_dayStartBalance > 0 &&
      (g_dayStartBalance - eq) / g_dayStartBalance * 100.0 >= MaxDailyLossPct)
   {
      g_haltedForDay = true;
      Print("日次損失上限到達。本日の取引を停止します。");
      CloseAllAndDeletePendings("日次損失上限");
   }

   int hr = TimeHour(TimeCurrent());

   // --- 約定検出 -> OCO: 反対側のペンディングを削除 ---
   if(CountPositions() > 0)
   {
      if(!g_firedToday)
      {
         g_firedToday = true;
         Print("ブレイク約定を検出。反対側の注文を取り消します。");
      }
      DeletePendings();
   }

   // --- EOD強制手仕舞い ---
   if(hr >= EodExitHour || hr < RangeStartHour)
   {
      CloseAllAndDeletePendings("時間手仕舞い");
      return;
   }

   // --- 未約定注文の期限切れ取消 ---
   if(hr >= TradeEndHour)
   {
      DeletePendings();
      return;
   }

   if(g_haltedForDay || g_firedToday || g_placedToday)
      return;

   // --- レンジ確定後にペンディング設置 ---
   if(hr >= RangeEndHour)
      PlaceBreakoutOrders();
}

//+------------------------------------------------------------------+
void UpdateDayTracking()
{
   datetime day = iTime(NULL, PERIOD_D1, 0);
   if(day != g_currentDay)
   {
      g_currentDay      = day;
      g_dayStartBalance = AccountBalance();
      g_haltedForDay    = false;
      g_placedToday     = false;
      g_firedToday      = false;
   }
}

//+------------------------------------------------------------------+
//| 本日のレンジを確定足から計算                                      |
//+------------------------------------------------------------------+
bool ComputeTodayRange(double &hi, double &lo)
{
   datetime dayStart = iTime(NULL, PERIOD_D1, 0);
   hi = -1; lo = -1;
   for(int i = 1; i < Bars; i++)
   {
      if(Time[i] < dayStart)
         break;
      int h = TimeHour(Time[i]);
      if(h >= RangeStartHour && h < RangeEndHour)
      {
         if(hi < 0 || High[i] > hi) hi = High[i];
         if(lo < 0 || Low[i]  < lo) lo = Low[i];
      }
   }
   return(hi > 0 && lo > 0 && hi > lo);
}

//+------------------------------------------------------------------+
//| ブレイクアウトのストップ注文を設置                                |
//+------------------------------------------------------------------+
void PlaceBreakoutOrders()
{
   // スプレッドフィルター
   if((Ask - Bid) / Point > MaxSpreadPoints)
      return;

   double hi, lo;
   if(!ComputeTodayRange(hi, lo))
      return;

   double range = hi - lo;
   double rangePct = range / lo * 100.0;
   if(MinRangePct > 0 && rangePct < MinRangePct) { g_placedToday = true; return; }
   if(MaxRangePct > 0 && rangePct > MaxRangePct) { g_placedToday = true; return; }

   // H4トレンドフィルター (確定バーのみ)
   bool allowLong = true, allowShort = !LongOnly;
   if(UseH4TrendFilter)
   {
      double f = iMA(NULL, PERIOD_H4, TrendFastEma, 0, MODE_EMA, PRICE_CLOSE, 1);
      double s = iMA(NULL, PERIOD_H4, TrendSlowEma, 0, MODE_EMA, PRICE_CLOSE, 1);
      allowLong  = allowLong  && (f > s);
      allowShort = allowShort && (f < s);
   }

   double buf      = BufferFrac * range;
   double spread   = Ask - Bid;
   double longLvl  = NormalizeDouble(hi + buf + spread, Digits); // BUYSTOPはAsk基準
   double shortLvl = NormalizeDouble(lo - buf, Digits);
   double slBuy    = SlAtRangeMid ? (hi + lo) / 2.0 : lo;
   double slSell   = SlAtRangeMid ? (hi + lo) / 2.0 + spread : hi + spread;

   bool placedAny = false;
   if(allowLong && (longLvl - slBuy) >= MinSlDistance)
      placedAny = PlaceStopOrder(OP_BUYSTOP, longLvl, NormalizeDouble(slBuy, Digits)) || placedAny;
   if(allowShort && (slSell - shortLvl) >= MinSlDistance)
      placedAny = PlaceStopOrder(OP_SELLSTOP, shortLvl, NormalizeDouble(slSell, Digits)) || placedAny;

   // フィルターで両方向とも不許可の日も「設置試行済み」にして再試行を止める
   g_placedToday = true;
   if(placedAny)
      Print("ブレイク注文設置: レンジ ", DoubleToString(lo, Digits), " - ",
            DoubleToString(hi, Digits), " (幅", DoubleToString(range, 2), "ドル)");
}

//+------------------------------------------------------------------+
//| ストップ注文1本を設置 (市場価格がレベル超過済みなら成行)           |
//+------------------------------------------------------------------+
bool PlaceStopOrder(int type, double level, double sl)
{
   double slDist = MathAbs(level - sl);
   double lots   = CalcLots(slDist);
   if(lots <= 0)
      return(false);

   double tp = 0;
   if(TpRMultiple > 0)
      tp = NormalizeDouble((type == OP_BUYSTOP) ? level + TpRMultiple * slDist
                                                : level - TpRMultiple * slDist, Digits);

   double minStop = MarketInfo(Symbol(), MODE_STOPLEVEL) * Point;
   int ticket = -1;

   // 既にレベルを超えていたら成行でエントリー (バックテストのギャップ約定と同じ)
   if(type == OP_BUYSTOP && Ask >= level)
      ticket = OrderSend(Symbol(), OP_BUY, lots, Ask, SlippagePoints, sl, tp, TradeComment, MagicNumber, 0, clrDodgerBlue);
   else if(type == OP_SELLSTOP && Bid <= level)
      ticket = OrderSend(Symbol(), OP_SELL, lots, Bid, SlippagePoints, sl, tp, TradeComment, MagicNumber, 0, clrTomato);
   else
   {
      // ストップレベル制限チェック
      if(type == OP_BUYSTOP && level - Ask < minStop)
         return(false);
      if(type == OP_SELLSTOP && Bid - level < minStop)
         return(false);
      ticket = OrderSend(Symbol(), type, lots, level, SlippagePoints, sl, tp,
                         TradeComment, MagicNumber, 0,
                         (type == OP_BUYSTOP) ? clrDodgerBlue : clrTomato);
   }
   if(ticket < 0)
   {
      Print("注文設置失敗 type=", type, " エラー:", GetLastError());
      return(false);
   }
   return(true);
}

//+------------------------------------------------------------------+
double CalcLots(double slDistPrice)
{
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   double tickSize  = MarketInfo(Symbol(), MODE_TICKSIZE);
   double minLot    = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot    = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep   = MarketInfo(Symbol(), MODE_LOTSTEP);
   if(tickValue <= 0 || tickSize <= 0 || slDistPrice <= 0 || lotStep <= 0)
      return(0);

   double riskMoney  = AccountEquity() * RiskPercent / 100.0;
   double lossPerLot = slDistPrice / tickSize * tickValue;
   if(lossPerLot <= 0)
      return(0);
   double lots = MathFloor(riskMoney / lossPerLot / lotStep) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));

   double marginPerLot = MarketInfo(Symbol(), MODE_MARGINREQUIRED);
   if(marginPerLot > 0)
   {
      double maxByMargin = MathFloor(AccountFreeMargin() * 0.9 / marginPerLot / lotStep) * lotStep;
      if(maxByMargin < minLot)
         return(0);
      lots = MathMin(lots, maxByMargin);
   }
   return(NormalizeDouble(lots, 2));
}

//+------------------------------------------------------------------+
//| ユーティリティ                                                    |
//+------------------------------------------------------------------+
int CountPositions()
{
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      if(OrderType() == OP_BUY || OrderType() == OP_SELL) n++;
   }
   return(n);
}

bool HasTradedToday()
{
   datetime dayStart = iTime(NULL, PERIOD_D1, 0);
   if(CountPositions() > 0)
      return(true);
   for(int i = OrdersHistoryTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      if(OrderOpenTime() >= dayStart)
         return(true);
   }
   return(false);
}

void DeletePendings()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      if(OrderType() == OP_BUYSTOP || OrderType() == OP_SELLSTOP ||
         OrderType() == OP_BUYLIMIT || OrderType() == OP_SELLLIMIT)
      {
         if(!OrderDelete(OrderTicket()))
            Print("注文取消失敗 エラー:", GetLastError());
      }
   }
}

void CloseAllAndDeletePendings(string reason)
{
   DeletePendings();
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      int ticket = OrderTicket();
      for(int attempt = 0; attempt < 3; attempt++)
      {
         RefreshRates();
         double px = (OrderType() == OP_BUY) ? Bid : Ask;
         if(OrderClose(ticket, OrderLots(), px, SlippagePoints, clrGray))
         {
            Print("決済 (", reason, ") チケット:", ticket);
            break;
         }
         Print("決済失敗 (試行", attempt + 1, "/3) エラー:", GetLastError());
         Sleep(500);
      }
   }
}
//+------------------------------------------------------------------+
