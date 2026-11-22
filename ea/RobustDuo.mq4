//+------------------------------------------------------------------+
//|                                                    RobustDuo.mq4 |
//|  Two uncorrelated strategies on H1 with portfolio risk control.  |
//|  A: trend-following breakout   B: range mean-reversion           |
//|  No martingale, no grid, no averaging. Every trade has a stop.   |
//|  Attach to one chart per symbol (any chart timeframe).           |
//+------------------------------------------------------------------+
#property copyright "RobustDuo"
#property version   "1.00"
#property strict
#property description "Trend breakout + mean reversion, fixed fractional risk,"
#property description "daily loss limit, max drawdown kill switch, USD exposure cap."

#define STRAT_TREND 1
#define STRAT_MR    2
#define EA_NAME     "RobustDuo"

//--- general
input string G0                  = "===== General =====";
input int    MagicBase           = 760100;   // Magic base (same value on every chart)
input bool   EnableTrend         = true;     // Strategy A: trend breakout
input bool   EnableMeanRev       = true;     // Strategy B: mean reversion

//--- risk
input string G1                  = "===== Risk =====";
input double RiskPercent         = 0.5;      // Risk per trade (% of balance)
input double MaxPortfolioRiskPct = 2.0;      // Max total open risk, all symbols (%)
input double MaxUsdRiskPct       = 1.5;      // Max open risk in one USD direction (%)
input int    MaxOpenPositions    = 6;        // Max open positions, all symbols
input double MaxDailyLossPct     = 2.0;      // Daily loss: stop new entries (%)
input double MaxDrawdownPct      = 15.0;     // Drawdown from peak: close all and halt (%)
input bool   ResetHalt           = false;    // Set true once to clear a halt, then set false
input double MaxLots             = 5.0;      // Hard cap on lot size
input double MinMarginLevelPct   = 300.0;    // Min margin level after entry (%)

//--- strategy A
input string G2                  = "===== A: Trend =====";
input int    Trend_FastEMA       = 50;       // H4 fast EMA
input int    Trend_SlowEMA       = 200;      // H4 slow EMA
input int    Trend_BreakoutBars  = 20;       // H1 breakout channel length
input double Trend_AdxMin        = 22.0;     // H1 ADX minimum
input double Trend_SL_ATR        = 2.5;      // Initial stop (ATR multiple)
input double Trend_Trail_ATR     = 3.0;      // Trailing stop (ATR multiple)

//--- strategy B
input string G3                  = "===== B: Mean reversion =====";
input int    MR_BBPeriod         = 20;       // Bollinger period
input double MR_BBDev            = 2.0;      // Bollinger deviation
input int    MR_RsiPeriod        = 14;       // RSI period
input double MR_RsiLow           = 30.0;     // RSI oversold
input double MR_RsiHigh          = 70.0;     // RSI overbought
input double MR_AdxMax           = 20.0;     // H1 ADX maximum (range regime)
input double MR_H4AdxMax         = 25.0;     // H4 ADX maximum (no strong trend)
input double MR_SL_ATR           = 1.5;      // Stop (ATR multiple)
input double MR_MinRR            = 0.6;      // Min reward/risk to middle band
input int    MR_MaxHoldBars      = 24;       // Time exit (H1 bars)
input bool   MR_UseSession       = false;    // Restrict B to a session
input int    MR_SessionStart     = 0;        // Session start hour (server)
input int    MR_SessionEnd       = 9;        // Session end hour (server)

