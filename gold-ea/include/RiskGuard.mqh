//+------------------------------------------------------------------+
//|                                                   RiskGuard.mqh   |
//|  リスク管理(安全装置): 最大DD・日次損失上限で取引を停止する      |
//+------------------------------------------------------------------+
#property strict

//--- 日次集計用の内部状態
double g_dayStartEquity = 0.0;   // その日の開始時エクイティ
int    g_currentDay     = -1;    // 現在処理中の日(DayOfYear)

//+------------------------------------------------------------------+
//| 日付が変わったら日次基準を更新する。OnTickの先頭で呼ぶ           |
//+------------------------------------------------------------------+
void RiskGuard_UpdateDaily()
{
   int doy = DayOfYear();
   if(doy != g_currentDay)
   {
      g_currentDay     = doy;
      g_dayStartEquity = AccountEquity();
   }
}

//+------------------------------------------------------------------+
//| 本日の損益率(%)。マイナスは損失                                  |
//+------------------------------------------------------------------+
double RiskGuard_DailyPnLPercent()
{
   if(g_dayStartEquity <= 0.0) return(0.0);
   return((AccountEquity() - g_dayStartEquity) / g_dayStartEquity * 100.0);
}

//+------------------------------------------------------------------+
//| 口座全体のドローダウン率(%)。残高に対するエクイティの下落        |
//+------------------------------------------------------------------+
double RiskGuard_DrawdownPercent()
{
   double balance = AccountBalance();
   if(balance <= 0.0) return(0.0);
   double dd = (balance - AccountEquity()) / balance * 100.0;
   return(dd > 0.0 ? dd : 0.0);
}

//+------------------------------------------------------------------+
//| 新規エントリーを許可してよいか判定する(安全装置)                 |
//|  maxDailyLossPct : 本日これ以上の損失%で当日停止 (例 5.0)        |
//|  maxDrawdownPct  : これ以上のDD%で停止          (例 20.0)        |
//|  戻り値 true=取引可 / false=停止                                 |
//+------------------------------------------------------------------+
bool RiskGuard_TradingAllowed(double maxDailyLossPct, double maxDrawdownPct)
{
   if(maxDailyLossPct > 0.0 && RiskGuard_DailyPnLPercent() <= -maxDailyLossPct)
      return(false);

   if(maxDrawdownPct > 0.0 && RiskGuard_DrawdownPercent() >= maxDrawdownPct)
      return(false);

   return(true);
}
//+------------------------------------------------------------------+
