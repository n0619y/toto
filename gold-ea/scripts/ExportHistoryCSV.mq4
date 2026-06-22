//+------------------------------------------------------------------+
//|                                            ExportHistoryCSV.mq4   |
//|  チャートに表示中の銘柄・時間足のヒストリカルデータをCSV出力する  |
//|  ※ EAではなく「スクリプト」。GOLDチャートにドラッグして実行。     |
//|                                                                  |
//|  出力先: MQL4/Files/<銘柄>_<分>min_export.csv                    |
//|  サーバー時間とGMTオフセットも記録し、分析時の時差問題を解消する  |
//+------------------------------------------------------------------+
#property strict
#property show_inputs

input int ExportBars = 0;   // 出力する本数 (0 = 利用可能な全本数)

void OnStart()
{
   string sym   = Symbol();
   int    tfMin  = Period();           // 時間足(分)
   int    total = Bars;
   int    n     = (ExportBars > 0 && ExportBars < total) ? ExportBars : total;

   string fname = StringConcatenate(sym, "_", tfMin, "min_export.csv");
   int fh = FileOpen(fname, FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(fh == INVALID_HANDLE)
   {
      Print("FileOpen 失敗 err=", GetLastError());
      return;
   }

   // 1行目: メタ情報(タイムゾーン較正用) — 分析側でこの行を読んで時差を補正する
   int gmtOffsetHours = (int)((TimeCurrent() - TimeGMT()) / 3600);
   FileWrite(fh, "#META", "symbol=" + sym, "tf_min=" + IntegerToString(tfMin),
                 "digits=" + IntegerToString(Digits),
                 "server_gmt_offset_hours=" + IntegerToString(gmtOffsetHours),
                 "exported_server_time=" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES));

   // 2行目: ヘッダ
   FileWrite(fh, "DateTime", "Open", "High", "Low", "Close", "Volume");

   // 古い→新しい順に出力 (i=n-1 が最古, i=0 が最新)
   for(int i = n - 1; i >= 0; i--)
   {
      FileWrite(fh,
                TimeToStr(Time[i], TIME_DATE|TIME_MINUTES),
                DoubleToStr(Open[i],  Digits),
                DoubleToStr(High[i],  Digits),
                DoubleToStr(Low[i],   Digits),
                DoubleToStr(Close[i], Digits),
                (long)Volume[i]);
   }
   FileClose(fh);

   PrintFormat("[Export完了] %d本 %s TF=%d分 → MQL4/Files/%s", n, sym, tfMin, fname);
   PrintFormat("サーバー時間=%s / GMT=%s / オフセット=%d時間",
               TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES),
               TimeToStr(TimeGMT(), TIME_DATE|TIME_MINUTES), gmtOffsetHours);
   Alert("Export完了: MQL4/Files/", fname, " (", n, "本)");
}
//+------------------------------------------------------------------+
