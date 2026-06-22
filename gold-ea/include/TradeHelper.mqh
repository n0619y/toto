//+------------------------------------------------------------------+
//|                                                 TradeHelper.mqh   |
//|  発注・決済・建値撤退・トレーリングの補助関数                    |
//+------------------------------------------------------------------+
#property strict

//+------------------------------------------------------------------+
//| 指定マジックの自EAポジション数を数える                          |
//+------------------------------------------------------------------+
int CountMyOrders(string sym, int magic)
{
   int cnt = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() == sym && OrderMagicNumber() == magic)
         if(OrderType() == OP_BUY || OrderType() == OP_SELL)
            cnt++;
   }
   return(cnt);
}

//+------------------------------------------------------------------+
//| 成行発注。SL/TPは価格差(ポイントではなく価格)で受け取る          |
//|  type : OP_BUY / OP_SELL                                         |
//+------------------------------------------------------------------+
bool OpenTrade(string sym, int type, double lots, double slDist, double tpDist,
               int magic, int slippage, string comment)
{
   if(lots <= 0.0) { Print("OpenTrade: lots<=0, skip"); return(false); }

   double price = (type == OP_BUY) ? MarketInfo(sym, MODE_ASK)
                                    : MarketInfo(sym, MODE_BID);
   int    digits = (int)MarketInfo(sym, MODE_DIGITS);
   double sl = 0.0, tp = 0.0;

   if(type == OP_BUY)
   {
      if(slDist > 0) sl = NormalizeDouble(price - slDist, digits);
      if(tpDist > 0) tp = NormalizeDouble(price + tpDist, digits);
   }
   else
   {
      if(slDist > 0) sl = NormalizeDouble(price + slDist, digits);
      if(tpDist > 0) tp = NormalizeDouble(price - tpDist, digits);
   }

   int ticket = OrderSend(sym, type, lots, NormalizeDouble(price, digits),
                          slippage, sl, tp, comment, magic, 0, clrNONE);
   if(ticket < 0)
   {
      Print("OrderSend failed err=", GetLastError(),
            " price=", price, " sl=", sl, " tp=", tp, " lots=", lots);
      return(false);
   }
   return(true);
}

//+------------------------------------------------------------------+
//| 自EAの全ポジションを成行決済                                    |
//+------------------------------------------------------------------+
void CloseAllMyOrders(string sym, int magic, int slippage)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != sym || OrderMagicNumber() != magic) continue;

      double price = 0.0;
      if(OrderType() == OP_BUY)       price = MarketInfo(sym, MODE_BID);
      else if(OrderType() == OP_SELL) price = MarketInfo(sym, MODE_ASK);
      else continue;

      if(!OrderClose(OrderTicket(), OrderLots(), price, slippage, clrNONE))
         Print("OrderClose failed err=", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| 建値撤退(ブレイクイーブン): 含み益が triggerDist 以上でSLを建値へ |
//+------------------------------------------------------------------+
void ApplyBreakEven(string sym, int magic, double triggerDist, double lockDist)
{
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != sym || OrderMagicNumber() != magic) continue;

      if(OrderType() == OP_BUY)
      {
         double bid = MarketInfo(sym, MODE_BID);
         if(bid - OrderOpenPrice() >= triggerDist)
         {
            double newSL = NormalizeDouble(OrderOpenPrice() + lockDist, digits);
            if(OrderStopLoss() < newSL)
               if(!OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0, clrNONE))
                  Print("BE modify failed err=", GetLastError());
         }
      }
      else if(OrderType() == OP_SELL)
      {
         double ask = MarketInfo(sym, MODE_ASK);
         if(OrderOpenPrice() - ask >= triggerDist)
         {
            double newSL = NormalizeDouble(OrderOpenPrice() - lockDist, digits);
            if(OrderStopLoss() == 0.0 || OrderStopLoss() > newSL)
               if(!OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0, clrNONE))
                  Print("BE modify failed err=", GetLastError());
         }
      }
   }
}

//+------------------------------------------------------------------+
//| トレーリングストップ: 価格にtrailDist追従させてSLを引き上げる    |
//+------------------------------------------------------------------+
void ApplyTrailing(string sym, int magic, double trailDist)
{
   if(trailDist <= 0) return;
   int digits = (int)MarketInfo(sym, MODE_DIGITS);
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != sym || OrderMagicNumber() != magic) continue;

      if(OrderType() == OP_BUY)
      {
         double bid   = MarketInfo(sym, MODE_BID);
         double newSL = NormalizeDouble(bid - trailDist, digits);
         if(newSL > OrderOpenPrice() && newSL > OrderStopLoss())
            if(!OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0, clrNONE))
               Print("Trail modify failed err=", GetLastError());
      }
      else if(OrderType() == OP_SELL)
      {
         double ask   = MarketInfo(sym, MODE_ASK);
         double newSL = NormalizeDouble(ask + trailDist, digits);
         if(newSL < OrderOpenPrice() && (OrderStopLoss() == 0.0 || newSL < OrderStopLoss()))
            if(!OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0, clrNONE))
               Print("Trail modify failed err=", GetLastError());
      }
   }
}
//+------------------------------------------------------------------+