//--- common indicators / filters
input string G4                  = "===== Filters =====";
input int    AtrPeriod           = 14;       // ATR period (H1)
input int    AdxPeriod           = 14;       // ADX period
input double VolSpikeRatio       = 2.0;      // Block entries if ATR14/ATR100 above this
input double MaxSpreadAtrRatio   = 0.15;     // Block entries if spread/ATR above this
input int    RolloverStartHour   = 23;       // No entries from this hour (server)
input int    RolloverEndHour     = 1;        // ... until this hour (server)
input bool   CloseOnFriday       = true;     // Close positions before the weekend
input int    FridayCloseHour     = 21;       // Friday close hour (server)
input string NewsTimes           = "";       // News (server time) "2026.12.04 15:30;2026.12.09 21:00"
input int    NewsBlockBeforeMin  = 30;       // Block entries before news (min)
input int    NewsBlockAfterMin   = 30;       // Block entries after news (min)

//--- execution / ops
input string G5                  = "===== Execution =====";
input int    SlippagePoints      = 30;       // Max slippage (points)
input int    MaxRetries          = 5;        // Order retries
input bool   UsePush             = true;     // Push notifications
input bool   UseAlert            = false;    // Terminal alerts
input bool   EnableCsvLog        = true;     // CSV log in MQL4/Files
input bool   ShowDashboard       = true;     // On-chart status

//--- state (everything important is re-derived from orders / global variables)
datetime g_lastBar = 0;
string   g_pfx     = "";
string   g_status  = "starting";
datetime g_news[];
int      g_tickets[];

