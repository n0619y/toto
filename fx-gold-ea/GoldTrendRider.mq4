//+------------------------------------------------------------------+
//|                                               GoldTrendRider.mq4 |
//|  XAUUSD トレンドフォローEA                                        |
//|                                                                  |
//|  戦略概要:                                                       |
//|   - EMA(速/遅)でトレンド方向を判定                                |
//|   - ドンチャンチャネル・ブレイクアウトでエントリー                |
//|   - ADXフィルターでレンジ相場を除外(任意)                         |
//|   - ATRベースの初期ストップ + シャンデリア・トレーリング          |
//|   - トレンド継続中はピラミッディング(増し玉)で利を伸ばす          |
//|   - 口座資金に対する%リスクで自動ロット計算                       |
//|                                                                  |
//|  防御機構:                                                       |
//|   - スプレッドフィルター                                          |
//|   - 日次損失上限(その日の取引を停止)                              |
//|   - 最大ドローダウン到達で全決済+完全停止                         |
//+------------------------------------------------------------------+
#property copyright "toto project"
#property version   "1.20"
#property strict

//=== エントリーロジック ===
input int    EmaFastPeriod     = 50;        // 短期EMA期間(トレンド判定)
input int    EmaSlowPeriod     = 200;       // 長期EMA期間(トレンド判定)
input int    DonchianPeriod    = 20;        // ドンチャンチャネル期間(ブレイク判定)
input bool   UseAdxFilter      = true;      // ADXフィルターを使う
input int    AdxPeriod         = 14;        // ADX期間
input double AdxThreshold      = 20.0;      // ADXしきい値(これ未満はレンジとみなし見送り)

//=== v1.2 追加フィルター ===
input bool   UseAtrExpansion   = false;     // ATR拡大フィルター(ボラ立ち上がり時のみエントリー) H4検証で採用
input int    AtrExpFastPeriod  = 14;        // 短期ATR期間
input int    AtrExpSlowPeriod  = 100;       // 長期ATR期間
input double AtrExpRatio       = 0.95;      // 短期ATR > 長期ATR x この比率 でエントリー許可
input bool   UseMtfFilter      = false;     // D1トレンド整合フィルター(検証では効果薄、オプション)
input int    MtfFastPeriod     = 50;        // D1短期EMA
input int    MtfSlowPeriod     = 200;       // D1長期EMA
input bool   UseBreakeven      = false;     // ブレイクイーブン移動(検証では利益低下、オプション)
input double BeTriggerAtr      = 1.0;       // 建値移動の発動幅 = ATR x この倍率

//=== 損切り・利食い ===
input int    AtrPeriod         = 14;        // ATR期間
input double SlAtrMult         = 2.0;       // 初期ストップ幅 = ATR x この倍率
input double TrailAtrMult      = 3.0;       // トレーリング幅 = ATR x この倍率(シャンデリア)
input int    TrailLookback     = 22;        // トレーリング基準の高値/安値参照バー数
input bool   UseTakeProfit     = false;     // 固定TPを使う(falseならトレールで伸ばす)
input double TpAtrMult         = 6.0;       // TP幅 = ATR x この倍率

//=== 資金管理(攻め設定) ===
input bool   LongOnly          = false;     // 買い専用モード(実データ検証で売りは全時間足マイナスだった)
input double RiskPercent       = 3.0;       // 1エントリーあたりのリスク(口座残高%)
input int    MaxPyramids       = 3;         // 同方向の最大ポジション数(増し玉含む)
input double PyramidSpacingATR = 1.0;       // 増し玉の間隔 = ATR x この倍率
input double MaxDailyLossPct   = 8.0;       // 日次損失上限% (到達でその日は停止)
input double MaxDrawdownPct    = 35.0;      // 最大DD% (到達で全決済+完全停止)

//=== 執行・フィルター ===
input int    MaxSpreadPoints   = 60;        // 許容最大スプレッド(ポイント)
input int    SlippagePoints    = 30;        // 許容スリッページ(ポイント)
input bool   UseSessionFilter  = true;      // 時間帯フィルターを使う
input int    SessionStartHour  = 7;         // 取引開始時刻(サーバー時間)
input int    SessionEndHour    = 21;        // 取引終了時刻(サーバー時間)
input int    MagicNumber       = 20260703;  // マジックナンバー
input string TradeComment      = "GoldTrendRider";

