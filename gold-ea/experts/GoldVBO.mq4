//+------------------------------------------------------------------+
//|                                                      GoldVBO.mq4   |
//|  XAU/USD(GOLD) Volatility-Breakout EA                            |
//|                                                                  |
//|  ★データ分析(2012-2022 H1)とOOS検証に基づく設計★                |
//|   - ローリングNバーのレンジ・ブレイクで初動を取る(時刻に非依存)  |
//|   - ★逆指値ストップ注文をブレイク水準に置いて『水準で即約定』★    |
//|     (次足成行では優位性が消えるため必須。entry_parity.pyで検証)   |
//|   - EMAトレンドフィルタで『逆らわない』(OOSでPF/DD改善を確認)     |
//|   - ATRボラゲート + ★効率比フィルタ★で揉み合いのだましブレイク除外|
//|   - ATRハード損切り + ATRチャンデリア・トレーリング + 時間切れ    |
//|   - リスク%でロット自動計算 + 最大DD/日次損失の安全装置          |
//|                                                                  |
//|  時間足別に最適化(multi_tf.py): H1→BreakoutBars=12 / H4→=24      |
//|  OOS実績(ER0.3,コスト$0.5): H1 PF2.28/Sh2.40, H4 PF2.32/Sh1.44   |
//|  XM実データ2023-25でも存続(H1 PF2.36, H4 PF2.13)。詳細TIMEFRAME_GUIDE|
//|  ※参考値。XM実データの全ティック再検証が前提。                 |
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
input bool   UseEfficiencyFilter  = true;    // ★効率比フィルタ:揉み合いのだましブレイクを除外
input int    ErPeriod            = 20;      // カウフマン効率比の期間
input double ErThreshold         = 0.30;    // この値以上(効率的トレンド)のみ参加
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

//+------------------------------------------------------------------+
//| カウフマン効率比 = |ErPeriod本の純変化| / Σ|1本ごとの変化|       |
//|  1に近い=効率的トレンド / 0に近い=揉み合い(だましが多い)         |
//+------------------------------------------------------------------+
double EfficiencyRatio()
{
   int n=ErPeriod;
   double net=MathAbs(Close[1]-Close[1+n]);
   double vol=0.0;
   for(int j=1;j<=n;j++) vol+=MathAbs(Close[j]-Close[j+1]);
   if(vol<=0.0) return(0.0);
   return(net/vol);
}

int CountMine()   // 成行ポジ(約定済み)の数
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
//| 自分の未約定ペンディング注文を全削除(新バーで毎回置き直すため)   |
//+------------------------------------------------------------------+
void DeleteMyPending()
{
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES)) continue;
      if(OrderSymbol()!=Symbol()||OrderMagicNumber()!=MagicNumber) continue;
      int t=OrderType();
      if(t==OP_BUYSTOP||t==OP_SELLSTOP||t==OP_BUYLIMIT||t==OP_SELLLIMIT)
         if(!OrderDelete(OrderTicket()))
            Print("Pending削除失敗 err=",GetLastError());
   }
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
      if(OrderType()!=OP_BUY && OrderType()!=OP_SELL) continue;  // ペンディングは対象外

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

   if(!RiskGuard_TradingAllowed(MaxDailyLossPct,MaxDrawdownPct)){ DeleteMyPending(); return; }
   if(atr<=0) return;

   // 新バーごとに古いペンディングは必ず置き直す(水準・条件を最新化)
   bool havePos = (CountMine()>0);
   DeleteMyPending();
   if(havePos) return;                       // 約定済みポジ保有中は新規を置かない
   if(!SpreadOK()) return;

   // ボラゲート: 現ATRが中央値超(変動拡大)
   if(UseVolGate && atr<=MedianATR()) return;
   // 効率比フィルタ: 揉み合い(だましブレイク多発)局面を除外
   if(UseEfficiencyFilter && EfficiencyRatio()<ErThreshold) return;

   // ローリング・ブレイク基準(直近 BreakoutBars 本の確定足 = shift 1..BreakoutBars)
   double rollHigh=High[iHighest(Symbol(),0,MODE_HIGH,BreakoutBars,1)];
   double rollLow =Low [iLowest (Symbol(),0,MODE_LOW ,BreakoutBars,1)];

   // トレンドフィルタ(直近確定足の終値)
   double ema=iMA(Symbol(),0,TrendEmaPeriod,0,MODE_EMA,PRICE_CLOSE,1);
   bool trendLong  = (!UseTrendFilter) || (Close[1]>ema);
   bool trendShort = (!UseTrendFilter) || (Close[1]<ema);

   double slDist=SL_AtrMult*atr;
   double lots=CalcLotByRisk(Symbol(),slDist,RiskPercent);
   if(lots<=0) return;

   int    digits=(int)MarketInfo(Symbol(),MODE_DIGITS);
   double stopLevel=MarketInfo(Symbol(),MODE_STOPLEVEL)*Point;
   // 有効期限は付けない(業者により拒否される)。新バー毎にDeleteMyPendingで置き直すため不要。
   datetime expiry=0;

   // 買い: ブレイク水準(rollHigh)に逆指値ストップ。既に上抜け済みなら成行。
   if(trendLong)
   {
      double ask=MarketInfo(Symbol(),MODE_ASK);
      double entryPx=NormalizeDouble(rollHigh,digits);
      if(rollHigh <= ask+stopLevel)   // 既に水準到達 → 成行(=次足始値ではなく即時)
      {
         double sl=NormalizeDouble(ask-slDist,digits);
         if(OrderSend(Symbol(),OP_BUY,lots,NormalizeDouble(ask,digits),Slippage,sl,0,"GoldVBO",MagicNumber,0,clrDodgerBlue)<0)
            Print("Buy(成行)失敗 err=",GetLastError());
      }
      else                            // 未到達 → 逆指値ストップで水準約定を狙う
      {
         double sl=NormalizeDouble(rollHigh-slDist,digits);
         if(OrderSend(Symbol(),OP_BUYSTOP,lots,entryPx,Slippage,sl,0,"GoldVBO",MagicNumber,expiry,clrDodgerBlue)<0)
            Print("BuyStop失敗 err=",GetLastError());
      }
   }
   // 売り: ブレイク水準(rollLow)に逆指値ストップ。既に下抜け済みなら成行。
   else if(trendShort && AllowShort)
   {
      double bid=MarketInfo(Symbol(),MODE_BID);
      double entryPx=NormalizeDouble(rollLow,digits);
      if(rollLow >= bid-stopLevel)    // 既に水準到達 → 成行
      {
         double sl=NormalizeDouble(bid+slDist,digits);
         if(OrderSend(Symbol(),OP_SELL,lots,NormalizeDouble(bid,digits),Slippage,sl,0,"GoldVBO",MagicNumber,0,clrOrangeRed)<0)
            Print("Sell(成行)失敗 err=",GetLastError());
      }
      else                            // 未到達 → 逆指値ストップ
      {
         double sl=NormalizeDouble(rollLow+slDist,digits);
         if(OrderSend(Symbol(),OP_SELLSTOP,lots,entryPx,Slippage,sl,0,"GoldVBO",MagicNumber,expiry,clrOrangeRed)<0)
            Print("SellStop失敗 err=",GetLastError());
      }
   }
}
//+------------------------------------------------------------------+