//+------------------------------------------------------------------+
int OnInit()
  {
   if(RiskPercent <= 0 || RiskPercent > 5 || MaxDrawdownPct <= 0 || MaxDailyLossPct <= 0 ||
      Trend_SL_ATR <= 0 || Trend_Trail_ATR <= 0 || MR_SL_ATR <= 0 ||
      Trend_BreakoutBars < 2 || Trend_FastEMA >= Trend_SlowEMA || MaxRetries < 1)
     {
      Print(EA_NAME, ": invalid inputs");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_pfx = (IsTesting() ? "T_" : "") + "RD_" + IntegerToString(AccountNumber()) + "_" +
           IntegerToString(MagicBase) + "_";

   if(IsTesting())
     {
      GlobalVariableDel(g_pfx + "Day");
      GlobalVariableDel(g_pfx + "DayEq");
      GlobalVariableDel(g_pfx + "Peak");
      GlobalVariableDel(g_pfx + "Halt");
      GlobalVariableDel(g_pfx + "DayNote");
     }
   if(ResetHalt)
     {
      GlobalVariableDel(g_pfx + "Halt");
      GlobalVariableSet(g_pfx + "Peak", AccountEquity());
      Print(EA_NAME, ": halt cleared, equity peak reset. Set ResetHalt=false now.");
     }

   ParseNews();
   RebuildTickets();
   g_lastBar = 0;
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(ShowDashboard) Comment("");
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   UpdateDayAndPeak();
   SyncTickets();

   if(CheckDrawdownHalt())
     {
      g_status = "HALTED: max drawdown reached";
      Dashboard();
      return;
     }

   ManageFridayClose();

   datetime t = iTime(Symbol(), PERIOD_H1, 0);
   bool newBar = false;
   if(t != g_lastBar)
     {
      newBar = (g_lastBar != 0);
      g_lastBar = t;
     }

   if(newBar)
     {
      double atr = iATR(Symbol(), PERIOD_H1, AtrPeriod, 1);
      ManageOpen(atr);
      string why = EntryBlockReason(atr);
      if(why == "")
        {
         g_status = "running";
         if(EnableTrend)   CheckTrend(atr);
         if(EnableMeanRev) CheckMeanRev(atr);
        }
      else
         g_status = "no entry: " + why;
     }
   Dashboard();
  }

//+------------------------------------------------------------------+
//| Account-level bookkeeping shared by all charts                   |
//+------------------------------------------------------------------+
void UpdateDayAndPeak()
  {
   string kDay = g_pfx + "Day", kEq = g_pfx + "DayEq", kPeak = g_pfx + "Peak";
   double today = (double)((long)TimeCurrent() / 86400);
   if(!GlobalVariableCheck(kDay) || GlobalVariableGet(kDay) != today)
     {
      GlobalVariableSet(kDay, today);
      GlobalVariableSet(kEq, AccountEquity());
     }
   if(!GlobalVariableCheck(kPeak) || AccountEquity() > GlobalVariableGet(kPeak))
      GlobalVariableSet(kPeak, AccountEquity());
  }

double DayLossPct()
  {
   double start = GlobalVariableGet(g_pfx + "DayEq");
   if(start <= 0) return(0);
   return((start - AccountEquity()) / start * 100.0);
  }

double DrawdownPct()
  {
   double peak = GlobalVariableGet(g_pfx + "Peak");
   if(peak <= 0) return(0);
   return((peak - AccountEquity()) / peak * 100.0);
  }

bool IsHalted()
  {
   return(GlobalVariableCheck(g_pfx + "Halt") && GlobalVariableGet(g_pfx + "Halt") > 0);
  }

bool CheckDrawdownHalt()
  {
   if(IsHalted())
     {
      if(CountOurOrders() > 0) CloseAllOurs("halt");
      return(true);
     }
   if(DrawdownPct() >= MaxDrawdownPct)
     {
      GlobalVariableSet(g_pfx + "Halt", 1);
      Notify("MAX DRAWDOWN " + DoubleToString(DrawdownPct(), 1) + "% reached. Closing all, EA halted.");
      LogCsv("HALT", 0, "drawdown " + DoubleToString(DrawdownPct(), 2));
      CloseAllOurs("halt");
      return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Entry gate                                                       |
//+------------------------------------------------------------------+
string EntryBlockReason(double atr)
  {
   if(!IsTradeAllowed())                     return("trading not allowed");
   if(iBars(Symbol(), PERIOD_H1) < 150)      return("not enough H1 bars");
   if(iBars(Symbol(), PERIOD_H4) < Trend_SlowEMA + 10) return("not enough H4 bars");
   if(atr <= 0)                              return("no ATR");

   if(DayLossPct() >= MaxDailyLossPct)
     {
      string kNote = g_pfx + "DayNote";
      double day = GlobalVariableGet(g_pfx + "Day");
      if(!GlobalVariableCheck(kNote) || GlobalVariableGet(kNote) != day)
        {
         GlobalVariableSet(kNote, day);
         Notify("Daily loss limit reached (" + DoubleToString(DayLossPct(), 2) + "%). No new entries today.");
         LogCsv("DAYLIMIT", 0, DoubleToString(DayLossPct(), 2));
        }
      return("daily loss limit");
     }

   datetime now = TimeCurrent();
   int h = TimeHour(now);
   if(CloseOnFriday && TimeDayOfWeek(now) == 5 && h >= FridayCloseHour - 2) return("friday");
   if(InHourWindow(h, RolloverStartHour, RolloverEndHour))                  return("rollover");
   if(InNewsWindow(now))                                                    return("news");

   double atrLong = iATR(Symbol(), PERIOD_H1, 100, 1);
   if(atrLong > 0 && atr / atrLong > VolSpikeRatio)                         return("volatility spike");
   if((Ask - Bid) > MaxSpreadAtrRatio * atr)                                return("spread");
   return("");
  }

bool InHourWindow(int h, int from, int to)
  {
   if(from == to) return(false);
   if(from < to)  return(h >= from && h < to);
   return(h >= from || h < to);
  }

void ParseNews()
  {
   ArrayResize(g_news, 0);
   if(StringLen(NewsTimes) < 10) return;
   string parts[];
   int n = StringSplit(NewsTimes, ';', parts);
   for(int i = 0; i < n; i++)
     {
      string s = StringTrimLeft(StringTrimRight(parts[i]));
      if(StringLen(s) < 10) continue;
      datetime t = StringToTime(s);
      if(t <= 0) continue;
      int k = ArraySize(g_news);
      ArrayResize(g_news, k + 1);
      g_news[k] = t;
     }
   Print(EA_NAME, ": ", ArraySize(g_news), " news times loaded");
  }

bool InNewsWindow(datetime now)
  {
   for(int i = 0; i < ArraySize(g_news); i++)
      if(now >= g_news[i] - NewsBlockBeforeMin * 60 && now <= g_news[i] + NewsBlockAfterMin * 60)
         return(true);
   return(false);
  }

//+------------------------------------------------------------------+
//| Strategy A: trend breakout                                       |
//+------------------------------------------------------------------+
void CheckTrend(double atr)
  {
   string s = Symbol();
   if(CountPositions(s, MagicBase + STRAT_TREND) > 0) return;

   double adx = iADX(s, PERIOD_H1, AdxPeriod, PRICE_CLOSE, MODE_MAIN, 1);
   if(adx < Trend_AdxMin) return;

   double emaF = iMA(s, PERIOD_H4, Trend_FastEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double emaS = iMA(s, PERIOD_H4, Trend_SlowEMA, 0, MODE_EMA, PRICE_CLOSE, 1);
   double c1   = iClose(s, PERIOD_H1, 1);
   double hh   = iHigh(s, PERIOD_H1, iHighest(s, PERIOD_H1, MODE_HIGH, Trend_BreakoutBars, 2));
   double ll   = iLow(s, PERIOD_H1, iLowest(s, PERIOD_H1, MODE_LOW, Trend_BreakoutBars, 2));
   if(emaF <= 0 || emaS <= 0 || hh <= 0 || ll <= 0) return;

   if(emaF > emaS && c1 > hh)
      OpenTrade(STRAT_TREND, OP_BUY, Trend_SL_ATR * atr, 0, "trend breakout up");
   else if(emaF < emaS && c1 < ll)
      OpenTrade(STRAT_TREND, OP_SELL, Trend_SL_ATR * atr, 0, "trend breakout down");
  }

//+------------------------------------------------------------------+
//| Strategy B: mean reversion in a range                            |
//+------------------------------------------------------------------+
void CheckMeanRev(double atr)
  {
   string s = Symbol();
   if(CountPositions(s, MagicBase + STRAT_MR) > 0) return;
   if(MR_UseSession && !InHourWindow(TimeHour(TimeCurrent()), MR_SessionStart, MR_SessionEnd)) return;

   double adx   = iADX(s, PERIOD_H1, AdxPeriod, PRICE_CLOSE, MODE_MAIN, 1);
   double adxH4 = iADX(s, PERIOD_H4, AdxPeriod, PRICE_CLOSE, MODE_MAIN, 1);
   if(adx >= MR_AdxMax || adxH4 >= MR_H4AdxMax) return;

   double up  = iBands(s, PERIOD_H1, MR_BBPeriod, MR_BBDev, 0, PRICE_CLOSE, MODE_UPPER, 1);
   double lo  = iBands(s, PERIOD_H1, MR_BBPeriod, MR_BBDev, 0, PRICE_CLOSE, MODE_LOWER, 1);
   double mid = iBands(s, PERIOD_H1, MR_BBPeriod, MR_BBDev, 0, PRICE_CLOSE, MODE_MAIN, 1);
   double rsi = iRSI(s, PERIOD_H1, MR_RsiPeriod, PRICE_CLOSE, 1);
   double c1  = iClose(s, PERIOD_H1, 1);
   if(up <= 0 || lo <= 0 || mid <= 0) return;

   double slDist = MR_SL_ATR * atr;
   if(c1 < lo && rsi < MR_RsiLow)
     {
      if(mid - Ask >= MR_MinRR * slDist)
         OpenTrade(STRAT_MR, OP_BUY, slDist, mid, "range fade long");
     }
   else if(c1 > up && rsi > MR_RsiHigh)
     {
      if(Bid - mid >= MR_MinRR * slDist)
         OpenTrade(STRAT_MR, OP_SELL, slDist, mid, "range fade short");
     }
  }

//+------------------------------------------------------------------+
//| Position management (once per H1 bar)                            |
//+------------------------------------------------------------------+
void ManageOpen(double atr)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol()) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      int m = OrderMagicNumber();
      if(m == MagicBase + STRAT_TREND)
         TrailSelected(atr);
      else if(m == MagicBase + STRAT_MR)
        {
         if(TimeCurrent() - OrderOpenTime() >= MR_MaxHoldBars * 3600)
            CloseSelected("time exit");
        }
     }
  }

void TrailSelected(double atr)
  {
   if(atr <= 0) return;
   RefreshRates();
   double c1      = iClose(Symbol(), PERIOD_H1, 1);
   double sl      = OrderStopLoss();
   double minDist = MarketInfo(Symbol(), MODE_STOPLEVEL) * Point;
   double n       = 0;
   bool   move    = false;

   if(OrderType() == OP_BUY)
     {
      n = NormalizeDouble(c1 - Trend_Trail_ATR * atr, Digits);
      move = (n > sl + 0.1 * atr && n < Bid - minDist);
     }
   else
     {
      n = NormalizeDouble(c1 + Trend_Trail_ATR * atr, Digits);
      move = ((sl <= 0 || n < sl - 0.1 * atr) && n > Ask + minDist);
     }
   if(!move) return;

   ResetLastError();
   if(!OrderModify(OrderTicket(), OrderOpenPrice(), n, OrderTakeProfit(), 0, clrNONE))
      Print(EA_NAME, ": trail modify failed #", OrderTicket(), " err ", GetLastError());
  }

void ManageFridayClose()
  {
   if(!CloseOnFriday) return;
   datetime now = TimeCurrent();
   if(TimeDayOfWeek(now) != 5 || TimeHour(now) < FridayCloseHour) return;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || !IsOurMagic(OrderMagicNumber())) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      CloseSelected("friday close");
     }
  }

