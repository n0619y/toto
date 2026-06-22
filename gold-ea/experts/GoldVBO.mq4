//+------------------------------------------------------------------+
//|                                                      GoldVBO.mq4   |
//|  XAU/USD(GOLD) Volatility-Breakout EA                            |
//|                                                                  |
//|  ★データ分析(2012-2022 H1)とOOS検証に基づく設計★                |
//|   - ローリングNバーのレンジ・ブレイクで初動を取る(時刻に非依存)  |
//|   - EMAトレンドフィルタで『逆らわない』(OOSでPF/DD改善を確認)     |
//|   - ATRボラゲート: 変動拡大時のみ参加(ボラ・クラスタリングを利用) |
//|   - ATRハード損切り + ATRチャンデリア・トレーリング + 時間切れ    |
//|   - リスク%でロット自動計算 + 最大DD/日次損失の安全装置          |
//|                                                                  |
//|  OOS(2018-2022)実績(コスト$0.5/往復): PF1.27, CAGR+17%, DD-12%   |
//|  ※公開データでの参考値。XM実データでの再検証が前提。            |
//+------------------------------------------------------------------+
#property copyright "FX GOLD EA Project"
#property version   "1.0"
#property strict

#include <MoneyManagement.mqh>
#include <RiskGuard.mqh>

//=== 入力パラメータ ================================================
input string Sec_General      = "==== 基本 ====";
input int    MagicNumber       = 20260622;
input int    Slippage          = 30;
input double MaxSpreadPoints    = 50;      // これ超のスプレッドでは新規見送り(コスト保護)

input string Sec_Risk         = "==== 資金/リスク管理 ====";
input double RiskPercent        = 1.0;     // 1トレードのリスク(残高%)
input double MaxDailyLossPct     = 5.0;     // 日次損失上限%(0=無効)
input double MaxDrawdownPct      = 20.0;    // 最大DD%(0=無効)

input string Sec_Entry        = "==== エントリー(検証済) ====";
input int    BreakoutBars       = 12;      // ローリング・ブレイク幅(本)
input int    TrendEmaPeriod      = 200;     // トレンドフィルタEMA
input bool   UseTrendFilter      = true;    // トレンドに逆らわない
input int    AtrPeriod           = 14;      // ATR期間
input int    VolMedianBars       = 200;     // ボラゲート基準(ATR中央値)の本数
input bool   UseVolGate          = true;    // ボラ拡大時のみ参加
input bool   AllowShort          = true;    // 売りも行う

input string Sec_Exit         = "==== エグジット(検証済) ====";
input double SL_AtrMult          = 2.0;     // 初期SL = ATR×
input double Trail_AtrMult        = 3.0;     // チャンデリア・トレール = ATR×
input int    MaxHoldBars          = 72;      // 時間切れ決済(本) 0=無効

//=== 内部 ==========================================================
datetime g_lastBar = 0;

int OnInit()
{
   PrintFormat("GoldVBO init %s digits=%d point=%.5f", Symbol(),
               (int)MarketInfo(Symbol(),MODE_DIGITS), Point);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){}

//+------------------------------------------------------------------+
//| ATR(AtrPeriod) の直近 VolMedianBars 本の中央値                   |
//+------------------------------------------------------------------+
double MedianATR()
{
   int m = VolMedianBars;
   double a[]; ArrayResize(a, m);
   for(int i=0;i<m;i++) a[i]=iATR(Symbol(),0,AtrPeriod,i+1);
   ArraySort(a);
   if(m%2==1) return a[m/2];
   return (a[m/2-1]+a[m/2])/2.0;
}

bool SpreadOK()
{
   double sp=(MarketInfo(Symbol(),MODE_ASK)-MarketInfo(Symbol(),MODE_BID))/Point;
   return(sp<=MaxSpreadPoints);
}

int CountMine()
{
   int c=0;
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderSymbol()==Symbol() && OrderMagicNumber()==MagicNumber
         && (OrderType()==OP_BUY||OrderType()==OP_SELL)) c++;
   }
   return c;
}

