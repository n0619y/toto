//+------------------------------------------------------------------+
//|                                                   GoldTrendEA.mq4 |
//|  XAU/USD(GOLD) 向け トレンドフォロー型 自動売買EA (MVP)          |
//|                                                                  |
//|  戦略: 高速EMA と 低速EMA のクロスで方向を決め、ATRベースで      |
//|        損切り(SL)と利食い(TP)を置く順張りトレンドフォロー。      |
//|  資金管理: 1トレードのリスク%からロットを自動計算。              |
//|  安全装置: 最大ドローダウン/日次損失上限で取引停止。             |
//+------------------------------------------------------------------+
#property copyright "FX GOLD EA Project"
#property version   "0.2"
#property strict

#include <MoneyManagement.mqh>
#include <RiskGuard.mqh>
#include <TradeHelper.mqh>

//=== 入力パラメータ ================================================
input string  Sec_General   = "==== 基本設定 ====";
input int     MagicNumber    = 20260622;   // マジックナンバー(自EA識別)
input int     Slippage       = 30;         // 許容スリッページ(ポイント)
input double  MaxSpreadPoints = 50;        // 許容最大スプレッド(ポイント) 超えたら見送り

input string  Sec_Risk      = "==== 資金/リスク管理 ====";
input double  RiskPercent    = 1.0;        // 1トレードのリスク(残高%)
input double  MaxDailyLossPct = 5.0;       // 日次損失上限%(超で当日停止) 0=無効
input double  MaxDrawdownPct  = 20.0;      // 最大DD%(超で停止) 0=無効

input string  Sec_Strategy  = "==== 戦略(EMAクロス) ====";
input int     FastEmaPeriod  = 20;         // 高速EMA期間
input int     SlowEmaPeriod  = 50;         // 低速EMA期間
input int     AtrPeriod      = 14;         // ATR期間
input double  SL_AtrMult      = 2.0;       // SL = ATR * この倍率
input double  TP_RR           = 1.5;       // TP = SL * このリスクリワード比

input string  Sec_Exit      = "==== 決済補助 ====";
input bool    UseBreakEven   = true;       // 建値撤退を使う
input double  BE_AtrTrigger   = 1.0;       // 含み益がATR*この倍率でSLを建値へ
input bool    UseTrailing    = true;       // トレーリングを使う
input double  Trail_AtrMult   = 2.0;       // トレール幅 = ATR * この倍率

input string  Sec_Time      = "==== 時間フィルター(サーバー時間) ====";
input bool    UseTimeFilter  = true;       // 取引時間帯を制限する
input int     StartHour       = 8;         // 取引開始時(時)
input int     EndHour         = 22;        // 取引終了時(時)
input bool    TradeOnFriday   = true;      // 金曜も取引する

//=== 内部状態 ======================================================
datetime g_lastBarTime = 0;   // 確定足ごとに1回だけ判定するため

//+------------------------------------------------------------------+
int OnInit()
{
   if(FastEmaPeriod >= SlowEmaPeriod)
      Print("警告: FastEmaPeriod は SlowEmaPeriod より小さくしてください。");
   PrintFormat("GoldTrendEA init: %s digits=%d point=%.5f",
               Symbol(), (int)MarketInfo(Symbol(), MODE_DIGITS), Point);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {}

//+------------------------------------------------------------------+
//| スプレッドが許容範囲か                                          |
//+------------------------------------------------------------------+
bool SpreadOK()
{
   double spread = (MarketInfo(Symbol(), MODE_ASK) - MarketInfo(Symbol(), MODE_BID)) / Point;
   return(spread <= MaxSpreadPoints);
}

//+------------------------------------------------------------------+
//| 取引時間帯か                                                    |
//+------------------------------------------------------------------+
bool TimeOK()
{
   if(!UseTimeFilter) return(true);
   int h   = TimeHour(TimeCurrent());
   int dow = TimeDayOfWeek(TimeCurrent());
   if(dow == 0 || dow == 6) return(false);          // 土日
   if(!TradeOnFriday && dow == 5) return(false);     // 金曜除外
   if(StartHour <= EndHour) return(h >= StartHour && h < EndHour);
   return(h >= StartHour || h < EndHour);            // 日跨ぎ対応
}

//+------------------------------------------------------------------+
//| シグナル判定: +1=買い / -1=売り / 0=なし (確定足のクロス)        |
//+------------------------------------------------------------------+
int GetSignal()
{
   double fastPrev = iMA(Symbol(), 0, FastEmaPeriod, 0, MODE_EMA, PRICE_CLOSE, 2);
   double slowPrev = iMA(Symbol(), 0, SlowEmaPeriod, 0, MODE_EMA, PRICE_CLOSE, 2);
   double fastNow  = iMA(Symbol(), 0, FastEmaPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double slowNow  = iMA(Symbol(), 0, SlowEmaPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);

   if(fastPrev <= slowPrev && fastNow > slowNow) return(1);   // ゴールデンクロス
   if(fastPrev >= slowPrev && fastNow < slowNow) return(-1);  // デッドクロス
   return(0);
}

//+------------------------------------------------------------------+
void OnTick()
{
   RiskGuard_UpdateDaily();

   string sym  = Symbol();
   double atr  = iATR(sym, 0, AtrPeriod, 1);

   //--- 決済補助は毎ティック処理 ---
   if(UseBreakEven && atr > 0)
      ApplyBreakEven(sym, MagicNumber, atr * BE_AtrTrigger, Point); // 建値+1ポイントで固定
   if(UseTrailing && atr > 0)
      ApplyTrailing(sym, MagicNumber, atr * Trail_AtrMult);

   //--- 確定足ごとに1回だけエントリー判定 ---
   if(g_lastBarTime == Time[0]) return;
   g_lastBarTime = Time[0];

   //--- 安全装置・フィルター ---
   if(!RiskGuard_TradingAllowed(MaxDailyLossPct, MaxDrawdownPct)) return;
   if(!TimeOK())   return;
   if(!SpreadOK()) return;
   if(atr <= 0)    return;

   //--- 既にポジションがあれば新規は取らない(1ポジ運用) ---
   if(CountMyOrders(sym, MagicNumber) > 0) return;

   //--- シグナル ---
   int sig = GetSignal();
   if(sig == 0) return;

   double slDist = atr * SL_AtrMult;
   double tpDist = slDist * TP_RR;
   double lots   = CalcLotByRisk(sym, slDist, RiskPercent);
   if(lots <= 0) { Print("ロット計算0のため見送り"); return; }

   int type = (sig > 0) ? OP_BUY : OP_SELL;
   OpenTrade(sym, type, lots, slDist, tpDist, MagicNumber, Slippage, "GoldTrendEA");
}
//+------------------------------------------------------------------+