//=== 内部状態 ===
datetime g_lastBarTime      = 0;     // 新バー検出用
datetime g_currentDay       = 0;     // 日付変化検出用
double   g_dayStartBalance  = 0.0;   // その日の開始残高
double   g_peakEquity       = 0.0;   // 資金曲線のピーク(DD計算用)
bool     g_haltedForDay     = false; // 日次損失上限による停止
bool     g_haltedMaxDD      = false; // 最大DDによる完全停止

//+------------------------------------------------------------------+
int OnInit()
{
   string sym = Symbol();
   if(StringFind(sym, "XAU") < 0 && StringFind(sym, "GOLD") < 0)
      Print("警告: このEAはXAUUSD(ゴールド)向けに設計されています。現在のシンボル: ", sym);

   g_lastBarTime     = 0;
   g_currentDay      = 0;
   g_dayStartBalance = AccountBalance();
   g_peakEquity      = AccountEquity();
   g_haltedForDay    = false;
   g_haltedMaxDD     = false;

   Print("GoldTrendRider 起動: リスク", DoubleToString(RiskPercent,1),
         "%/トレード, 最大ピラミッド", MaxPyramids, ", 日次損失上限",
         DoubleToString(MaxDailyLossPct,1), "%, 最大DD", DoubleToString(MaxDrawdownPct,1), "%");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnTick()
{
   UpdateDayTracking();
   UpdateEquityPeak();

   // 最大DD停止: 全決済して以後何もしない(手動での再起動が必要)
   if(g_haltedMaxDD)
      return;
   if(CheckMaxDrawdown())
      return;

   // トレーリングは毎ティック更新(保有中の防御は止めない)
   ManageTrailingStops();

   // 日次損失上限チェック
   if(!g_haltedForDay && CheckDailyLoss())
      g_haltedForDay = true;
   if(g_haltedForDay)
      return;

   // エントリー判定は新バー確定時のみ(ノイズ回避)
   if(!IsNewBar())
      return;
   if(UseSessionFilter && !InSession())
      return;
   if(!SpreadOk())
      return;

   CheckSignalsAndTrade();
}

//+------------------------------------------------------------------+
//| 新バー検出                                                        |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime t = Time[0];
   if(t == g_lastBarTime)
      return(false);
   g_lastBarTime = t;
   return(true);
}

//+------------------------------------------------------------------+
//| 日付変化の追跡(日次損失リセット)                                  |
//+------------------------------------------------------------------+
void UpdateDayTracking()
{
   datetime day = iTime(NULL, PERIOD_D1, 0);
   if(day != g_currentDay)
   {
      g_currentDay      = day;
      g_dayStartBalance = AccountBalance();
      if(g_haltedForDay)
         Print("新しい取引日: 日次停止を解除します");
      g_haltedForDay = false;
   }
}

void UpdateEquityPeak()
{
   double eq = AccountEquity();
   if(eq > g_peakEquity)
      g_peakEquity = eq;
}

//+------------------------------------------------------------------+
//| 日次損失上限: 当日開始残高からの含み込み損失をチェック            |
//+------------------------------------------------------------------+
bool CheckDailyLoss()
{
   if(g_dayStartBalance <= 0)
      return(false);
   double lossPct = (g_dayStartBalance - AccountEquity()) / g_dayStartBalance * 100.0;
   if(lossPct >= MaxDailyLossPct)
   {
      Print("日次損失上限に到達 (", DoubleToString(lossPct,2), "%)。全決済し本日の取引を停止します。");
      CloseAllPositions("日次損失上限");
      return(true);
   }
   return(false);
}

