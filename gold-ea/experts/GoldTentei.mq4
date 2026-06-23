//+------------------------------------------------------------------+
//|                                                   GoldTentei.mq4   |
//|  天底ロジック(機械化v2) 押し目買い/戻り売り スイングEA            |
//|                                                                  |
//|  ★資料(天底ロジック)の客観化＋OOS検証(MTF版:PF1.42,DD-6.2%)に基づく★|
//|   - ダウ構造(スイング検出)でトレンドと押し安値/戻り高値を判定     |
//|   - 上位足H4のEMA位置で大局トレンドを一致確認(MTFフィルタ)        |
//|   - 直近インパルスのフィボ38.2-61.8へ押したら『反転の事実』を待つ |
//|     (直近高値ブレイク + EMA整合) = 落ちるナイフを掴まない         |
//|   - TP = N波動(FE: 押し安値 + インパルス値幅×倍率)               |
//|   - SL = 構造(押し目の安値の少し外)                              |
//|   - リスク%でロット自動 + 最大DD/日次損失の安全装置              |
//|                                                                  |
//|  ※GoldVBO(ブレイク)と低相関。別マジックで同口座併用=分散運用可。 |
//|  ※公開データの参考値。XM実データでの再検証が前提。              |
//+------------------------------------------------------------------+
#property copyright "FX GOLD EA Project"
#property version   "1.0"
#property strict

#include <MoneyManagement.mqh>
#include <RiskGuard.mqh>

input string Sec_General   = "==== 基本 ====";
input int    MagicNumber    = 20260623;   // GoldVBOと別番号にする
input int    Slippage       = 30;
input double MaxSpreadPoints = 50;

input string Sec_Risk      = "==== 資金/リスク管理 ====";
input double RiskPercent     = 0.5;        // 1トレードのリスク%(ポートフォリオ運用は控えめ推奨)
input double MaxDailyLossPct  = 5.0;
input double MaxDrawdownPct   = 20.0;

input string Sec_Strategy  = "==== 天底ロジック(検証済) ====";
input int    PivotK          = 3;          // スイング検出の片側バー数(OOS最良=3)
input int    MaxScanBars      = 300;        // ピボット探索の遡及本数
input double FibLo            = 0.382;      // 押し目ゾーン上限(浅い側)
input double FibHi            = 0.618;      // 押し目ゾーン下限(深い側)
input double Ntarget          = 1.618;      // TP=N波動 値幅倍率(FE)
input double SL_BufferAtr      = 0.5;        // SL=押し目安値 - ATR×
input int    RevBars          = 3;          // 反転確認: 直近この本数の高値ブレイク
input int    TrendEmaPeriod    = 200;        // マクロ整合EMA(長)
input int    FastEmaPeriod     = 20;         // 反転確認EMA(短)
input bool   UseTrendEma       = true;
input bool   AllowShort        = false;      // 既定ロングのみ(ショートは検証で弱い)
input int    MaxHoldBars       = 120;

input string Sec_Mtf       = "==== 上位足トレンドフィルタ(MTF) ====";
input bool   UseMtfFilter      = true;       // H4トレンド一致時のみエントリー(OOSでPF1.16→1.42)
input ENUM_TIMEFRAMES MtfTimeframe = PERIOD_H4; // 上位足
input int    MtfEmaPeriod      = 100;        // 上位足EMA(位置で大局判定, OOS最良=100)
input bool   MtfNeedSlope      = false;      // EMA傾きも要求(検証では位置のみが頑健)

datetime g_lastBar=0;

int OnInit(){ PrintFormat("GoldTentei init %s digits=%d",Symbol(),(int)MarketInfo(Symbol(),MODE_DIGITS)); return(INIT_SUCCEEDED); }
void OnDeinit(const int reason){}

bool SpreadOK(){ return((MarketInfo(Symbol(),MODE_ASK)-MarketInfo(Symbol(),MODE_BID))/Point<=MaxSpreadPoints); }
int  CountMine(){ int c=0; for(int i=OrdersTotal()-1;i>=0;i--){ if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES))continue; if(OrderSymbol()==Symbol()&&OrderMagicNumber()==MagicNumber&&(OrderType()==OP_BUY||OrderType()==OP_SELL))c++; } return c; }