//+------------------------------------------------------------------+
//| 保有ポジ管理: チャンデリア・トレーリング + 時間切れ             |
//+------------------------------------------------------------------+
void ManageOpen(double atr)
{
   double stopLevel = MarketInfo(Symbol(),MODE_STOPLEVEL)*Point;
   int digits=(int)MarketInfo(Symbol(),MODE_DIGITS);
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderSymbol()!=Symbol()||OrderMagicNumber()!=MagicNumber) continue;

      int barsSince=iBarShift(Symbol(),0,OrderOpenTime());
      if(MaxHoldBars>0 && barsSince>=MaxHoldBars)
      {
         double px=(OrderType()==OP_BUY)?MarketInfo(Symbol(),MODE_BID):MarketInfo(Symbol(),MODE_ASK);
         if(!OrderClose(OrderTicket(),OrderLots(),NormalizeDouble(px,digits),Slippage,clrNONE))
            Print("時間切れClose失敗 err=",GetLastError());
         continue;
      }
      int look=MathMax(barsSince+1,1);
      if(OrderType()==OP_BUY)
      {
         double hh=High[iHighest(Symbol(),0,MODE_HIGH,look,0)];
         double newSL=NormalizeDouble(hh-Trail_AtrMult*atr,digits);
         double bid=MarketInfo(Symbol(),MODE_BID);
         if(newSL>OrderStopLoss() && bid-newSL>stopLevel)
            if(!OrderModify(OrderTicket(),OrderOpenPrice(),newSL,OrderTakeProfit(),0,clrNONE))
               Print("Trail(B)失敗 err=",GetLastError());
      }
      else if(OrderType()==OP_SELL)
      {
         double ll=Low[iLowest(Symbol(),0,MODE_LOW,look,0)];
         double newSL=NormalizeDouble(ll+Trail_AtrMult*atr,digits);
         double ask=MarketInfo(Symbol(),MODE_ASK);
         if((OrderStopLoss()==0.0||newSL<OrderStopLoss()) && newSL-ask>stopLevel)
            if(!OrderModify(OrderTicket(),OrderOpenPrice(),newSL,OrderTakeProfit(),0,clrNONE))
               Print("Trail(S)失敗 err=",GetLastError());
      }
   }
}

//+------------------------------------------------------------------+
void OnTick()
{
   RiskGuard_UpdateDaily();
   double atr=iATR(Symbol(),0,AtrPeriod,1);
   if(atr>0) ManageOpen(atr);

   // 確定足ごとに1回だけ判定
   if(g_lastBar==Time[0]) return;
   g_lastBar=Time[0];

   if(!RiskGuard_TradingAllowed(MaxDailyLossPct,MaxDrawdownPct)) return;
   if(atr<=0) return;
   if(CountMine()>0) return;
   if(!SpreadOK()) return;

   // ボラゲート: 現ATRが中央値超(変動拡大)
   if(UseVolGate && atr<=MedianATR()) return;

   // ローリング・ブレイク基準(直前バーを除く BreakoutBars 本)
   double rollHigh=High[iHighest(Symbol(),0,MODE_HIGH,BreakoutBars,2)];
   double rollLow =Low [iLowest (Symbol(),0,MODE_LOW ,BreakoutBars,2)];

   // トレンドフィルタ
   double ema=iMA(Symbol(),0,TrendEmaPeriod,0,MODE_EMA,PRICE_CLOSE,1);
   bool trendLong  = (!UseTrendFilter) || (Close[1]>ema);
   bool trendShort = (!UseTrendFilter) || (Close[1]<ema);

   double slDist=SL_AtrMult*atr;
   double lots=CalcLotByRisk(Symbol(),slDist,RiskPercent);
   if(lots<=0) return;

   int digits=(int)MarketInfo(Symbol(),MODE_DIGITS);
   // 直前バーがレンジ上抜け→買い / 下抜け→売り。成行で参加。
   if(High[1]>=rollHigh && trendLong)
   {
      double ask=MarketInfo(Symbol(),MODE_ASK);
      double sl=NormalizeDouble(ask-slDist,digits);
      if(OrderSend(Symbol(),OP_BUY,lots,NormalizeDouble(ask,digits),Slippage,sl,0,"GoldVBO",MagicNumber,0,clrDodgerBlue)<0)
         Print("Buy失敗 err=",GetLastError());
   }
   else if(Low[1]<=rollLow && trendShort && AllowShort)
   {
      double bid=MarketInfo(Symbol(),MODE_BID);
      double sl=NormalizeDouble(bid+slDist,digits);
      if(OrderSend(Symbol(),OP_SELL,lots,NormalizeDouble(bid,digits),Slippage,sl,0,"GoldVBO",MagicNumber,0,clrOrangeRed)<0)
         Print("Sell失敗 err=",GetLastError());
   }
}
//+------------------------------------------------------------------+