//+------------------------------------------------------------------+
//| 最大ドローダウン: ピーク資金からの下落率をチェック                |
//+------------------------------------------------------------------+
bool CheckMaxDrawdown()
{
   if(g_peakEquity <= 0)
      return(false);
   double ddPct = (g_peakEquity - AccountEquity()) / g_peakEquity * 100.0;
   if(ddPct >= MaxDrawdownPct)
   {
      g_haltedMaxDD = true;
      Print("最大ドローダウンに到達 (", DoubleToString(ddPct,2),
            "%)。全決済しEAを完全停止します。再開するにはEAを再アタッチしてください。");
      CloseAllPositions("最大DD停止");
      return(true);
   }
   return(false);
}

//+------------------------------------------------------------------+
//| 時間帯フィルター(サーバー時間)                                    |
//+------------------------------------------------------------------+
bool InSession()
{
   int h = TimeHour(TimeCurrent());
   if(SessionStartHour <= SessionEndHour)
      return(h >= SessionStartHour && h < SessionEndHour);
   // 日をまたぐ設定(例: 22時〜5時)にも対応
   return(h >= SessionStartHour || h < SessionEndHour);
}

bool SpreadOk()
{
   double spreadPts = (Ask - Bid) / Point;
   if(spreadPts > MaxSpreadPoints)
   {
      Print("スプレッド過大のためスキップ: ", DoubleToString(spreadPts,0), "pt");
      return(false);
   }
   return(true);
}