//+------------------------------------------------------------------+
//| Order helpers                                                    |
//+------------------------------------------------------------------+
bool IsOurMagic(int m)
  {
   return(m == MagicBase + STRAT_TREND || m == MagicBase + STRAT_MR);
  }

int CountPositions(string sym, int magic)
  {
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() == sym && OrderMagicNumber() == magic) n++;
     }
   return(n);
  }

int CountOurOrders()
  {
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(IsOurMagic(OrderMagicNumber())) n++;
     }
   return(n);
  }

double MoneyPerLot(string sym, double priceDist)
  {
   double tv = MarketInfo(sym, MODE_TICKVALUE);
   double ts = MarketInfo(sym, MODE_TICKSIZE);
   if(tv <= 0 || ts <= 0) return(0);
   return(priceDist / ts * tv);
  }

// +1 = position is long USD, -1 = short USD, 0 = no USD leg
int UsdSign(string sym, int type)
  {
   int dir = (type == OP_BUY) ? 1 : -1;
   if(SymbolInfoString(sym, SYMBOL_CURRENCY_BASE) == "USD")   return(dir);
   if(SymbolInfoString(sym, SYMBOL_CURRENCY_PROFIT) == "USD") return(-dir);
   return(0);
  }

// Risk in account currency of the currently selected order
double SelectedOrderRisk()
  {
   double sl = OrderStopLoss();
   if(sl <= 0) return(AccountBalance() * RiskPercent / 100.0);
   double dist = (OrderType() == OP_BUY) ? OrderOpenPrice() - sl : sl - OrderOpenPrice();
   if(dist <= 0) return(0);
   return(MoneyPerLot(OrderSymbol(), dist) * OrderLots());
  }