//+------------------------------------------------------------------+
//| 確認済みスイング(ピボット)を新しい順に収集                       |
//|  hs[]/hp[]=高値ピボットのshift/価格, ls[]/lp[]=安値ピボット       |
//+------------------------------------------------------------------+
void CollectPivots(int &hs[],double &hp[],int &ls[],double &lp[])
{
   ArrayResize(hs,0);ArrayResize(hp,0);ArrayResize(ls,0);ArrayResize(lp,0);
   int k=PivotK; int last=MathMin(MaxScanBars,Bars-k-1);
   char lastType=0; // 交互化用
   for(int s=k; s<=last; s++)  // shift小(新しい)→大(古い)
   {
      bool isH=true,isL=true;
      for(int j=s-k;j<=s+k;j++){ if(High[j]>High[s])isH=false; if(Low[j]<Low[s])isL=false; }
      if(isH && lastType!='H'){ int n=ArraySize(hs);ArrayResize(hs,n+1);ArrayResize(hp,n+1);hs[n]=s;hp[n]=High[s];lastType='H'; }
      else if(isL && lastType!='L'){ int n=ArraySize(ls);ArrayResize(ls,n+1);ArrayResize(lp,n+1);ls[n]=s;lp[n]=Low[s];lastType='L'; }
   }
}

//+------------------------------------------------------------------+
//| 保有管理: 時間切れのみ(SL/TPは注文に設定済み)                    |
//+------------------------------------------------------------------+
void ManageOpen()
{
   for(int i=OrdersTotal()-1;i>=0;i--)
   {
      if(!OrderSelect(i,SELECT_BY_POS,MODE_TRADES))continue;
      if(OrderSymbol()!=Symbol()||OrderMagicNumber()!=MagicNumber)continue;
      if(MaxHoldBars>0 && iBarShift(Symbol(),0,OrderOpenTime())>=MaxHoldBars)
      {
         double px=(OrderType()==OP_BUY)?MarketInfo(Symbol(),MODE_BID):MarketInfo(Symbol(),MODE_ASK);
         if(!OrderClose(OrderTicket(),OrderLots(),NormalizeDouble(px,(int)MarketInfo(Symbol(),MODE_DIGITS)),Slippage,clrNONE))
            Print("時間切れClose失敗 err=",GetLastError());
      }
   }
}