//+------------------------------------------------------------------+
//| シグナル判定とエントリー                                          |
//+------------------------------------------------------------------+
void CheckSignalsAndTrade()
{
   double emaFast = iMA(NULL, 0, EmaFastPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double emaSlow = iMA(NULL, 0, EmaSlowPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double atr     = iATR(NULL, 0, AtrPeriod, 1);
   if(atr <= 0)
      return;

   bool adxOk = true;
   if(UseAdxFilter)
      adxOk = (iADX(NULL, 0, AdxPeriod, PRICE_CLOSE, MODE_MAIN, 1) >= AdxThreshold);

   // v1.2: ATR拡大フィルター(ボラティリティが立ち上がっている時だけ取引)
   bool atrExpOk = true;
   if(UseAtrExpansion)
   {
      double atrSlow = iATR(NULL, 0, AtrExpSlowPeriod, 1);
      atrExpOk = (atrSlow > 0 && iATR(NULL, 0, AtrExpFastPeriod, 1) > atrSlow * AtrExpRatio);
   }

   // v1.2: D1トレンド整合フィルター(前日までの確定日足で判定)
   bool mtfBull = true, mtfBear = true;
   if(UseMtfFilter)
   {
      double dFast = iMA(NULL, PERIOD_D1, MtfFastPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
      double dSlow = iMA(NULL, PERIOD_D1, MtfSlowPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
      mtfBull = (dFast > dSlow);
      mtfBear = (dFast < dSlow);
   }

   // 直近確定バーを除いた過去DonchianPeriod本の高値/安値
   int hiIdx = iHighest(NULL, 0, MODE_HIGH, DonchianPeriod, 2);
   int loIdx = iLowest(NULL, 0, MODE_LOW, DonchianPeriod, 2);
   if(hiIdx < 0 || loIdx < 0)
      return;
   double donchHigh = High[hiIdx];
   double donchLow  = Low[loIdx];

   bool bullTrend = (emaFast > emaSlow);
   bool bearTrend = (emaFast < emaSlow);
   bool buyBreak  = (Close[1] > donchHigh);
   bool sellBreak = (Close[1] < donchLow);

   int buys  = CountOrders(OP_BUY);
   int sells = CountOrders(OP_SELL);

   //--- ドテン: 逆方向のブレイクが出たら既存を閉じる
   if(bearTrend && sellBreak && buys > 0)
      CloseDirection(OP_BUY, "逆方向ブレイク");
   if(bullTrend && buyBreak && sells > 0)
      CloseDirection(OP_SELL, "逆方向ブレイク");

   buys  = CountOrders(OP_BUY);
   sells = CountOrders(OP_SELL);

   //--- 買い: 上昇トレンド + 上抜けブレイク
   if(bullTrend && adxOk && atrExpOk && mtfBull && sells == 0)
   {
      if(buys == 0 && buyBreak)
         OpenPosition(OP_BUY, atr);
      else if(buys > 0 && buys < MaxPyramids)
      {
         // ピラミッディング: 最後のエントリーからATR x 間隔ぶん順行したら増し玉
         double lastEntry = LastEntryPrice(OP_BUY);
         if(lastEntry > 0 && Close[1] >= lastEntry + PyramidSpacingATR * atr)
            OpenPosition(OP_BUY, atr);
      }
   }

   //--- 売り: 下降トレンド + 下抜けブレイク (LongOnly時は新規売りなし。買いの決済は上のドテン処理で行う)
   if(bearTrend && adxOk && atrExpOk && mtfBear && buys == 0 && !LongOnly)
   {
      if(sells == 0 && sellBreak)
         OpenPosition(OP_SELL, atr);
      else if(sells > 0 && sells < MaxPyramids)
      {
         double lastEntry = LastEntryPrice(OP_SELL);
         if(lastEntry > 0 && Close[1] <= lastEntry - PyramidSpacingATR * atr)
            OpenPosition(OP_SELL, atr);
      }
   }
}

//+------------------------------------------------------------------+
//| ポジションを開く(リスク%からロット自動計算)                       |
//+------------------------------------------------------------------+
void OpenPosition(int type, double atr)
{
   RefreshRates();
   double price, sl, tp = 0;
   double slDist = SlAtrMult * atr;

   if(type == OP_BUY)
   {
      price = Ask;
      sl    = price - slDist;
      if(UseTakeProfit) tp = price + TpAtrMult * atr;
   }
   else
   {
      price = Bid;
      sl    = price + slDist;
      if(UseTakeProfit) tp = price - TpAtrMult * atr;
   }

   double lots = CalcLots(slDist);
   if(lots <= 0)
   {
      Print("ロット計算結果が0のためエントリー見送り");
      return;
   }

   price = NormalizeDouble(price, Digits);
   sl    = NormalizeDouble(sl,    Digits);
   tp    = NormalizeDouble(tp,    Digits);

   int ticket = -1;
   for(int attempt = 0; attempt < 3 && ticket < 0; attempt++)
   {
      RefreshRates();
      price  = (type == OP_BUY) ? Ask : Bid;
      ticket = OrderSend(Symbol(), type, lots, price, SlippagePoints,
                         sl, tp, TradeComment, MagicNumber, 0,
                         (type == OP_BUY) ? clrDodgerBlue : clrTomato);
      if(ticket < 0)
      {
         int err = GetLastError();
         Print("OrderSend失敗 (試行", attempt + 1, "/3) エラー:", err);
         // ECN口座など SL/TP同時指定不可(130)の場合は建ててから修正
         if(err == 130 || err == 3)
         {
            RefreshRates();
            price  = (type == OP_BUY) ? Ask : Bid;
            ticket = OrderSend(Symbol(), type, lots, price, SlippagePoints,
                               0, 0, TradeComment, MagicNumber, 0);
            if(ticket >= 0 && OrderSelect(ticket, SELECT_BY_TICKET))
            {
               if(!OrderModify(ticket, OrderOpenPrice(), sl, tp, 0))
                  Print("SL/TP設定失敗 エラー:", GetLastError(), " チケット:", ticket);
            }
         }
         Sleep(500);
      }
   }

   if(ticket >= 0)
      Print((type == OP_BUY ? "買い" : "売り"), "エントリー: ", DoubleToString(lots,2),
            "ロット @", DoubleToString(price, Digits), " SL:", DoubleToString(sl, Digits));
   else
      Print("エントリー失敗(リトライ上限)");
}

//+------------------------------------------------------------------+
//| リスク%ベースのロット計算                                         |
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
   double lossPerLot = slDistPrice / tickSize * tickValue; // 1ロットあたりのSL到達時損失
   if(lossPerLot <= 0)
      return(0);

   double lots = riskMoney / lossPerLot;
   lots = MathFloor(lots / lotStep) * lotStep;      // ロットステップに丸め(切り捨て)
   lots = MathMax(minLot, MathMin(maxLot, lots));

   // 証拠金不足チェック
   double marginPerLot = MarketInfo(Symbol(), MODE_MARGINREQUIRED);
   if(marginPerLot > 0)
   {
      double freeMargin = AccountFreeMargin();
      double maxByMargin = MathFloor(freeMargin * 0.9 / marginPerLot / lotStep) * lotStep;
      if(maxByMargin < minLot)
      {
         Print("証拠金不足: 必要", DoubleToString(marginPerLot * minLot, 0),
               " 利用可能", DoubleToString(freeMargin, 0));
         return(0);
      }
      lots = MathMin(lots, maxByMargin);
   }
   return(NormalizeDouble(lots, 2));
}

//+------------------------------------------------------------------+
//| シャンデリア・トレーリングストップ                                |
//| 買い: 直近N本高値 - ATR x 倍率 / 売り: 直近N本安値 + ATR x 倍率   |
//+------------------------------------------------------------------+
void ManageTrailingStops()
{
   double atr = iATR(NULL, 0, AtrPeriod, 1);
   if(atr <= 0)
      return;

   int hiIdx = iHighest(NULL, 0, MODE_HIGH, TrailLookback, 1);
   int loIdx = iLowest(NULL, 0, MODE_LOW, TrailLookback, 1);
   if(hiIdx < 0 || loIdx < 0)
      return;

   double buyTrail  = NormalizeDouble(High[hiIdx] - TrailAtrMult * atr, Digits);
   double sellTrail = NormalizeDouble(Low[loIdx]  + TrailAtrMult * atr, Digits);
   double minStopDist = MarketInfo(Symbol(), MODE_STOPLEVEL) * Point;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber)
         continue;

      if(OrderType() == OP_BUY)
      {
         double newSL = buyTrail;
         // v1.2: ブレイクイーブン — 発動幅以上の含み益で建値をSLの下限にする
         if(UseBreakeven && Bid >= OrderOpenPrice() + BeTriggerAtr * atr)
            newSL = MathMax(newSL, OrderOpenPrice());
         newSL = NormalizeDouble(newSL, Digits);
         // SLは上方向にのみ更新。ストップレベル制限も考慮
         if(newSL > OrderStopLoss() + Point && newSL < Bid - minStopDist)
         {
            if(!OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0))
               Print("トレール更新失敗(買い) エラー:", GetLastError());
         }
      }
      else if(OrderType() == OP_SELL)
      {
         double newSL = sellTrail;
         if(UseBreakeven && Ask <= OrderOpenPrice() - BeTriggerAtr * atr)
            newSL = MathMin(newSL, OrderOpenPrice());
         newSL = NormalizeDouble(newSL, Digits);
         if((OrderStopLoss() == 0 || newSL < OrderStopLoss() - Point) && newSL > Ask + minStopDist)
         {
            if(!OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0))
               Print("トレール更新失敗(売り) エラー:", GetLastError());
         }
      }
   }
}