void PortfolioRisk(double &total, double &usdLong, double &usdShort, int &count)
  {
   total = 0; usdLong = 0; usdShort = 0; count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(!IsOurMagic(OrderMagicNumber())) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      double r = SelectedOrderRisk();
      int sgn = UsdSign(OrderSymbol(), OrderType());
      total += r;
      if(sgn > 0) usdLong += r;
      if(sgn < 0) usdShort += r;
      count++;
     }
  }

bool IsRetryable(int err)
  {
   return(err == 4 || err == 6 || err == 128 || err == 129 || err == 135 ||
          err == 136 || err == 137 || err == 138 || err == 146);
  }

// Cross-chart lock so two charts cannot pass the portfolio check at once
bool AcquireLock()
  {
   if(IsTesting()) return(true);
   string k = g_pfx + "Lock";
   for(int i = 0; i < 50; i++)
     {
      if(!GlobalVariableCheck(k))
        {
         GlobalVariableTemp(k);
         GlobalVariableSet(k, 0);
        }
      if(GlobalVariableSetOnCondition(k, 1, 0)) return(true);
      Sleep(100);
     }
   return(false);
  }

void ReleaseLock()
  {
   if(IsTesting()) return;
   GlobalVariableSet(g_pfx + "Lock", 0);
  }

