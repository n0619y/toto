//+------------------------------------------------------------------+
//|                                            MoneyManagement.mqh    |
//|  資金管理モジュール: リスク%からロットを自動計算する             |
//+------------------------------------------------------------------+
#property strict

//+------------------------------------------------------------------+
//| ロットを業者の制約（最小/最大/ステップ）に丸める                 |
//+------------------------------------------------------------------+
double NormalizeLot(string sym, double lots)
{
   double minLot  = MarketInfo(sym, MODE_MINLOT);
   double maxLot  = MarketInfo(sym, MODE_MAXLOT);
   double lotStep = MarketInfo(sym, MODE_LOTSTEP);
   if(lotStep <= 0) lotStep = 0.01;

   lots = MathFloor(lots / lotStep) * lotStep;   // ステップに合わせて切り捨て
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;

   // 小数桁を lotStep に合わせて整える
   int digits = (int)MathRound(MathLog10(1.0 / lotStep));
   if(digits < 0) digits = 0;
   return(NormalizeDouble(lots, digits));
}

//+------------------------------------------------------------------+
//| リスク%とSL距離(価格差)からロットを計算                          |
//|  slPriceDistance : エントリー価格とSLの価格差(絶対値)            |
//|  riskPercent     : 1トレードで許容する残高に対する損失%          |
//+------------------------------------------------------------------+
double CalcLotByRisk(string sym, double slPriceDistance, double riskPercent)
{
   if(slPriceDistance <= 0.0 || riskPercent <= 0.0)
      return(0.0);

   double balance   = AccountBalance();
   double riskMoney = balance * riskPercent / 100.0;

   double tickValue = MarketInfo(sym, MODE_TICKVALUE); // 1ティック・1ロットあたりの損益(口座通貨)
   double tickSize  = MarketInfo(sym, MODE_TICKSIZE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return(0.0);

   // SL距離で1ロットあたりに発生する損失額
   double lossPerLot = (slPriceDistance / tickSize) * tickValue;
   if(lossPerLot <= 0.0)
      return(0.0);

   double lots = riskMoney / lossPerLot;
   return(NormalizeLot(sym, lots));
}
//+------------------------------------------------------------------+