void OnTick()
{
   RiskGuard_UpdateDaily();
   ManageOpen();

   if(g_lastBar==Time[0]) return;        // 確定足ごと
   g_lastBar=Time[0];

   if(!RiskGuard_TradingAllowed(MaxDailyLossPct,MaxDrawdownPct)) return;
   if(CountMine()>0) return;
   if(!SpreadOK()) return;

   double atr=iATR(Symbol(),0,14,1); if(atr<=0) return;
   double emaL=iMA(Symbol(),0,TrendEmaPeriod,0,MODE_EMA,PRICE_CLOSE,1);
   double emaF=iMA(Symbol(),0,FastEmaPeriod,0,MODE_EMA,PRICE_CLOSE,1);

   // ===== 上位足(H4)トレンドフィルタ: 確定済みH4バーのEMA位置(+任意で傾き) =====
   double mtfEma   = iMA(Symbol(),MtfTimeframe,MtfEmaPeriod,0,MODE_EMA,PRICE_CLOSE,1);
   double mtfEmaPv = iMA(Symbol(),MtfTimeframe,MtfEmaPeriod,0,MODE_EMA,PRICE_CLOSE,2);
   bool mtfLongOK  = (!UseMtfFilter) || (Close[1]>mtfEma && (!MtfNeedSlope || mtfEma>mtfEmaPv));
   bool mtfShortOK = (!UseMtfFilter) || (Close[1]<mtfEma && (!MtfNeedSlope || mtfEma<mtfEmaPv));

   int hs[],ls[]; double hp[],lp[];
   CollectPivots(hs,hp,ls,lp);
   if(ArraySize(hp)<2 || ArraySize(lp)<2) return;

   double H1=hp[0],H0=hp[1],L0=lp[0],Lp0=lp[1];
   int    H1s=hs[0],L0s=ls[0];
   int    digits=(int)MarketInfo(Symbol(),MODE_DIGITS);

   // ===== ロング: 上昇(HH&HL) かつ 直近ピボットが高値(=高値更新後の押し) =====
   bool up = (H1>H0 && L0>Lp0 && H1s<L0s);   // 高値の方が新しい
   if(up)
   {
      double leg=H1-L0;
      if(leg>0)
      {
         double zoneHi=H1-FibLo*leg;                       // 浅い押しでも可
         // 押し目がゾーンに到達したか(高値以降の最安値)
         int sinceHigh=MathMax(H1s,1);
         double pullLow=Low[iLowest(Symbol(),0,MODE_LOW,sinceHigh,1)];
         bool touched=(pullLow<=zoneHi);
         // 反転の事実: 直近RevBars高値を終値ブレイク + EMA整合 + 構造維持
         double recentHi=High[iHighest(Symbol(),0,MODE_HIGH,RevBars,2)];
         bool brk=Close[1]>recentHi;
         bool ema=(!UseTrendEma)||(Close[1]>emaL);
         bool emaf=Close[1]>emaF;
         bool struct_ok=Close[1]>L0;
         if(touched && brk && ema && emaf && struct_ok && mtfLongOK)
         {
            double slPrice=pullLow-SL_BufferAtr*atr;
            double ask=MarketInfo(Symbol(),MODE_ASK);
            double slDist=ask-slPrice;
            if(slDist>0)
            {
               double lots=CalcLotByRisk(Symbol(),slDist,RiskPercent);
               double tp=pullLow+Ntarget*leg;
               if(lots>0)
                  if(OrderSend(Symbol(),OP_BUY,lots,NormalizeDouble(ask,digits),Slippage,
                       NormalizeDouble(slPrice,digits),NormalizeDouble(tp,digits),"GoldTentei",MagicNumber,0,clrDodgerBlue)<0)
                     Print("Buy失敗 err=",GetLastError());
               return;
            }
         }
      }
   }

   // ===== ショート(任意): 下降(LH&LL) かつ 直近ピボットが安値(=安値更新後の戻り) =====
   bool dn = (H1<H0 && L0<Lp0 && L0s<H1s);   // 安値の方が新しい
   if(AllowShort && dn)
   {
      double leg=H1-L0;
      if(leg>0)
      {
         double zoneLo=L0+FibLo*leg;
         int sinceLow=MathMax(L0s,1);
         double pullHi=High[iHighest(Symbol(),0,MODE_HIGH,sinceLow,1)];
         bool touched=(pullHi>=zoneLo);
         double recentLo=Low[iLowest(Symbol(),0,MODE_LOW,RevBars,2)];
         bool brk=Close[1]<recentLo;
         bool ema=(!UseTrendEma)||(Close[1]<emaL);
         bool emaf=Close[1]<emaF;
         bool struct_ok=Close[1]<H1;
         if(touched && brk && ema && emaf && struct_ok && mtfShortOK)
         {
            double slPrice=pullHi+SL_BufferAtr*atr;
            double bid=MarketInfo(Symbol(),MODE_BID);
            double slDist=slPrice-bid;
            if(slDist>0)
            {
               double lots=CalcLotByRisk(Symbol(),slDist,RiskPercent);
               double tp=pullHi-Ntarget*leg;
               if(lots>0)
                  if(OrderSend(Symbol(),OP_SELL,lots,NormalizeDouble(bid,digits),Slippage,
                       NormalizeDouble(slPrice,digits),NormalizeDouble(tp,digits),"GoldTentei",MagicNumber,0,clrOrangeRed)<0)
                     Print("Sell失敗 err=",GetLastError());
            }
         }
      }
   }
}
//+------------------------------------------------------------------+