//+------------------------------------------------------------------+
//| ユーティリティ                                                    |
//+------------------------------------------------------------------+
int CountOrders(int type)
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber && OrderType() == type)
         count++;
   }
   return(count);
}

double LastEntryPrice(int type)
{
   double price = 0;
   datetime latest = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber || OrderType() != type)
         continue;
      if(OrderOpenTime() > latest)
      {
         latest = OrderOpenTime();
         price  = OrderOpenPrice();
      }
   }
   return(price);
}

void CloseDirection(int type, string reason)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber || OrderType() != type)
         continue;
      ClosePosition(OrderTicket(), reason);
   }
}

void CloseAllPositions(string reason)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber)
         continue;
      if(OrderType() == OP_BUY || OrderType() == OP_SELL)
         ClosePosition(OrderTicket(), reason);
   }
}

void ClosePosition(int ticket, string reason)
{
   if(!OrderSelect(ticket, SELECT_BY_TICKET))
      return;
   for(int attempt = 0; attempt < 3; attempt++)
   {
      RefreshRates();
      double price = (OrderType() == OP_BUY) ? Bid : Ask;
      if(OrderClose(ticket, OrderLots(), price, SlippagePoints, clrGray))
      {
         Print("決済 (", reason, ") チケット:", ticket);
         return;
      }
      Print("決済失敗 (試行", attempt + 1, "/3) エラー:", GetLastError());
      Sleep(500);
   }
}
//+------------------------------------------------------------------+