//+------------------------------------------------------------------+
//| Open a trade with fixed fractional risk                          |
//+------------------------------------------------------------------+
bool OpenTrade(int strat, int type, double slDist, double tpPrice, string reason)
  {
   if(!AcquireLock())
     {
      Print(EA_NAME, ": lock timeout, entry skipped");
      return(false);
     }
   bool ok = OpenTradeLocked(strat, type, slDist, tpPrice, reason);
   ReleaseLock();
   return(ok);
  }

bool OpenTradeLocked(int strat, int type, double slDist, double tpPrice, string reason)
  {
   string s = Symbol();
   RefreshRates();
   double price   = (type == OP_BUY) ? Ask : Bid;
   double minDist = MarketInfo(s, MODE_STOPLEVEL) * Point + (Ask - Bid);
   if(slDist <= minDist)
     {
      Print(EA_NAME, ": stop too close for broker stop level, skipped");
      return(false);
     }
   if(tpPrice > 0 && MathAbs(tpPrice - price) <= minDist) return(false);

   //--- lot size from risk
   double balance   = MathMin(AccountBalance(), AccountEquity());
   double riskMoney = balance * RiskPercent / 100.0;
   double perLot    = MoneyPerLot(s, slDist);
   if(perLot <= 0) return(false);
   double step   = MarketInfo(s, MODE_LOTSTEP);
   double minLot = MarketInfo(s, MODE_MINLOT);
   double maxLot = MathMin(MarketInfo(s, MODE_MAXLOT), MaxLots);
   if(step <= 0) step = 0.01;
   double lots = MathFloor(riskMoney / perLot / step + 1e-9) * step;
   lots = NormalizeDouble(MathMin(lots, maxLot), 2);
   if(lots < minLot)
     {
      Print(EA_NAME, ": risk budget below minimum lot, skipped (", reason, ")");
      LogCsv("SKIP", 0, "min lot exceeds risk; " + reason);
      return(false);
     }
   double newRisk = perLot * lots;

   //--- portfolio limits
   double total, usdLong, usdShort;
   int    count;
   PortfolioRisk(total, usdLong, usdShort, count);
   if(count >= MaxOpenPositions)                                  return(Skip("max positions", reason));
   if(total + newRisk > balance * MaxPortfolioRiskPct / 100.0)    return(Skip("portfolio risk cap", reason));
   int sgn = UsdSign(s, type);
   double usdCap = balance * MaxUsdRiskPct / 100.0;
   if(sgn > 0 && usdLong + newRisk > usdCap)                      return(Skip("USD long cap", reason));
   if(sgn < 0 && usdShort + newRisk > usdCap)                     return(Skip("USD short cap", reason));

   //--- margin
   ResetLastError();
   double freeAfter = AccountFreeMarginCheck(s, type, lots);
   if(freeAfter <= 0 || GetLastError() == 134)                    return(Skip("not enough margin", reason));
   double marginAfter = AccountMargin() + (AccountFreeMargin() - freeAfter);
   if(marginAfter > 0 && AccountEquity() / marginAfter * 100.0 < MinMarginLevelPct)
      return(Skip("margin level", reason));

   //--- send
   int    magic   = MagicBase + strat;
   string comment = EA_NAME + (strat == STRAT_TREND ? "-A" : "-B");
   int    ticket  = -1;
   bool   twoStep = false;
   double sl = 0, tp = 0;
   int    err = 0;

   for(int a = 0; a < MaxRetries + 1; a++)
     {
      RefreshRates();
      price = (type == OP_BUY) ? Ask : Bid;
      sl = NormalizeDouble((type == OP_BUY) ? price - slDist : price + slDist, Digits);
      tp = (tpPrice > 0) ? NormalizeDouble(tpPrice, Digits) : 0;
      ResetLastError();
      ticket = OrderSend(s, type, lots, NormalizeDouble(price, Digits), SlippagePoints,
                         twoStep ? 0 : sl, twoStep ? 0 : tp, comment, magic, 0,
                         type == OP_BUY ? clrDodgerBlue : clrTomato);
      if(ticket > 0) break;
      err = GetLastError();
      if(err == 130 && !twoStep) { twoStep = true; continue; }   // broker wants stops set after fill
      if(!IsRetryable(err)) break;
      Sleep(500);
     }
   if(ticket <= 0)
     {
      Print(EA_NAME, ": OrderSend failed err ", err, " (", reason, ")");
      LogCsv("SENDFAIL", 0, "err " + IntegerToString(err) + "; " + reason);
      return(false);
     }

   if(twoStep && !AttachStops(ticket, type, slDist, tp))
     {
      // never leave a position without a stop
      if(OrderSelect(ticket, SELECT_BY_TICKET)) CloseSelected("could not set stop");
      Notify(s + ": position closed because the stop could not be set.");
      return(false);
     }

   AddTicket(ticket);
   string d = reason + "; lots " + DoubleToString(lots, 2) + "; risk " + DoubleToString(newRisk, 2);
   LogCsv(type == OP_BUY ? "BUY" : "SELL", ticket, d);
   Notify(s + (type == OP_BUY ? " BUY " : " SELL ") + DoubleToString(lots, 2) + " (" + reason + ")");
   return(true);
  }

bool Skip(string why, string reason)
  {
   Print(EA_NAME, ": entry skipped, ", why, " (", reason, ")");
   LogCsv("SKIP", 0, why + "; " + reason);
   return(false);
  }

bool AttachStops(int ticket, int type, double slDist, double tp)
  {
   for(int a = 0; a < MaxRetries; a++)
     {
      if(!OrderSelect(ticket, SELECT_BY_TICKET)) { Sleep(300); continue; }
      double op = OrderOpenPrice();
      double sl = NormalizeDouble((type == OP_BUY) ? op - slDist : op + slDist, Digits);
      ResetLastError();
      if(OrderModify(ticket, op, sl, tp, 0, clrNONE)) return(true);
      Print(EA_NAME, ": attach stops failed err ", GetLastError());
      Sleep(500);
     }
   return(false);
  }

// Close the currently selected market order
bool CloseSelected(string why)
  {
   int    ticket = OrderTicket();
   int    type   = OrderType();
   string sym    = OrderSymbol();
   double lots   = OrderLots();
   int    dg     = (int)MarketInfo(sym, MODE_DIGITS);
   int    err    = 0;

   for(int a = 0; a < MaxRetries + 1; a++)
     {
      RefreshRates();
      double price = (type == OP_BUY) ? MarketInfo(sym, MODE_BID) : MarketInfo(sym, MODE_ASK);
      ResetLastError();
      if(OrderClose(ticket, lots, NormalizeDouble(price, dg), SlippagePoints, clrGray))
        {
         Print(EA_NAME, ": closed #", ticket, " (", why, ")");
         return(true);
        }
      err = GetLastError();
      if(!IsRetryable(err)) break;
      Sleep(500);
     }
   Print(EA_NAME, ": close failed #", ticket, " err ", err, " (", why, ")");
   return(false);
  }

void CloseAllOurs(string why)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(!IsOurMagic(OrderMagicNumber())) continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL) continue;
      CloseSelected(why);
     }
  }

//+------------------------------------------------------------------+
//| Ticket tracking: detect closes for logging and notification      |
//+------------------------------------------------------------------+
void AddTicket(int ticket)
  {
   for(int i = 0; i < ArraySize(g_tickets); i++)
      if(g_tickets[i] == ticket) return;
   int n = ArraySize(g_tickets);
   ArrayResize(g_tickets, n + 1);
   g_tickets[n] = ticket;
  }

void RebuildTickets()
  {
   ArrayResize(g_tickets, 0);
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() == Symbol() && IsOurMagic(OrderMagicNumber())) AddTicket(OrderTicket());
     }
  }

void SyncTickets()
  {
   for(int i = ArraySize(g_tickets) - 1; i >= 0; i--)
     {
      if(!OrderSelect(g_tickets[i], SELECT_BY_TICKET)) continue;
      if(OrderCloseTime() == 0) continue;
      double pl = OrderProfit() + OrderSwap() + OrderCommission();
      LogCsv("CLOSE", OrderTicket(), "pl " + DoubleToString(pl, 2) + "; " + OrderComment());
      Notify(OrderSymbol() + " closed #" + IntegerToString(OrderTicket()) + " P/L " + DoubleToString(pl, 2));
      int last = ArraySize(g_tickets) - 1;
      g_tickets[i] = g_tickets[last];
      ArrayResize(g_tickets, last);
     }
  }

//+------------------------------------------------------------------+
//| Output                                                           |
//+------------------------------------------------------------------+
void Notify(string msg)
  {
   Print(EA_NAME, ": ", msg);
   if(IsTesting()) return;
   if(UsePush)  SendNotification(EA_NAME + ": " + msg);
   if(UseAlert) Alert(EA_NAME + ": " + msg);
  }

void LogCsv(string event, int ticket, string detail)
  {
   if(!EnableCsvLog || IsOptimization()) return;
   string fn = EA_NAME + "_" + Symbol() + ".csv";
   int h = FileOpen(fn, FILE_CSV | FILE_READ | FILE_WRITE | FILE_SHARE_READ, ',');
   if(h == INVALID_HANDLE) return;
   if(FileSize(h) == 0)
      FileWrite(h, "time", "symbol", "event", "ticket", "detail", "balance", "equity");
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), Symbol(), event,
             IntegerToString(ticket), detail,
             DoubleToString(AccountBalance(), 2), DoubleToString(AccountEquity(), 2));
   FileClose(h);
  }

void Dashboard()
  {
   if(!ShowDashboard || IsOptimization()) return;
   if(IsTesting() && !IsVisualMode()) return;
   double total, usdLong, usdShort;
   int    count;
   PortfolioRisk(total, usdLong, usdShort, count);
   double bal = AccountBalance();
   string t = EA_NAME + "  [" + g_status + "]\n";
   t += "Day P/L: " + DoubleToString(-DayLossPct(), 2) + "%  (limit -" + DoubleToString(MaxDailyLossPct, 1) + "%)\n";
   t += "Drawdown: " + DoubleToString(DrawdownPct(), 2) + "%  (halt at " + DoubleToString(MaxDrawdownPct, 1) + "%)\n";
   t += "Open positions (all symbols): " + IntegerToString(count) + "\n";
   if(bal > 0)
      t += "Open risk: " + DoubleToString(total / bal * 100.0, 2) + "%   USD long " +
           DoubleToString(usdLong / bal * 100.0, 2) + "% / short " +
           DoubleToString(usdShort / bal * 100.0, 2) + "%\n";
   Comment(t);
  }
//+------------------------------------------------------------------+
