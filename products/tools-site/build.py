"""静的サイトを public/ に生成する。  使い方: python build.py

site.json を書き換えて再実行すると、サイト名・URL・広告IDが全ページに反映される。
url にパスがあれば（例: https://n0619y.github.io/toto）、内部リンクとファイルの参照はその階層（/toto）つきで出す。
python build.py --check は、公開前に直すべき項目を一覧表示する（生成はしない。警告だけで、エラーでは止めない）。
"""

import html
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).parent
SITE = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
OUT = ROOT / "public"
BASE = str(SITE["url"]).strip().rstrip("/")   # 公開URL。canonical・og:url・sitemap・構造化データはすべてここから作る
# 置き場所の階層（ベースパス）。url のパス部分から決める: https://n0619y.github.io/toto → "/toto"、https://example.com → ""（ドメイン直下）。
# HTML の中では内部リンクや CSS・JS・画像を href="/..." / src="/..." と書いておき、page() が最後にまとめてベースパスを前に付ける（with_base_path）。
BASE_PATH = urlsplit(BASE).path.rstrip("/")
DEFAULT_URL = "https://example.com"           # site.json の初期値。このままなら --check が警告する
DEFAULT_OPERATOR = "くらしの計算機 運営"
OG_IMAGE = str(SITE.get("og_image", "")).strip()   # SNS で共有されたときの画像。https:// のURLか、src/ に置いたファイル名。空なら og:image を出さない
OG_IMAGE_URL = OG_IMAGE if OG_IMAGE.startswith(("https://", "http://")) else (f"{BASE}/{OG_IMAGE.lstrip('/')}" if OG_IMAGE else "")
# theme-color と favicon の色は style.css の変数から取る（1つ目がライト、2つ目がダーク）
_CSS = (ROOT / "src" / "style.css").read_text(encoding="utf-8")
THEME_LIGHT, THEME_DARK = re.findall(r"--bg:(#[0-9a-fA-F]{3,8})", _CSS)[:2]
ACCENT = re.search(r"--acc:(#[0-9a-fA-F]{3,8})", _CSS).group(1)

ERA_OPTS = "".join(f"<option>{e}</option>" for e in ("令和", "平成", "昭和", "大正", "明治"))

def _n(id_, label, value="", mode="decimal", lo=' min="0"'):
    """数値入力欄。負の数を許す欄は lo="" を渡す。"""
    v = f' value="{value}"' if value != "" else ""
    return f'<label>{label}<input id="{id_}" type="number" inputmode="{mode}"{lo} step="any"{v}></label>'


# PSA系ツールの初期値（一例）。解説記事の計算例もこの数字から作るので、ツールと記事がずれない。
DEF = {"feeUsd": 79.99, "fx": 155, "shipOut": 7700, "shipBack": 69.99, "cards": 20, "duty": 30, "taxRate": 10, "misc": 150,
       "p10": 50, "p9": 40, "pLow": 10, "target": 20}

PSA_SALE = f"""<p class="lead">鑑定後の売値と、そのグレードになる確率（合計100%）</p>
<div class="row">{_n("v10", "PSA10の売値（円）")}{_n("p10", "PSA10の確率（%）", DEF["p10"])}</div>
<div class="row">{_n("v9", "PSA9の売値（円）")}{_n("p9", "PSA9の確率（%）", DEF["p9"])}</div>
<div class="row">{_n("vLow", "それ以下の売値（円）")}{_n("pLow", "それ以下の確率（%）", DEF["pLow"])}</div>"""
PSA_COST = f"""<p class="lead">鑑定にかかる費用（初期値は一例です。実際の料金は各自でご確認ください）</p>
<div class="row">{_n("feeUsd", "鑑定料（USD/枚）", DEF["feeUsd"])}{_n("fx", "為替（円/ドル）", DEF["fx"])}</div>
<div class="row">{_n("shipOut", "往路送料（円/箱）", DEF["shipOut"])}{_n("shipBack", "復路送料（USD/箱）", DEF["shipBack"])}</div>
<div class="row">{_n("cards", "1箱の枚数", DEF["cards"], "numeric")}{_n("duty", "米国関税（USD/箱）", DEF["duty"])}</div>
<div class="row">{_n("taxRate", "輸入時の税率（%）", DEF["taxRate"])}{_n("misc", "諸経費（円/枚）", DEF["misc"])}</div>"""
PSA_NOTE = ("費用は1枚あたりに直して合計します。鑑定料＝鑑定料(USD)×為替、往路送料＝往路送料÷1箱の枚数、復路送料＝復路送料(USD)×為替÷1箱の枚数、"
            "輸入時の税＝(鑑定料＋復路送料)×税率、米国関税＝関税(USD)×為替÷1箱の枚数、これに諸経費（スリーブ・梱包材・国内の発送費など）を足します。\n"
            "期待売値は「各グレードの売値×そのグレードになる確率」の合計です。売値には、販売手数料や送料を引いたあとの手取り額、または買取店の買取価格を入れてください。\n"
            "初期値は一例です。鑑定料・送料・関税・税率はプランや時期、申込方法（直接か代行か）で変わるため、必ずご自身で最新の料金を確認して書き換えてください。"
            "グレードの確率はカードの状態で大きく変わり、このツールが予測するものではありません。\n"
            "結果は入力した数字をそのまま計算した参考値で、利益を保証するものではありません。入力内容は外部に送信されません。")

CARD_TOOLS = [
    ("psa-profit", "PSA鑑定 損益シミュレーター", "トレカをPSA鑑定に出したときの1枚あたりの費用・期待利益・利益率・損益分岐の仕入れ値を計算します。PSA10・PSA9になった場合の損益も表示。",
     f"""{_n("buy", "仕入れ値（円）", "", "numeric")}
{PSA_SALE}
{PSA_COST}""",
     "仕入れたカードをPSA鑑定に出して売ると、期待値でいくら残るかを計算します。期待利益＝期待売値−費用の合計−仕入れ値です。"
     "利益率は「仕入れ値に対して」と「仕入れ値＋費用に対して」の2通りを表示します。損益分岐の仕入れ値は、期待利益がちょうど0円になる仕入れ値です。\n"
     "「PSA10だった場合」「PSA9だった場合」「それ以下だった場合」は、そのグレードの売値から費用の合計と仕入れ値を引いた額です。期待値がプラスでも、PSA9以下では赤字になることがよくあります。\n"
     + PSA_NOTE),
    ("psa-max-buy", "PSA鑑定 仕入れ上限 逆算", "PSA鑑定の費用と目標利益率から「この値段までなら仕入れてよい」上限額を逆算します。",
     f"""{_n("target", "目標利益率（%・仕入れ値に対して）", DEF["target"])}
{PSA_SALE}
{PSA_COST}""",
     "仕入れ上限＝(期待売値−費用の合計)÷(1＋目標利益率)です。この金額で仕入れると、期待利益が仕入れ値のちょうど目標利益率ぶんになります。"
     "表示は100円単位に切り下げた額と、切り下げ前の額（1円未満切り捨て）の両方です。目標利益率を0%にすると損益分岐の仕入れ値になります。\n"
     + PSA_NOTE),
    ("grading-fee", "鑑定料の円換算", "ドル建ての鑑定料を、枚数・為替・送料から1枚あたりと合計の円額に換算します。",
     f"""<div class="row">{_n("count", "枚数", DEF["cards"], "numeric")}{_n("unitUsd", "鑑定料の単価（USD/枚）", DEF["feeUsd"])}</div>
{_n("fx", "為替（円/ドル）", DEF["fx"])}
<div class="row">{_n("shipOut", "往路送料の合計（円）", 0)}{_n("shipBack", "復路送料の合計（USD）", 0)}</div>""",
     "合計＝枚数×単価(USD)×為替＋往路送料(円)＋復路送料(USD)×為替。送料は枚数で均等に割って1枚あたりに按分します。\n"
     "初期値は一例です。鑑定料はプランや申告価格で変わり、為替も日々動きます。実際の料金と、カード会社などが適用する換算レートはご自身で確認してください。"
     "関税や輸入時の税は含めていません。それらも含めた損益は「PSA鑑定 損益シミュレーター」で計算できます。"),
    ("card-roi", "トレカ売買の利益率計算", "仕入れ値・売値・販売手数料率・送料から、利益・利益率・損益分岐の売値を計算します。フリマやオークションでの転売に。",
     f"""<div class="row">{_n("buy", "仕入れ値（円）", "", "numeric")}{_n("sell", "売値（円）", "", "numeric")}</div>
<div class="row">{_n("fee", "販売手数料率（%）", 10)}{_n("ship", "送料（円）", 0, "numeric")}</div>""",
     "利益＝売値−販売手数料−送料−仕入れ値、販売手数料＝売値×手数料率です。利益率は「売値に対して」と「仕入れ値に対して」の2通りを表示します。"
     "損益分岐の売値は、利益が0円以上になる最低の売値（(仕入れ値＋送料)÷(1−手数料率)を1円単位に切り上げ）です。\n"
     "手数料率の初期値10%は一例です。手数料率や1円未満の端数処理は販売先によって異なるため、実際の額と数円ずれることがあります。振込手数料などは送料の欄に足して計算してください。"),
    ("furima-vs-kaitori", "フリマと買取の手取り比較", "同じカードをフリマで売った場合と買取に出した場合の手取りを比べ、差額と、手取りが同じになる買取率を計算します。",
     f"""{_n("price", "相場価格（円）", "", "numeric")}
<p class="lead">フリマで売る場合（初期値は一例です）</p>
<div class="row">{_n("fee", "販売手数料率（%）", 10)}{_n("fship", "送料（円）", 210, "numeric")}</div>
<p class="lead">買取に出す場合（初期値は一例です）</p>
{_n("rate", "買取率（%・相場に対して）", 93)}
<div class="row">{_n("kship", "売り手負担の送料（円）", 0, "numeric")}{_n("kfee", "売り手負担の振込手数料（円）", 0, "numeric")}</div>""",
     "フリマの手取り＝相場価格−販売手数料−送料、買取の手取り＝買取額−売り手が負担する送料−売り手が負担する振込手数料です。"
     "販売手数料＝相場価格×手数料率、買取額＝相場価格×買取率で、どちらも1円未満を切り捨てます。差額は「買取の手取り−フリマの手取り」で、プラスなら買取のほうが多くなります。\n"
     "手取りが同じになる買取率＝(フリマの手取り＋売り手が負担する送料＋振込手数料)÷相場価格です（端数処理前の値を小数第2位で四捨五入）。買取率がこれより高ければ、買取のほうが手取りが多くなります。\n"
     "手数料率・送料・買取率・振込手数料は、サービスや発送方法、店によって違います。初期値は一例なので、必ずご自身の条件に書き換えてください。1円未満の端数処理もサービスによって異なり、実際の額と数円ずれることがあります。\n"
     "フリマでは相場価格どおりに売れるものとして計算しています。売れるまでの日数、値下げ、梱包材の費用、売上金を引き出すときの手数料、査定で減額される場合は含めていません。"
     "このツールは入力した数字を比べるだけで、特定のサービスや店を勧めるものではありません。金額は円の整数で、率は小数第4位まで入力できます。入力内容は外部に送信されません。"),
]

LIFE_TOOLS = [    ("wareki", "和暦・西暦 変換", "西暦から和暦、和暦から西暦へすぐ変換。改元のあった年や干支も表示します。",
     f"""<label>西暦<input id="seireki" type="number" inputmode="numeric"></label>
<p class="lead">または和暦から</p>
<div class="row"><label>元号<select id="era">{ERA_OPTS}</select></label>
<label>年<input id="eraYear" type="number" inputmode="numeric" min="1" placeholder="例: 8"></label></div>""",
     "明治は太陽暦が採用された1873年（明治6年）以降に対応しています。改元のあった年は、改元前後の両方の元号を表示します。"),
    ("age", "年齢計算", "生年月日から満年齢・数え年・干支・生まれてからの日数を計算します。",
     """<label>生年月日<input id="birth" type="date"></label>
<label>基準日<input id="on" type="date"></label>""",
     "満年齢は誕生日を迎えた回数、数え年は生まれた年を1歳として元日に1歳加える数え方です。"),
    ("school", "入学・卒業年 早見", "生年月日から小学校〜大学の入学年・卒業年を一覧にします。履歴書の作成に。",
     """<label>生年月日<input id="birth" type="date"></label>""",
     "4月2日から翌年4月1日生まれが同じ学年になります。浪人・留年・休学がない場合の年です。大学は4年制で計算しています。"),
    ("days", "日数計算", "2つの日付の間の日数や、◯日後の日付と曜日を計算します。",
     """<label>開始日<input id="from" type="date"></label>
<label>終了日<input id="to" type="date"></label>
<label>または 開始日から◯日後<input id="n" type="number" inputmode="numeric" placeholder="例: 100"></label>""",
     "「初日を含む」は開始日を1日目として数える方法です。終了日が開始日より前のときは「◯日前」と表示し、週への換算は日数の絶対値で行います。「◯日後」にマイナスの整数を入れると◯日前の日付を計算できます。"),
    ("count", "文字数カウント", "入力した文章の文字数・空白を除いた文字数・行数・原稿用紙換算をその場で数えます。",
     """<label>文章<textarea id="text" placeholder="ここに入力または貼り付け"></textarea></label>""",
     "入力した文章は外部に送信されず、お使いのブラウザの中だけで数えます。絵文字なども1文字として数えます。"),
    ("warikan", "割り勘計算", "合計金額と人数から1人あたりの金額を計算。100円・500円単位の切り上げにも対応。",
     """<label>合計金額（円）<input id="total" type="number" inputmode="numeric" min="0"></label>
<div class="row"><label>人数<input id="people" type="number" inputmode="numeric" value="2" min="1"></label>
<label>切り上げ単位<select id="unit"><option value="1">1円</option><option value="10">10円</option><option value="100" selected>100円</option><option value="500">500円</option><option value="1000">1000円</option></select></label></div>""",
     "指定した単位で切り上げるため、集めた金額が合計を上回ります。その差額を「おつり」として表示します。"),
    ("tax", "消費税計算", "税抜から税込、税込から税抜を計算。8%・10%と端数処理を選べます。",
     """<label>金額（円）<input id="price" type="number" inputmode="numeric" min="0"></label>
<div class="row"><label>入力額<select id="dir"><option value="net">税抜</option><option value="gross">税込</option></select></label>
<label>税率<select id="rate"><option value="10">10%</option><option value="8">8%（軽減税率）</option></select></label>
<label>端数<select id="mode"><option value="floor">切り捨て</option><option value="round">四捨五入</option><option value="ceil">切り上げ</option></select></label></div>""",
     "消費税の1円未満の端数処理は事業者が決められます。多くの店舗では切り捨てです。"),
    ("discount", "割引・ポイント還元 計算", "◯%オフの支払額と、ポイント還元を含めた実質価格を計算します。",
     """<label>元の価格（円）<input id="price" type="number" inputmode="numeric" min="0"></label>
<div class="row"><label>割引率（%）<input id="off" type="number" inputmode="decimal" value="0" min="0" max="100" step="any"></label>
<label>ポイント還元率（%）<input id="point" type="number" inputmode="decimal" value="0" min="0" max="100" step="any"></label></div>""",
     "ポイントは割引後の支払額に対して付く前提で、1円未満・1ポイント未満は切り捨てています。"),
    ("unit", "単位変換", "坪と平方メートル、インチとセンチ、合とミリリットルなど、暮らしでよく使う単位を変換します。",
     """<label>種類<select id="group"></select></label>
<label>数値<input id="value" type="number" inputmode="decimal" value="1"></label>
<div class="row"><label>変換前<select id="from"></select></label><label>変換後<select id="to"></select></label></div>""",
     "1坪は400/121㎡（約3.3058㎡）です。畳の大きさは地域や建物で異なるため目安です。"),
    ("zenhan", "全角・半角 変換", "英数字と記号の全角・半角を一括で変換します。",
     """<label>変換したい文章<textarea id="text"></textarea></label>
<div class="row"><button id="toHalf">半角にする</button><button id="toFull">全角にする</button></div>
<label>結果<textarea id="out" readonly></textarea></label><button id="copy">結果をコピー</button>""",
     "変換するのは英数字・記号・スペースです。カタカナは変換しません。文章は外部に送信されません。"),
    ("password", "パスワード生成", "安全なランダムパスワードをブラウザ内で生成します。長さと文字の種類を選べます。",
     """<label>長さ<input id="len" type="number" inputmode="numeric" value="16" min="4" max="64"></label>
<label><input id="lower" type="checkbox" checked>英小文字</label><label><input id="upper" type="checkbox" checked>英大文字</label>
<label><input id="digit" type="checkbox" checked>数字</label><label><input id="symbol" type="checkbox">記号</label>
<div class="row"><button id="gen">生成する</button><button id="copy">コピー</button></div>""",
     "パスワードはお使いのブラウザの中で生成され、外部には送信・保存されません。見間違えやすい文字（0とO、1とlなど）は除いています。"),
    ("percent", "割合（パーセント）計算", "AはBの何%か、AのB%はいくつか、AからBへの増減率を一度に計算します。",
     f"""<div class="row">{_n("a", "A", "", "decimal", "")}{_n("b", "B", "", "decimal", "")}</div>""",
     "「AはBの何%」＝A÷B×100、「AのB%」＝A×B÷100、「AからBへの増減率」＝(B−A)÷Aの絶対値×100 です。小数点以下は6桁までで四捨五入して表示します。"),
    ("time-calc", "時間の足し算・引き算", "「1:30」のような時間の合計と、開始〜終了の時間差を計算します。日付をまたぐ勤務や休憩の差し引きにも対応。",
     """<label>足したい時間（1行に1つ。引くときは先頭に - ）<textarea id="list" placeholder="1:30&#10;2:45&#10;-0:15"></textarea></label>
<p class="lead">または開始〜終了の時間差</p>
<div class="row"><label>開始<input id="start" type="time"></label><label>終了<input id="end" type="time"></label></div>
<label>休憩（分・任意）<input id="brk" type="number" inputmode="numeric" min="0" placeholder="例: 60"></label>""",
     "時間は「時:分」で入力します（分は00〜59。「100:30」のように24時間を超えてもかまいません）。終了が開始より前の時刻のときは、翌日の終了として計算します。開始と終了が同じ時刻のときは0分です。"),
    ("hourly-wage", "時給・日給・月給・年収 換算", "時給・日給・月給・年収のどれか1つから、残りを換算します。1日の労働時間と月の勤務日数を指定できます。",
     f"""<div class="row">{_n("amount", "金額（円）", "", "numeric")}
<label>金額の種類<select id="kind"><option value="hour">時給</option><option value="day">日給</option><option value="month">月給</option><option value="year">年収</option></select></label></div>
<div class="row">{_n("hours", "1日の労働時間", 8)}{_n("days", "月の勤務日数", 20)}</div>""",
     "日給＝時給×1日の労働時間、月給＝日給×月の勤務日数、年収＝月給×12 として換算した額面の目安です。税金・社会保険料・残業の割増・賞与・交通費は計算に含めていません。1円未満は四捨五入して表示します。"),
    ("random", "乱数・抽選", "指定した範囲から重複なしで数字を選んだり、名前のリストから当選者を選んだりできます。",
     f"""<div class="row">{_n("min", "最小", 1, "numeric", "")}{_n("max", "最大", 100, "numeric", "")}{_n("n", "個数", 1, "numeric")}</div>
<label><input id="sort" type="checkbox">小さい順に並べる</label>
<button id="draw">数字を選ぶ</button>
<p class="lead">またはリストから選ぶ</p>
<label>リスト（1行に1件）<textarea id="list" placeholder="佐藤&#10;鈴木&#10;高橋"></textarea></label>
<label>選ぶ数<input id="k" type="number" inputmode="numeric" value="1" min="1"></label>
<button id="pick">リストから選ぶ</button>""",
     "ブラウザの暗号用乱数（crypto.getRandomValues）を使い、どの数字・どの行も同じ確率で選ばれます。同じものが2回選ばれることはありません。結果は引いた順に表示します。"
     "リストに同じ名前が2行あるときは別々の候補として扱います。入力内容と結果は外部に送信・保存されないため、ページを閉じると消えます。"),
    ("base-convert", "2進数・8進数・10進数・16進数 変換", "2進・8進・10進・16進の数を相互に変換します。桁数の多い大きな整数にも対応。",
     """<label>数値<input id="value" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="例: 255"></label>
<label>入力した数の種類<select id="from"><option value="10">10進数</option><option value="2">2進数</option><option value="8">8進数</option><option value="16">16進数</option></select></label>""",
     "整数だけに対応しています（小数は変換できません）。先頭に - を付けると負の数として、符号を付けたまま変換します（2の補数表現ではありません）。"
     "0x・0b・0o の接頭辞、桁区切りの空白や _ は無視します。4,096桁まで入力できます。"),
    ("kana", "ひらがな・カタカナ 変換", "ひらがなをカタカナに、カタカナをひらがなに一括で変換します。",
     """<label>変換したい文章<textarea id="text"></textarea></label>
<div class="row"><button id="toKata">カタカナにする</button><button id="toHira">ひらがなにする</button></div>
<label>結果<textarea id="out" readonly></textarea></label><button id="copy">結果をコピー</button>""",
     "漢字・英数字・記号・長音（ー）はそのまま残します。半角カタカナは変換しません。ヷ・ヸ・ヹ・ヺ は対応するひらがなが無いためそのままです。文章は外部に送信されません。"),
    ("aspect", "アスペクト比 計算", "幅と高さから 16:9 などの比率を求め、同じ比率のまま幅や高さを変えたときのサイズを計算します。",
     f"""<div class="row">{_n("w", "幅", 1920)}{_n("h", "高さ", 1080)}</div>
<p class="lead">同じ比率でサイズを変える（どちらか、または両方）</p>
<div class="row">{_n("newW", "新しい幅")}{_n("newH", "新しい高さ")}</div>""",
     "幅と高さがどちらも整数のとき、最大公約数で割った比率（例: 1920×1080 → 16:9）を表示します。小数を含むときは「幅÷高さ:1」の形で表示します。"
     "幅と高さの欄に 16 と 9 のように比率そのものを入れて、新しい幅から高さを求めることもできます。割り切れないときは小数第2位までと、四捨五入した整数を表示します。"),
]

TOOLS = CARD_TOOLS + LIFE_TOOLS
GROUPS = [("トレカ・PSA鑑定", CARD_TOOLS), ("くらし・仕事", LIFE_TOOLS)]

e = html.escape
AD_HEAD = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={e(SITE["adsense_client"])}" '
           'crossorigin="anonymous"></script>') if SITE["adsense_client"] else ""
AD_SLOT = ('<div class="ad"><ins class="adsbygoogle" style="display:block" data-ad-format="auto" '
           f'data-ad-client="{e(SITE["adsense_client"])}" data-full-width-responsive="true"></ins>'
           '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>') if SITE["adsense_client"] else ""

# ---- トレカ鑑定の収支管理: 解説記事と商品紹介ページ -------------------------------
# 記事は「計算の考え方」だけを書く。料金・関税・税率の実際の額や制度は書かない（変わるうえ、確認していないため）。
# 記事内の数字はすべて DEF（ツールの初期値）と EX（仮の売値）から計算する。

SHEET_NAME = "PSA鑑定 収支管理シート"
SHEET_DESC = ("トレカをPSA鑑定に出して売る個人向けの、Excel / Googleスプレッドシート用の収支管理シートの紹介です。"
              "在庫台帳・注文別集計・月次集計・仕入れ前シミュレーターが1ファイルに入っています。")
SHEET_IMAGES = ROOT.parent / "psa-sheet" / "dist" / "images"   # 読むだけ。PNG があれば縮小して public/sheet/ に出力する
SHEET_IMAGE_WIDTH = 1200   # 表示幅は最大約650px。高解像度の画面でも文字が読めるよう、その約2倍にする
SHEET_IMAGE_QUALITY = 90   # WebP の品質。80 でも読めるが、細い文字の周りのにじみが少ない 90 にしている
PRODUCT_URL = str(SITE.get("product_url", "")).strip()
PRODUCT_PRICE = str(SITE.get("product_price", "")).strip()
PRODUCT_VERIFIED = str(SITE.get("product_verified", "")).strip()
if PRODUCT_URL and not PRODUCT_URL.startswith(("https://", "http://")):
    raise SystemExit("site.json の product_url は https:// から始まるURLにしてください（販売前は空にします）")

EX = {"buy": 8000, "v10": 60000, "v9": 15000, "vLow": 5000}   # 計算例のための仮の数字（相場ではない）
TOOL_TITLE = {s: t for s, t, *_ in CARD_TOOLS}


def yen(x):
    """四捨五入して円表示。app.js の yenR（Math.round）と同じ丸め方にする（round() は .5 を偶数側に丸めるため使わない）。"""
    return f"{int((x + 0.5) // 1):,}円"


def psa_costs(d):
    """1枚あたりの費用。src/lib.js の psaCosts、pokeca/core.py の per_card_costs と同じ式。"""
    grading = d["feeUsd"] * d["fx"]
    back = d["shipBack"] * d["fx"] / d["cards"]
    c = {"grading": grading, "shipOut": d["shipOut"] / d["cards"], "shipBack": back,
         "importTax": (grading + back) * d["taxRate"] / 100, "usDuty": d["duty"] * d["fx"] / d["cards"], "misc": d["misc"]}
    c["total"] = sum(c.values())
    return c


def tool_link(slug):
    return f'<a href="/{slug}/">{e(TOOL_TITLE[slug])}</a>'


def _table(pairs):
    return "<table>" + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in pairs) + "</table>"


_C = psa_costs(DEF)
_C_HALF = psa_costs({**DEF, "cards": DEF["cards"] // 2})
_EXPECTED = (EX["v10"] * DEF["p10"] + EX["v9"] * DEF["p9"] + EX["vLow"] * DEF["pLow"]) / 100
_BREAKEVEN = _EXPECTED - _C["total"]
_MAX_EXACT = _BREAKEVEN / (1 + DEF["target"] / 100)
_MAX_BUY = max(0, _MAX_EXACT // 100 * 100)
_SPEND = EX["buy"] + _C["total"]
# シートのシミュレーターは仕入れ上限を2行で出す（費用を1円に四捨五入してから計算。販売手数料率は初期値の0%）
_SHEET_MAX_BUY = max(0, (_EXPECTED * (1 - DEF["target"] / 100) - round(_C["total"])) // 100 * 100)   # 売却額に対する利益率（利益÷売却額）
_SHEET_MAX_ON_BUY = max(0, (_EXPECTED - round(_C["total"])) / (1 + DEF["target"] / 100) // 100 * 100)  # 仕入れ値に対する利益率（ツールと同じ定義）
_EX_NOTE = "ツールの初期値と同じ数字を使った一例です。実際の料金や税率を示すものではありません。"
NO_ADVICE = "この記事は計算の考え方を説明するもので、税務・法律の助言ではありません。税や関税の扱いは、税理士・税務署・税関などにご確認ください。"

GUIDES = [
    ("grading-cost", "鑑定に出すときの1枚あたり費用の数え方",
     "鑑定料・往復送料・輸入時にかかる費用・諸経費を、1枚あたりに直して足す考え方を、計算例つきで説明します。",
     f"""<p>鑑定に出したカードがいくらで売れれば元が取れるかを考えるには、まず「1枚にいくらかかったか」を決める必要があります。
鑑定料だけを見ていると、送料などの箱単位の費用が抜けて、原価を低く見積もってしまいます。ここでは、費用を1枚あたりに直して足す考え方をまとめます。</p>
<h2>1枚ごとの費用と、箱ごとの費用を分ける</h2>
<p>鑑定にかかる費用は、かかり方で2種類に分かれます。</p>
<ul><li><b>1枚ごとにかかるもの</b>: 鑑定料、スリーブや梱包材などの諸経費</li>
<li><b>箱（1回の発送）ごとにかかるもの</b>: 行きの送料、返送の送料、通関でかかる費用</li></ul>
<p>箱ごとの費用は、その箱に入れた枚数で割って1枚あたりに直します（按分）。1枚あたりの費用は、この2種類を足したものです。</p>
<h2>ドル建ての費用は円に直してから足す</h2>
<p>鑑定料や返送の送料がドル建てのときは、為替を掛けて円に直します。試算に使う為替と、実際の請求に使われる換算レートは一致しないので、
試算では少し不利な側の数字を置き、請求額が確定したら実額に置き換えるのが安全です。</p>
<h2>輸入時にかかる費用</h2>
<p>返送されたカードを受け取るときに税がかかる場合があります。このサイトのツールでは、試算のために「（鑑定料＋返送の送料）× 税率」という形で置いています。
これは計算上の置き方で、実際に何に対してどの率でかかるのか、そもそもかかるのかは、制度・時期・申込方法（直接か代行か）によって変わります。
当サイトでは確認していないため、必ずご自身で確かめた数字を入れてください。発送先の国でかかる費用も、箱単位なら同じように枚数で割ります。かからなければ0です。</p>
<h2>一例で足してみる</h2>
<p>{_EX_NOTE}為替{DEF["fx"]}円、鑑定料{DEF["feeUsd"]}ドル/枚、行きの送料{DEF["shipOut"]:,}円/箱、返送の送料{DEF["shipBack"]}ドル/箱、
1箱{DEF["cards"]}枚、発送先の国でかかる費用{DEF["duty"]}ドル/箱、輸入時の税率{DEF["taxRate"]}%、諸経費{DEF["misc"]}円/枚の場合です。</p>
<div class="card note">{_table([
    ("鑑定料", yen(_C["grading"])), ("行きの送料（÷枚数）", yen(_C["shipOut"])), ("返送の送料（×為替÷枚数）", yen(_C["shipBack"])),
    ("輸入時の税", yen(_C["importTax"])), ("発送先の国でかかる費用（×為替÷枚数）", yen(_C["usDuty"])), ("諸経費", yen(_C["misc"])),
    ("1枚あたりの合計", yen(_C["total"]))])}</div>
<p>同じ条件で数字を変えて試すには {tool_link("psa-profit")} を、鑑定料と送料だけを円に直すには {tool_link("grading-fee")} を使えます。</p>
<h2>判断が分かれるところ</h2>
<ul><li><b>1箱の枚数</b>: 枚数が少ないほど、箱ごとの費用が1枚に重く乗ります。上の例で1箱を{DEF["cards"] // 2}枚にすると、1枚あたりの合計は{yen(_C_HALF["total"])}になります。</li>
<li><b>按分のしかた</b>: ここでは枚数で均等に割っています。高いカードに多く配分する考え方もありますが、どちらにしても、決めた方法を全部のカードで通すことが大事です。</li>
<li><b>諸経費に何を入れるか</b>: 国内の発送費や売るときの梱包材を入れるかどうかは自分で決めます。売値を「手数料を引いた手取り額」で考えるなら、同じ手数料を費用にも入れると二重になります。</li>
<li><b>代行を使う場合</b>: 代行の手数料は鑑定料か諸経費に含め、料金の仕組みが違う部分は項目を読み替えます。</li></ul>
<p>{NO_ADVICE}</p>""",
     ["psa-profit", "grading-fee"]),
    ("break-even", "損益分岐の仕入れ値と、グレードが下振れしたときの損益の見方",
     "期待売値から費用を引いて損益分岐の仕入れ値を出す考え方と、PSA9以下だった場合の損益の見方、期待値で考える意味と限界を説明します。",
     f"""<p>未鑑定のカードを「いくらまでなら仕入れてよいか」は、鑑定後の売値・費用・グレードの出方の3つで決まります。
ここでは損益分岐の仕入れ値の出し方と、その数字だけでは見えない下振れの見方を説明します。</p>
<h2>期待売値を出す</h2>
<p>鑑定結果は出してみるまで分からないので、グレードごとに「その場合の売値」と「そうなる確率」を置き、掛けて足します。これが期待売値です。
売値には、販売手数料や送料を引いたあとの手取り額を入れます。</p>
<p>仮の数字で、PSA10なら{EX["v10"]:,}円・PSA9なら{EX["v9"]:,}円・それ以下なら{EX["vLow"]:,}円、確率は{DEF["p10"]}%・{DEF["p9"]}%・{DEF["pLow"]}%（ツールの初期値）とすると、
期待売値は{yen(_EXPECTED)}です。売値は説明のために置いた一例で、相場ではありません。</p>
<h2>損益分岐の仕入れ値</h2>
<div class="card note"><p>損益分岐の仕入れ値 ＝ 期待売値 − 1枚あたりの費用</p></div>
<p>1枚あたりの費用が{yen(_C["total"])}（ツールの初期値で計算した一例。数え方は <a href="/guide/grading-cost/">1枚あたり費用の数え方</a>）なら、
損益分岐は{yen(_BREAKEVEN)}です。これより安く仕入れると、期待値のうえでは利益が残ります。</p>
<p>利益の目標があるときは、仕入れ上限 ＝（期待売値 − 費用）÷（1 ＋ 目標利益率）で逆算します。目標を仕入れ値に対して{DEF["target"]}%とすると、
上の例では{yen(_MAX_BUY)}（100円単位に切り下げ）です。利益率を「仕入れ値に対して」と「売値に対して」のどちらで考えるかで上限は変わるので、どちらかに決めて揃えます。
計算は {tool_link("psa-max-buy")} でできます。</p>
<h2>グレードが下振れしたときの損益</h2>
<p>期待値は平均の話なので、1枚ごとの結果は別に見ます。上の例のカードを{EX["buy"]:,}円で仕入れた場合です。</p>
<div class="card note">{_table([
    ("期待利益", yen(_EXPECTED - _SPEND)), ("PSA10だった場合", yen(EX["v10"] - _SPEND)),
    ("PSA9だった場合", yen(EX["v9"] - _SPEND)), ("それ以下だった場合", yen(EX["vLow"] - _SPEND))])}</div>
<p>期待利益はプラスですが、この置き方では{DEF["p9"] + DEF["pLow"]}%の確率で1枚あたり赤字になります。期待値のプラスは、PSA10の利益がそれ以外の赤字を埋めることで成り立っています。
グレード別の損益は {tool_link("psa-profit")} に表示されます。</p>
<h2>期待値で考える意味と限界</h2>
<p>似た条件の仕入れを何度も繰り返すと、平均の結果は期待値に近づいていきます。1枚ごとの当たり外れに左右されない仕入れの基準を持てるのが、期待値で考える意味です。一方で、次の限界があります。</p>
<ul><li><b>枚数が少ないうちは大きくぶれる</b>: 数枚では、全部が下のグレードになることも普通に起こります。その場合の赤字の合計に資金が耐えられるかを、期待値とは別に確かめます。</li>
<li><b>確率は自分で置いた仮定</b>: 式が予測してくれるわけではありません。カードの状態の見立てが外れれば、期待値そのものが変わります。自分の実績の割合も、枚数が少ないうちは当てになりません。</li>
<li><b>売値は動く</b>: 鑑定から返ってくるまでのあいだに相場が変わることがあります。</li>
<li><b>時間と資金の拘束は入っていない</b>: 売れるまでの期間や、そのあいだ資金が動かせないことは、この式には出てきません。</li></ul>
<p>確率や売値を悪い側にずらしても成り立つかどうかを見てから、仕入れ値を決めるのが堅実です。</p>
<p>{NO_ADVICE}</p>""",
     ["psa-profit", "psa-max-buy"]),
    ("records", "鑑定転売の記録の付け方（1枚ごとに何を残すか）",
     "カード1枚を1行で記録するときに、どの項目を残しておくと注文別・月別・グレード別に後で集計できるかを説明します。",
     """<p>鑑定に出して売るまでには数か月かかることがあり、そのあいだに仕入れ・発送・返却・売却がばらばらに起こります。
あとから「結局いくら残ったのか」を出せるかどうかは、最初にどう記録したかで決まります。ここでは、1枚ごとに残す項目と、その意味を説明します。</p>
<h2>カード1枚を1行にする</h2>
<p>鑑定結果も売値も1枚ごとに違います。まとめて買った分を1行にしてしまうと、あとで利益をカードごとに分けられません。
同じカードを複数枚持っていても、1枚ずつ別の行にします。</p>
<h2>残しておく項目</h2>
<ul><li><b>管理番号</b>: 自分で振る通し番号です。同じカードが何枚あっても区別でき、現物のスリーブなどに同じ番号を書いておけば行と結びつきます。</li>
<li><b>状態</b>: 在庫・鑑定中・返却済・売却済のように、いまどの段階にあるかを表します。売れていない分を数えるときに使います。</li>
<li><b>カード名・番号</b>: 何のカードかを表します。表記を揃えておくと、あとで探しやすくなります。</li>
<li><b>仕入日・仕入先・仕入値</b>: まとめ買いのときは、合計を1枚ずつの値段に分けます。分け方は自分で決め、同じ方法を続けます。</li>
<li><b>鑑定の注文番号</b>: どの注文（どの箱）で出したかを表します。注文ごとの収支をまとめるときの目印です。</li>
<li><b>認定番号</b>: 返ってきたケースに付く番号です。現物と行を1対1で結びます。</li>
<li><b>グレード</b>: 鑑定結果です。グレード別の枚数と割合のもとになります。</li>
<li><b>売却日・売却先・売却額</b>: 売却日は月ごとの集計の目印です。「3月ごろ」のような文字ではなく、日付として入れておきます。</li></ul>
<h2>そこから計算できるもの</h2>
<p>上の項目に1枚あたりの鑑定費用（数え方は <a href="/guide/grading-cost/">1枚あたり費用の数え方</a>）を足すと、次の数字が行ごとに出せます。</p>
<div class="card note"><p>原価合計 ＝ 仕入値 ＋ 鑑定費用<br>利益 ＝ 売却額 − 販売手数料 − 原価合計</p></div>
<p>これを注文番号でまとめれば注文ごとの収支と、まだ売れていない分の原価が分かります。売却日でまとめれば月ごとの売上・原価・利益になります。
グレードで数えれば、自分が出したカードのグレード別の割合が出ます。この割合は次の仕入れを試算するときの確率の参考になりますが、枚数が少ないうちは大きくぶれます。</p>
<h2>判断が分かれるところ</h2>
<ul><li><b>鑑定費用を試算で置くか、実額で置くか</b>: 出す前は試算の額しか分かりません。請求が確定したら実額に置き換えると、あとで為替や料金の前提を変えても過去の行が動きません。</li>
<li><b>売るときの送料の扱い</b>: 売却額から引いて入れるか、別の列に分けるかです。どちらでもかまいませんが、途中で変えると月ごとの比較ができなくなります。</li>
<li><b>利益率の分母</b>: 売却額に対する割合か、仕入値に対する割合かで数字が変わります。1件の売買の2通りの利益率は __CARD_ROI__ で比べられます。</li>
<li><b>売れていない在庫</b>: 利益には入りませんが、資金はすでに出ています。利益とは別に、未売却分の原価の合計を見ておきます。</li></ul>
<p>記録をどう申告に使うかは、この記事では扱いません。__NO_ADVICE__</p>""".replace("__CARD_ROI__", tool_link("card-roi")).replace("__NO_ADVICE__", NO_ADVICE),
     ["card-roi", "psa-profit"]),
]
GUIDE_TITLE = {s: t for s, t, *_ in GUIDES}
# トレカ向けツールの各ページ下部に出す解説記事（一般向けツールには出さない）
TOOL_GUIDES = {"psa-profit": ["break-even", "grading-cost", "records"], "psa-max-buy": ["break-even", "grading-cost"],
               "grading-fee": ["grading-cost", "records"], "card-roi": ["records", "break-even"],
               "furima-vs-kaitori": ["records"]}
SHEET_LI = f'<li><a href="/sheet/"><b>{e(SHEET_NAME)}（商品紹介）</b><span>在庫台帳・注文別集計・月次集計・シミュレーターが入った、Excel / Googleスプレッドシート用のシートです。</span></a></li>'


def guide_items(slugs):
    desc = {s: d for s, _, d, *_ in GUIDES}
    return "".join(f'<li><a href="/guide/{s}/"><b>{e(GUIDE_TITLE[s])}</b><span>{e(desc[s])}</span></a></li>' for s in slugs)


def tool_items(slugs):
    desc = {s: d for s, _, d, *_ in CARD_TOOLS}
    return "".join(f'<li><a href="/{s}/"><b>{e(TOOL_TITLE[s])}</b><span>{e(desc[s])}</span></a></li>' for s in slugs)


def card_pillar(slugs):
    """トレカ向けツールの下部と、トップの「トレカ・PSA鑑定」に置く導線。"""
    return f'<ul class="tools">{guide_items(slugs)}{SHEET_LI}</ul>'


SHEET_SHOTS = {  # ファイル名 → 説明（alt とキャプション）。ここに無い PNG は汎用の説明で表示する
    "01-cover.png": "PSA鑑定 収支管理シートの表紙画像。在庫台帳の一部の列を抜粋したもの",
    "02-ledger.png": "在庫台帳シートの画面",
    "03-monthly.png": "月次集計シートの画面",
    "04-simulator.png": "シミュレーターシートの画面",
    "05-howto.png": "使い方の説明画像",
}
SHEET_FAQ = [
    ("Excel で開いたら、数字が出ず空欄に見えます。",
     "画面上部に「保護ビュー」の黄色い帯が出ていたら、「編集を有効にする」を押してください。このファイルには計算済みの値を入れておらず、開いたアプリがその場で計算する作りです。"
     "そのため、販売サイトやスマートフォンのプレビュー表示では、数式のセルが空に見えることがあります。"),
    ("Googleスプレッドシートで使うには、どうすればいいですか。",
     "Googleスプレッドシートで空のファイルを開き、「ファイル」→「インポート」→「アップロード」で xlsx を選び、「新しいスプレッドシートを作成する」で取り込みます。"
     "元の xlsx（購入時の zip）は消さずに取っておいてください。"),
    ("スマートフォンや、ほかの表計算アプリでも使えますか。",
     "パソコンの Microsoft Excel と Googleスプレッドシートを対象にしています。スマートフォンのアプリでの操作は想定していません（表が横に長く、入力しづらいためです）。"
     "Numbers など他の表計算アプリは対象外で、動くかどうかは確認していません。"),
    ("為替や鑑定料を変えると、過去の行の金額も変わりますか。",
     "変わります。設定は1組だけで、在庫台帳のすべての行が同じ設定を見て鑑定費用を計算するためです。過去ぶんを固定したいときは、その行の「鑑定費用」のセルに実際にかかった金額を直接入力します。"
     "注文ごと・サービスレベルごとに料金を持ち分ける機能はありません。"),
    ("PSA 以外の鑑定会社でも使えますか。",
     "費用の項目名をご自身で読み替えれば、費用と利益の計算には使えます。ただし、グレードの選択肢は「未鑑定 / PSA10 / PSA9 / PSA8以下」の4つで固定で、通貨は円とドルの1組だけです。"
     "他社の料金体系や手続きに合うかどうかは確認していません。"),
    ("シミュレーターの結果どおりに利益が出ますか。相場は自動で入りますか。",
     "いいえ。シミュレーターは、ご自身が入れた売値と確率から平均（期待値）を計算するだけで、将来の相場や鑑定結果を予測するものではありません。利益が出ることを保証するものでもありません。"
     "相場や PSA の注文状況を自動で取得する機能はなく、すべて手入力です。"),
    ("無料ツール「PSA鑑定 仕入れ上限 逆算」と、仕入れ上限の金額が違うのはなぜですか。",
     "目標利益率の定義が2通りあるためです。シミュレーターは、仕入れ上限を「売却額に対する利益率」（利益 ÷ 売却額。在庫台帳・月次集計と同じ定義）と"
     "「仕入れ値に対する利益率」（利益 ÷ 仕入れ値。無料ツールと同じ定義）の2行で表示します。無料ツールの金額と比べるときは「仕入れ値に対する利益率」の行を見てください。"
     "「判定」は「売却額に対する利益率」の行で判定します。販売手数料率が0でないときや、前提の数字が違うときは、この行でもツールと合いません。"),
    ("税金や関税の計算は、これで合っていますか。確定申告に使えますか。",
     "このシートは収支の記録と試算のための道具で、税額を計算するものではありません。設定の税率・関税の初期値は一例で、実際の税額や制度を示すものではありません。"
     "税務と、関税・輸入時の税の扱いは、必ずご自身で税理士・税務署・税関などに確認してください。"),
    ("使い方の質問や、不具合の問い合わせはできますか。",
     "個別のサポート（使い方の質問への回答、カスタマイズ、不具合の個別対応）は行っていません。同梱の「よくある質問」とファイル内の「使い方」シートで解決できる範囲でお使いください。"
     "バージョンアップ版の提供もお約束していません。"),
]


def png_size(path):
    """PNG の幅と高さ（img の width/height に入れて、読み込み中のガタつきを防ぐ）。"""
    with open(path, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def export_shot(png, out_dir):
    """商品画像1枚を out_dir に出力し、(ファイル名, 幅, 高さ) を返す。元の PNG は読むだけで変更しない。

    Pillow があれば幅 SHEET_IMAGE_WIDTH px に縮小した WebP にする（幅がそれ以下の画像は拡大しない）。
    Pillow が無い環境では縮小せずに PNG のままコピーする。
    形式は 1200px 幅で比べて決めた: WebP 品質90 が合計約0.39MB、256色PNG 約0.48MB（赤字の色が変わる）、
    フルカラーPNG 約1.3MB、JPEG 品質90 約0.73MB。
    """
    try:
        from PIL import Image
    except ImportError:
        print(f"警告: Pillow が無いため {png.name} を縮小せずにコピーしました（pip install pillow で縮小されます）")
        shutil.copy(png, out_dir / png.name)
        return (png.name, *png_size(png))
    with Image.open(png) as im:
        im = im.convert("RGBA" if "A" in im.getbands() or "transparency" in im.info else "RGB")
        if im.width > SHEET_IMAGE_WIDTH:
            im = im.resize((SHEET_IMAGE_WIDTH, max(1, round(im.height * SHEET_IMAGE_WIDTH / im.width))), Image.LANCZOS)
        name = png.stem + ".webp"
        im.save(out_dir / name, "WEBP", quality=SHEET_IMAGE_QUALITY, method=6)
        return (name, im.width, im.height)


def sheet_body(shots):
    """shots: public/sheet/ に出力した画像の [(ファイル名, 幅, 高さ)]。空なら画像なしで組む。"""
    def fig(name, w, h, lazy=True):
        alt = SHEET_SHOTS.get(Path(name).stem + ".png", f"{SHEET_NAME}の画面")
        lz = ' loading="lazy"' if lazy else ""
        return (f'<figure><img src="/sheet/{e(name)}" alt="{e(alt)}" width="{w}" height="{h}"{lz}>'
                f'<figcaption>{e(alt)}。画像内のカード名・金額はすべて架空のサンプルです。</figcaption></figure>')
    cover = fig(*shots[0], lazy=False) if shots else ""
    rest = "".join(fig(*s) for s in shots[1:])
    price = f'<p class="price">価格: {e(PRODUCT_PRICE)}</p>' if PRODUCT_PRICE else ""
    if PRODUCT_URL:
        buy = (f'<div class="card note">{price}<a class="btn" href="{e(PRODUCT_URL)}" rel="noopener">販売ページで購入する（外部サイト）</a>'
               '<p class="lead">購入・決済・ダウンロードは外部の販売サイトで行います。当サイトでは販売・決済をしていません。</p></div>')
    else:
        buy = (f'<div class="card note">{price}<p><b>販売準備中</b></p>'
               '<p class="lead">まだ販売を始めていません。販売を始めたら、ここに販売ページへのリンクを掲載します。</p></div>')
    if PRODUCT_VERIFIED:
        verified = f"<li>動作確認した環境: {e(PRODUCT_VERIFIED)}</li>"
    else:
        verified = ("<li><b>Microsoft Excel と Googleスプレッドシートの実機での動作確認は、まだ行っていません。</b>"
                    "現時点で確認しているのは、数式の静的な点検と、LibreOffice Calc で再計算した値が手計算と一致することだけです。"
                    "Excel・Googleスプレッドシートで開いたあとの見た目（列幅・色・フォント）、プルダウン、入力規則、シート保護がそのまま残るかは確かめていません。</li>")
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in SHEET_FAQ)
    return f"""<h1>{e(SHEET_NAME)}</h1>
<p class="lead">トレカをPSA鑑定に出して売る個人向けの、Excel / Googleスプレッドシート用の収支管理シートです。
1枚ごとの仕入値・鑑定費用・売却額を台帳に入れると、原価と利益、注文別・月別の集計が自動で出ます。</p>
{cover}{buy}
<h2>何ができるか</h2>
<ul><li><b>在庫台帳</b>: カード1枚を1行で記録します。状態（在庫・鑑定中・返却済・売却済）とグレードはプルダウンで選びます。500行ぶん用意しています。</li>
<li><b>鑑定費用の自動計算</b>: 為替・鑑定料・往復送料・関税・税率・諸経費を設定すると、1枚あたりの鑑定費用を計算し、原価合計・販売手数料・利益・利益率まで出します。</li>
<li><b>注文別集計</b>: PSA注文番号ごとに、枚数・仕入合計・鑑定費用合計・売却合計・利益・未売却ぶんの原価を集計します（30注文まで）。</li>
<li><b>月次集計とグレード別割合</b>: 指定した年の売却月ごとの売上・原価・利益・枚数と、グレード別の枚数・割合（自分のPSA10率）を出します。</li>
<li><b>仕入れ前シミュレーター</b>: 仕入れ値と、PSA10 / PSA9 / それ以下の売値・確率を入れると、期待利益・損益分岐の仕入れ値・目標利益率からの仕入れ上限を表示します。
仕入れ上限は、目標利益率の2つの定義（売却額に対する利益率 / 仕入れ値に対する利益率）それぞれで出ます。</li></ul>
<p>黄色いセルが入力欄、灰色のセルは数式です。相場の取得やPSAの注文状況の取得などの自動連携はなく、すべて手入力です。</p>
{rest}
<h2>無料ツールとの違い</h2>
<p>1枚あたりの鑑定費用の式は、当サイトの {tool_link("psa-profit")} と同じです（シートは、1枚あたりの費用を1円単位に四捨五入してから計算します）。</p>
<p>利益率の定義は2通りあります。シートの在庫台帳・月次集計は「利益 ÷ 売却額」、当サイトの {tool_link("psa-max-buy")} は「利益 ÷ 仕入れ値」です。
シートのシミュレーターは、仕入れ上限をこの定義ごとに1行ずつ、2行で表示します。</p>
<ul><li><b>仕入れ上限（売却額に対する利益率）</b>: 利益 ÷ 売却額 が目標以上になる上限です。在庫台帳・月次集計と同じ定義で、シミュレーターの「判定」はこの行で判定します。</li>
<li><b>仕入れ上限（仕入れ値に対する利益率）</b>: 利益 ÷ 仕入れ値 が目標以上になる上限です。当サイトのツールと同じ定義なので、ツールの金額と比べるときはこの行を見ます。</li></ul>
<p>一例として、期待売値{yen(_EXPECTED)}・費用{yen(_C["total"])}・目標{DEF["target"]}%・販売手数料率0%のとき、ツールは{yen(_MAX_BUY)}、
シートは「仕入れ値に対する利益率」の行が{yen(_SHEET_MAX_ON_BUY)}、「売却額に対する利益率」の行が{yen(_SHEET_MAX_BUY)}です。
同じ目標でも、売却額の{DEF["target"]}%を残すほうが条件が厳しいので、「売却額に対する利益率」の行のほうが低く出ます。</p>
<p>「仕入れ値に対する利益率」の行でも、シートの販売手数料率が0でないとき（ツールには販売手数料の欄がありません）、為替・鑑定料などの前提が違うとき、
費用の四捨五入で100円の境目にちょうど当たったときは、ツールと一致しません。</p>
<h2>同梱物</h2>
<p>zip ファイル1つに、次の3ファイルが入っています。</p>
<ul><li><code>psa-shushi-kanri.xlsx</code>: シート本体（使い方 / 設定 / 在庫台帳 / 注文別集計 / 月次集計 / シミュレーター の6枚）</li>
<li><code>よくある質問_FAQ.txt</code>: よくある質問</li>
<li><code>はじめにお読みください.txt</code>: 開き方と最初の手順</li></ul>
<p>使い方の説明はファイル内の「使い方」シートに入っています。別冊のマニュアルはありません。在庫台帳には架空のサンプルデータが5行入っています（消してからお使いください）。</p>
<h2>対応環境</h2>
<ul><li>Microsoft Excel（.xlsx を開けるバージョン）</li>
<li>Googleスプレッドシート（「ファイル」→「インポート」で取り込み）</li>
<li>マクロ（VBA）・アドイン・外部データ接続は使っていません。使っている関数は IF / AND / OR / SUM / SUMIFS / COUNTIFS / COUNT / COUNTA / ROUND / ROUNDDOWN / MAX / DATE のみです。</li>
{verified}
<li>スマートフォンのアプリでの操作は想定していません（入力はパソコンを前提にしています）。</li></ul>
<h2>購入前に確認してほしいこと</h2>
<ul><li><b>サポートはありません。</b>使い方の質問への回答、カスタマイズ、不具合の個別対応は行っていません。バージョンアップ版の提供もお約束していません。</li>
<li><b>返金・キャンセルは、販売サイトの規定に従います。</b>当サイトでは受け付けていません。</li>
<li><b>税務と関税は各自でご確認ください。</b>このシートは収支の記録と試算のための道具で、税額を計算するものではありません。
確定申告・所得区分・消費税などの税務と、関税・輸入時の税の扱いは、税理士・税務署・税関などにご確認ください。</li>
<li><b>非公式のツールです。</b>PSA（Professional Sports Authenticator）社とは関係がありません。カード名・価格などのサンプルデータはすべて架空です。</li>
<li>鑑定料・送料・為替・関税・税率の初期値は一例です。必ずご自身の実際の金額に書き換えてください。</li>
<li>利益が出ることや、計算結果が実際の費用・税額と一致することを保証するものではありません。</li>
<li>設定を変えると、過去の行も含めて鑑定費用が計算し直されます（過去ぶんを固定する方法は「使い方」シートに記載）。</li>
<li>購入者ご本人の利用に限ります。ファイルの再配布・転売はご遠慮ください。</li></ul>
{buy}
<h2>よくある質問（抜粋）</h2>
<p class="lead">同梱の「よくある質問」からの抜粋です。</p>
{faq}
<h2>まずは無料ツールで計算する</h2>
<ul class="tools">{tool_items([s for s, *_ in CARD_TOOLS])}</ul>
<h2>計算の考え方の解説</h2>
<ul class="tools">{guide_items([s for s, *_ in GUIDES])}</ul>"""


GUIDE_INDEX_TITLE = "解説記事の一覧"
GUIDE_CRUMB = ("解説記事", "guide/")
PAGES = []   # 生成したページの (パス, title, description)。重複の点検に使う


def json_ld(*objs):
    """構造化データ。</script> で途切れないよう < は < にして出す。"""
    return "".join('<script type="application/ld+json">'
                   + json.dumps({"@context": "https://schema.org", **o}, ensure_ascii=False).replace("<", "\\u003c")
                   + "</script>" for o in objs)


def crumbs_html(crumbs):
    """パンくず。crumbs は [(名前, パス)] で、トップは含めない。最後の1件がいまのページ。"""
    items = '<li><a href="/">トップ</a></li>' + "".join(
        f'<li aria-current="page">{e(n)}</li>' if i == len(crumbs) - 1 else f'<li><a href="/{p}">{e(n)}</a></li>'
        for i, (n, p) in enumerate(crumbs))
    return f'<nav aria-label="パンくずリスト"><ol class="crumbs">{items}</ol></nav>'


def crumbs_ld(crumbs):
    names = [("トップ", "")] + list(crumbs)
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": n, "item": f"{BASE}/{p}"} for i, (n, p) in enumerate(names, 1)]}


_ROOT_REF = re.compile(r'\b(href|src)="/(?!/)')


def with_base_path(html_text):
    """href="/..." と src="/..." の前にベースパスを付ける（//example.com のような外部の参照は対象外）。ベースパスが空なら何も変えない。

    リンクを書く場所ごとに付けると付け忘れが 404 になるので、全ページが通る page() の出口で1回だけ行う。
    JavaScript（app.js → ./lib.js）は相対 import で、パスを組み立てる箇所も無いので、ベースパスを渡す必要はない。
    """
    return _ROOT_REF.sub(rf'\1="{BASE_PATH}/', html_text) if BASE_PATH else html_text


SITE_LD = {"@type": "WebSite", "name": SITE["name"], "url": f"{BASE}/"}


def page(path, title, desc, body, tool="", crumbs=(), ld=(), og_type="website", index=True):
    """共通テンプレート。index=False は検索に載せないページ（404）で、canonical・og:url・構造化データを出さない。"""
    full = f"{title}｜{SITE['name']}" if path else f"{SITE['name']}｜{title}"
    PAGES.append((path, full, desc))
    url = f"{BASE}/{path}"
    if index:
        robots = f'<link rel="canonical" href="{e(url)}">\n<meta property="og:url" content="{e(url)}">'
        ld = json_ld(*ld, *([crumbs_ld(crumbs)] if crumbs else []))
    else:
        robots, ld = '<meta name="robots" content="noindex">', ""
    image = f'\n<meta property="og:image" content="{e(OG_IMAGE_URL)}">' if OG_IMAGE_URL else ""
    return with_base_path(f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full)}</title>
<meta name="description" content="{e(desc)}">
{robots}
<meta property="og:title" content="{e(title if path else full)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{e(SITE['name'])}">
<meta property="og:locale" content="ja_JP">{image}
<meta name="twitter:card" content="{'summary_large_image' if OG_IMAGE_URL else 'summary'}">
<meta name="theme-color" content="{THEME_LIGHT}" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="{THEME_DARK}" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/style.css">{AD_HEAD}{ld}
</head><body data-tool="{tool}">
<header><a href="/">{e(SITE['name'])}</a></header>
<main>{crumbs_html(crumbs) if crumbs else ""}{body}</main>
<footer><a href="/">ツール一覧</a> ・ <a href="/born/">生まれ年の早見表</a> ・ <a href="/era/">和暦の年の早見</a> ・ <a href="/guide/">解説記事</a> ・ <a href="/privacy/">プライバシーポリシー・運営者情報</a><br>
計算結果は参考値です。重要な判断の前には公式の情報でご確認ください。</footer>
<script type="module" src="/app.js"></script>
</body></html>
""")


# ---- 早見ページ（/born/<西暦>/ と /era/<元号>/<年>/）-------------------------------
# 載せるのは計算で出せる値だけ（年齢・干支・和暦と西暦の対応・入学卒業年・定義を書ける節目）。その年の出来事などは載せない。
# 値は Python で計算し直さず、src/hayami.mjs（中身は src/lib.js の関数）を node で1回呼んで受け取る。
# 和暦の年のパスを /wareki/<元号>/<年>/ にしなかったのは、/wareki/ が変換ツールで、一覧ページを置く場所が重なるため。

BORN_INDEX = ("生まれ年の早見表", "born/")
ERA_INDEX = ("和暦の年の早見", "era/")
HAYAMI_TOOLS = ("age", "school", "wareki")   # 早見ページからリンクし、下部に早見ページへのリンクを出すツール
HAYAMI_LI = ('<li><a href="/born/"><b>生まれ年の早見表</b><span>生まれ年ごとの年齢早見表・干支・履歴書用の入学卒業年・節目の年。</span></a></li>'
             '<li><a href="/era/"><b>和暦の年の早見</b><span>「昭和50年は西暦何年」を、明治6年から今年まで1年ずつ。</span></a></li>')


def hayami_data():
    """早見ページの値（今日の日付で計算）。node が無ければ、理由を出して止める。"""
    t = date.today()
    try:
        r = subprocess.run(["node", str(ROOT / "src" / "hayami.mjs"), str(t.year), str(t.month), str(t.day)],
                           capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit("node が見つかりません。早見ページの値は src/lib.js で計算するため、ビルドには Node.js が必要です。")
    if r.returncode:
        raise SystemExit(f"src/hayami.mjs が失敗しました:\n{r.stderr}")
    return json.loads(r.stdout)


def _hy(key, now):
    """日付で変わる値。ビルド時点の値を書いておき、app.js の hayami が開いた日の値で上書きする。"""
    return f'<span data-hy="{key}">{e(now[key])}</span>'


def _grid(head, rows):
    return ('<table class="grid"><tr>' + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
            + "".join(f"<tr><th>{r[0]}</th>" + "".join(f"<td>{c}</td>" for c in r[1:]) + "</tr>" for r in rows) + "</table>")


def _yw(y, w):
    """表のセル用: 西暦の下に和暦を小さく出す。"""
    return f"{y}年<small>{e(w)}</small>"


def _asof(now):
    return (f'<p class="lead">年齢などは{_hy("asof", now)}の値です。JavaScript が有効なら、ページを開いた日の値に更新して表示します。</p>')


def _future_note(d, last_year):
    """表に今年より先の年があるときの注記（将来の元号は分からないため）。"""
    ty = d["today"][0]
    if last_year <= ty:
        return ""
    return f'<p class="lead">{ty + 1}年より先の和暦は、元号が{e(d["era"][-1]["era"])}のまま続いた場合の年数です。</p>'


def _hayami_tools():
    desc = {s: (t, x) for s, t, x, *_ in LIFE_TOOLS}
    return ('<ul class="tools">' + "".join(f'<li><a href="/{s}/"><b>{e(desc[s][0])}</b><span>{e(desc[s][1])}</span></a></li>' for s in HAYAMI_TOOLS)
            + HAYAMI_LI + "</ul>")


def born_name(b):
    return f'{b["year"]}年（{b["warekiLabel"]}）'


def born_page(d, b):
    """生まれ年ページ1枚の (title, description, body)。"""
    ty, y, now = d["today"][0], b["year"], b["now"]
    name, eto = born_name(b), f'{b["eto"]}年（{b["etoKana"]}どし）'
    n, el = b["school"]["normal"], b["school"]["early"]
    age_now = (f"{ty}年は生まれた年で、誕生日から0歳です。" if y == ty
               else f"{ty}年に{now['after']}になります（誕生日の前は{now['before']}）。")
    ms = b["milestones"]
    if b["schoolOk"]:
        title = f"{name}生まれの早見表（年齢・干支・入学卒業年）"
        desc = (f"{name}生まれは{eto}。{age_now}"
                f"小学校入学は{n[0]['enter']}年4月（早生まれは{el[0]['enter']}年4月）、4年制大学の卒業は{n[3]['grad']}年3月（早生まれは{el[3]['grad']}年3月）。100歳までの年齢早見表つき。")
    else:
        title = f"{name}生まれの早見表（年齢・干支・節目の年）"
        desc = (f"{name}生まれは{eto}。{age_now}"
                f"{ms[0]['name']}は{ms[0]['yearMan']}年、{ms[4]['name']}は数え年で{ms[4]['yearKazoe']}年。100歳までの年齢早見表と、節目の年の一覧つき。")
    split = "".join(f'<tr><th>{w["fromLabel"]}〜{w["toLabel"]}生まれ</th><td>{e(w["label"])}生まれ</td></tr>' for w in b["wareki"]) if len(b["wareki"]) > 1 else ""
    split_lead = (f'{y}年は年の途中で改元があったため、生まれた日によって{"と".join(e(w["label"]) for w in b["wareki"])}に分かれます。' if split else "")
    head = (f'<div class="card" id="hayami" data-kind="born" data-year="{y}" data-built="{ty * 100 + d["today"][1]}"><table>'
            f'<tr><th>生まれ年</th><td>{e(name)}</td></tr>{split}<tr><th>干支</th><td>{e(eto)}</td></tr>'
            f'<tr><th>{_hy("year", now)}の年齢（誕生日の前）</th><td>{_hy("before", now)}</td></tr>'
            f'<tr><th>{_hy("year", now)}の年齢（誕生日の後）</th><td>{_hy("after", now)}</td></tr>'
            f'<tr><th>{_hy("year", now)}の数え年</th><td>{_hy("kazoe", now)}</td></tr></table>{_asof(now)}</div>')
    age_rows = lambda rows: _grid(["年齢", "西暦", "和暦"], [(f'{a["age"]}歳', f'{a["year"]}年', e(a["wareki"])) for a in rows])
    ages = (f'<h2>年齢早見表（{y}年生まれ）</h2>'
            f'<p class="lead">その年の誕生日を迎えた後の満年齢です。誕生日の前は1歳少なく、数え年は1歳多くなります。まず10年ごと、その下に1歳ごとの表があります。</p>'
            f'{age_rows(b["ages"][::10])}'
            f'<details><summary>1歳ごとの表（0〜100歳）を開く</summary>{age_rows(b["ages"])}</details>{_future_note(d, y + 100)}')
    sch = lambda rows: _grid(["", "入学（4月）", "卒業（3月）"], [(s["name"], _yw(s["enter"], s["enterWareki"]), _yw(s["grad"], s["gradWareki"])) for s in rows])
    school = (f'<h2>履歴書用の入学・卒業年（{y}年生まれ）</h2>'
              f'<p class="lead">4月2日から翌年4月1日生まれが同じ学年になるため、{y}年生まれは生まれた日で学年が分かれます。</p>'
              f'<div class="cols"><div><h3>{y}年4月2日〜12月31日生まれ</h3>{sch(n)}</div>'
              f'<div><h3>{y}年1月1日〜4月1日生まれ（早生まれ）</h3>{sch(el)}</div></div>'
              f'<p>浪人・留年・休学がない場合の年です。大学は4年制で計算しています。和暦は、入学は4月、卒業は3月の時点の元号です。'
              f'生年月日を入れて確かめるには <a href="/school/">入学・卒業年 早見</a> を使えます。</p>{_future_note(d, n[3]["grad"])}')
    if not b["schoolOk"]:   # いまの学校制度になる前に小学校へ入学する年代
        school = (f'<h2>入学・卒業年について</h2><p>{y}年生まれの人は、いまの学校制度（小学校6年・中学校3年・高校3年・大学4年）になる前に小学校へ入学する年代です。'
                  'いまの制度の年数で数えた入学・卒業年は当時の学校の区切りと合わないため、この年の表は載せていません。</p>')
    defs = "".join(
        (f'<li><b>{m["name"]}（{m["kana"]}）</b>: 満{m["man"]}歳になる年（生まれ年＋{m["man"]}年）。数え年では{m["kazoe"]}歳で、どちらで数えても同じ年です。</li>'
         if m["yearKazoe"] == m["yearMan"] else
         f'<li><b>{m["name"]}（{m["kana"]}）</b>: 数え年{m["kazoe"]}歳になる年（生まれ年＋{m["kazoe"] - 1}年）。満年齢で数える場合は、満{m["man"]}歳になる年（生まれ年＋{m["man"]}年）。</li>')
        for m in ms)
    miles = (f'<h2>節目の年（{y}年生まれ）</h2>'
             + _grid(["", "数え年で数える場合", "満年齢で数える場合"],
                     [(m["name"], _yw(m["yearKazoe"], f'数え年{m["kazoe"]}歳・{m["warekiKazoe"]}'), _yw(m["yearMan"], f'満{m["man"]}歳・{m["warekiMan"]}')) for m in ms])
             + f'<p class="lead">載せているのは、年の決め方を下のとおり書けるものだけです。数え年は、生まれた年を1歳とし、元日ごとに1歳加える数え方です。</p><ul>{defs}'
             f'<li><b>年男・年女</b>: 生まれ年と同じ十二支（{b["eto"]}）の年。12年ごとで、{"・".join(f"{x}年" for x in b["etoYears"])}。</li></ul>'
             f'<p>厄年は、数え方が神社や地域によって違い、1つの決まりとして書けないため載せていません。</p>{_future_note(d, ms[-1]["yearMan"])}')
    by = {x["year"]: x for x in d["born"]}
    prev = f'<a href="/born/{y - 1}/">← {e(born_name(by[y - 1]))}生まれ</a>' if y - 1 in by else "<span></span>"
    nxt = f'<a href="/born/{y + 1}/">{e(born_name(by[y + 1]))}生まれ →</a>' if y + 1 in by else "<span></span>"
    eras = "、".join(f'<a href="/era/{x["slug"]}/{x["n"]}/">{e(x["label"])}は西暦何年</a>' for x in d["era"] if x["year"] == y)
    nav = (f'<h2>前後の年</h2><p class="nav">{prev}{nxt}</p>'
           f'<p>和暦の年のページ: {eras} ／ <a href="/born/">生まれ年の一覧</a></p>')
    body = (f'<h1>{e(name)}生まれの早見表</h1>'
            f'<p class="lead">{y}年に生まれた人の、年齢・干支・{"履歴書に書く入学と卒業の年・" if b["schoolOk"] else ""}節目の年を、計算でまとめた早見表です。{split_lead}</p>'
            f'{head}{AD_SLOT}{ages}{school}{miles}{nav}<h2>関連するツールと早見表</h2>{_hayami_tools()}')
    return title, desc, body


def era_page(d, x, i):
    """和暦の年ページ1枚の (title, description, body)。i は d["era"] の中の位置。"""
    ty, y, now, label, other = d["today"][0], x["year"], x["now"], x["label"], x["other"]
    first = x["n"] == 1
    full = f'{label}（{x["era"]}1年）' if first else label           # 元年は「1年」でも読めるようにする
    eto = f'{x["eto"]}年（{x["etoKana"]}どし）'
    has_born = y >= d["bornMin"]                                      # 年齢を出すのは、生まれ年ページのある年だけ
    current = x["era"] == d["era"][-1]["era"]
    if other:
        span = f'{y}年{x["from"]}〜{x["to"]}'
        other_txt = (f'{other["toLabel"]}までは{other["label"]}' if x["n"] == 1 else f'{other["fromLabel"]}から{other["label"]}')
        h1 = f'{full}は西暦{y}年（{x["from"] + "から" if x["n"] == 1 else x["to"] + "まで"}）'
        period = f'{span}（{other_txt}）'
        what = f'{full}は西暦{y}年の{x["from"]}〜{x["to"]}です（{other_txt}）。'
    else:
        h1, period = f"{full}は西暦{y}年", f"{y}年1月1日〜12月31日"
        what = f"{full}は西暦{y}年です。"
    title = f"{h1}｜干支・年齢の早見"
    ago = f"{ty}年の今年にあたります。" if y == ty else f"{ty}年からみて{now['ago']}です。"
    age_desc = ("" if not has_born else f"{label}生まれの人は、{ty}年は誕生日から0歳です。" if y == ty
                else f"{label}生まれの人は、{ty}年に{now['after']}になります（誕生日の前は{now['before']}）。")
    desc = f"{what}干支は{eto}。{ago}{age_desc}"
    rows = (f'<tr><th>和暦</th><td>{e(full)}</td></tr><tr><th>西暦</th><td>{y}年</td></tr><tr><th>期間</th><td>{e(period)}</td></tr>'
            f'<tr><th>干支</th><td>{e(eto)}</td></tr>'
            f'<tr><th>{_hy("year", now)}からみて</th><td>{_hy("ago", now)}</td></tr>')
    if not current:
        rows += f'<tr><th>{e(x["era"])}が続いていた場合の{_hy("year", now)}</th><td>{_hy("ifCont", now)}</td></tr>'
    if has_born:
        rows += (f'<tr><th>{e(label)}生まれの年齢（{_hy("year", now)}・誕生日の前）</th><td>{_hy("before", now)}</td></tr>'
                 f'<tr><th>{e(label)}生まれの年齢（{_hy("year", now)}・誕生日の後）</th><td>{_hy("after", now)}</td></tr>')
    head = (f'<div class="card" id="hayami" data-kind="era" data-era="{e(x["era"])}" data-n="{x["n"]}" data-built="{ty * 100 + d["today"][1]}">'
            f'<table>{rows}</table>{_asof(now)}</div>')
    lead = what + (f'「{label}」と「{x["era"]}1年」は同じ年です。' if first else "")
    if x["era"] == "明治" and x["n"] == 6:
        lead += "このサイトの和暦は、太陽暦が採用された明治6年（1873年）以降を対象にしています。"
    steps = (f'<h2>{e(label)}から10年ごとの年</h2>'
             + _grid(["", "西暦", "和暦"], [(f'{s["after"]}年後', f'{s["year"]}年', e(s["wareki"])) for s in x["steps"]])
             + _future_note(d, x["steps"][-1]["year"]))
    born = ""
    if has_born:
        b = next(b for b in d["born"] if b["year"] == y)
        born = (f'<h2>{y}年生まれの早見表</h2><ul class="tools"><li><a href="/born/{y}/"><b>{e(born_name(b))}生まれの早見表</b>'
                f'<span>100歳までの年齢早見表、履歴書用の入学・卒業年、節目の年。</span></a></li></ul>')
    link = lambda z, arrow_left: (f'<a href="/era/{z["slug"]}/{z["n"]}/">' + ("← " if arrow_left else "")
                                  + f'{e(z["label"])}（{z["year"]}年）' + ("" if arrow_left else " →") + "</a>")
    prev = link(d["era"][i - 1], True) if i > 0 else "<span></span>"
    nxt = link(d["era"][i + 1], False) if i + 1 < len(d["era"]) else "<span></span>"
    nav = (f'<h2>前後の年</h2><p class="nav">{prev}{nxt}</p>'
           f'<p><a href="/era/#{x["slug"]}">{e(x["era"])}の年の一覧</a></p>')
    body = (f'<h1>{e(h1)}</h1><p class="lead">{e(lead)}</p>{head}{AD_SLOT}{steps}{born}{nav}'
            f'<h2>関連するツールと早見表</h2>{_hayami_tools()}')
    return title, desc, body


def write_page(path, html_text):
    out = OUT / path
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html_text, encoding="utf-8")


def build_hayami():
    """早見ページを全部書き出し、sitemap に入れるパスの一覧を返す。"""
    d = hayami_data()
    ty = d["today"][0]
    paths = ["born/", "era/"]
    for b in d["born"]:
        title, desc, body = born_page(d, b)
        path = f'born/{b["year"]}/'
        write_page(path, page(path, title, desc, body, "hayami", crumbs=[BORN_INDEX, (f'{b["year"]}年生まれ', path)]))
        paths.append(path)
    for i, x in enumerate(d["era"]):
        title, desc, body = era_page(d, x, i)
        path = f'era/{x["slug"]}/{x["n"]}/'
        write_page(path, page(path, title, desc, body, "hayami", crumbs=[ERA_INDEX, (x["label"], path)]))
        paths.append(path)

    first, last = d["born"][0], d["born"][-1]
    decades = {}
    for b in d["born"]:
        decades.setdefault(b["year"] // 10 * 10, []).append(b)
    born_desc = (f'{first["year"]}年（{first["warekiLabel"]}）から{last["year"]}年（{last["warekiLabel"]}）までの生まれ年ごとに、'
                 "年齢早見表・干支・履歴書用の入学卒業年・節目の年をまとめた早見表の一覧です。")
    born_list = "".join(
        f'<h2 id="y{dec}">{dec}年代生まれ</h2><ul class="years">'
        + "".join(f'<li><a href="/born/{b["year"]}/">{e(born_name(b))}</a></li>' for b in bs) + "</ul>" for dec, bs in decades.items())
    write_page("born/", page("born/", f'生まれ年の早見表の一覧（{first["year"]}年〜{last["year"]}年）', born_desc,
                             f'<h1>生まれ年の早見表</h1><p class="lead">{e(born_desc)}生まれ年を選んでください。</p>{born_list}'
                             f'<h2>関連するツールと早見表</h2>{_hayami_tools()}', crumbs=[BORN_INDEX]))
    eras = {}
    for x in d["era"]:
        eras.setdefault(x["era"], []).append(x)
    e0, e1 = d["era"][0], d["era"][-1]
    era_desc = (f'{e0["label"]}（{e0["year"]}年）から{e1["label"]}（{e1["year"]}年）まで、和暦の年ごとに西暦との対応・干支・'
                "その年に生まれた人の年齢をまとめた早見ページの一覧です。")
    era_list = "".join(
        f'<h2 id="{xs[0]["slug"]}">{e(name)}（{xs[0]["year"]}年〜{xs[-1]["year"]}年）</h2><ul class="years">'
        + "".join(f'<li><a href="/era/{x["slug"]}/{x["n"]}/">{e(x["label"])}（{x["year"]}年）</a></li>' for x in xs) + "</ul>"
        for name, xs in reversed(eras.items()))
    write_page("era/", page("era/", f'和暦の年の早見の一覧（{e0["label"]}〜{e1["label"]}）', era_desc,
                            f'<h1>和暦の年の早見</h1><p class="lead">{e(era_desc)}'
                            f'明治は太陽暦が採用された明治6年（1873年）以降が対象です。西暦や和暦を入力して変換するには <a href="/wareki/">和暦・西暦 変換</a> を使えます。</p>'
                            f'{era_list}<h2>関連するツールと早見表</h2>{_hayami_tools()}', crumbs=[ERA_INDEX]))
    return paths, len(d["born"]), len(d["era"]), ty


def favicon_svg():
    """角丸の四角に「＝」。外部ファイルを使わず、ここで生成する。"""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="{ACCENT}"/>'
            f'<rect x="16" y="21" width="32" height="8" rx="4" fill="{THEME_LIGHT}"/>'
            f'<rect x="16" y="35" width="32" height="8" rx="4" fill="{THEME_LIGHT}"/></svg>\n')


def check():
    """公開前に直すべき項目を [(区分, 文)] で返す。区分は「要対応」か「任意」。"""
    must, opt = [], []
    if BASE == DEFAULT_URL or "example.com" in BASE:
        must.append(f"url が初期値（{BASE}）のままです。公開URLに書き換えてください（canonical・og:url・sitemap.xml・robots.txt に使われます）。")
    elif not BASE.startswith("https://"):
        must.append(f"url（{BASE}）が https:// で始まっていません。")
    operator = str(SITE.get("operator", "")).strip()
    if not operator or operator == DEFAULT_OPERATOR:
        must.append(f"operator が{'空' if not operator else '初期値（' + operator + '）のまま'}です。運営者名（ペンネーム可）に書き換えてください。")
    if not str(SITE.get("contact", "")).strip():
        must.append("contact が空です。プライバシーポリシーのページに連絡先が表示されません（広告の審査では連絡先が見られます）。")
    ads = str(SITE.get("adsense_client", "")).strip()
    if ads and not ads.startswith("ca-pub-"):
        must.append(f"adsense_client（{ads}）が ca-pub- で始まっていません。")
    if OG_IMAGE and OG_IMAGE_URL != OG_IMAGE and not (ROOT / "src" / OG_IMAGE.lstrip("/")).is_file():
        must.append(f"og_image のファイル src/{OG_IMAGE.lstrip('/')} がありません（og:image のリンク先が存在しなくなります）。")
    built = OUT / "index.html"
    if not built.is_file():
        must.append("public/ がまだ生成されていません。python build.py を実行してください。")
    elif f'<link rel="canonical" href="{e(BASE)}/">' not in built.read_text(encoding="utf-8"):
        must.append("public/ がいまの site.json の url で生成されていません。python build.py を実行し直してください。")
    if built.is_file() and not (OUT / "born" / str(date.today().year) / "index.html").is_file():
        must.append(f"public/ の早見ページが{date.today().year}年のぶんまで生成されていません（年が変わったあと再ビルドしていません）。python build.py を実行し直してください。")
    if not ads:
        opt.append("adsense_client が空です。広告枠は出ません（審査に通ってから入れます）。")
    if not OG_IMAGE:
        opt.append("og_image がありません。SNS で共有されたときに画像が出ません（1200×630px ほどの画像を src/ に置いてファイル名を書くか、https:// のURLを書きます）。")
    if not PRODUCT_URL:
        opt.append("product_url が空です。商品紹介ページ（/sheet/）は「販売準備中」と表示されます。")
    elif not PRODUCT_PRICE:
        opt.append("product_price が空です。商品紹介ページに価格が表示されません。")
    if not PRODUCT_VERIFIED:
        opt.append("product_verified が空です。商品紹介ページに「Excel と Googleスプレッドシートの実機では未確認」と表示されます。")
    if not (SHEET_IMAGES.is_dir() and any(SHEET_IMAGES.glob("*.png"))):
        opt.append("商品画像（products/psa-sheet/dist/images/*.png）がありません。商品紹介ページは画像なしになります。")
    return [("要対応", m) for m in must] + [("任意", m) for m in opt]


def print_check():
    items = check()
    must = [m for k, m in items if k == "要対応"]
    print(f"公開前チェック: 要対応 {len(must)} 件 / 任意 {len(items) - len(must)} 件（site.json を直して python build.py）")
    for k, m in items:
        print(f"  [{k}] {m}")
    if not must:
        print("  公開前に直す必要のある項目はありません。")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for f in ("lib.js", "app.js", "style.css"):
        shutil.copy(ROOT / "src" / f, OUT / f)
    (OUT / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")   # GitHub Pages に Jekyll の処理をさせない（中身は空でよい）
    if OG_IMAGE and OG_IMAGE_URL != OG_IMAGE and (ROOT / "src" / OG_IMAGE.lstrip("/")).is_file():
        shutil.copy(ROOT / "src" / OG_IMAGE.lstrip("/"), OUT / OG_IMAGE.lstrip("/"))

    links = "".join(
        f'<h2>{e(g)}</h2><ul class="tools">'
        + "".join(f'<li><a href="/{s}/"><b>{e(t)}</b><span>{e(d)}</span></a></li>' for s, t, d, *_ in tools) + "</ul>"
        + (f'<p class="lead">計算の考え方の解説（<a href="/guide/">{GUIDE_INDEX_TITLE}</a>）と、記録用のシート</p>{card_pillar([s for s, *_ in GUIDES])}'
           if tools is CARD_TOOLS else "")
        for g, tools in GROUPS)
    links += f'<h2>早見表</h2><ul class="tools">{HAYAMI_LI}</ul>'
    compact = lambda tools: "".join(f'<li><a href="/{s}/"><b>{e(t)}</b></a></li>' for s, t, *_ in tools)
    for slug, title, desc, form, note in TOOLS:
        # 「ほかのツール」は同じグループを先に出す
        same = next(tools for _, tools in GROUPS if any(s == slug for s, *_ in tools))
        others = compact([t for t in same if t[0] != slug] + [t for t in TOOLS if t not in same])
        app_ld = {"@type": "WebApplication", "name": title, "description": desc, "url": f"{BASE}/{slug}/", "inLanguage": "ja",
                  "applicationCategory": "UtilitiesApplication", "operatingSystem": "Any",
                  "offers": {"@type": "Offer", "price": "0", "priceCurrency": "JPY"}}
        body = (f'<h1>{e(title)}</h1><p class="lead">{e(desc)}</p>'
                f'<div class="card">{form}</div><div class="card" id="result" aria-live="polite"></div>{AD_SLOT}'
                f'<h2>このツールについて</h2>{"".join(f"<p>{e(p)}</p>" for p in note.split(chr(10)))}'
                + (f'<h2>計算の考え方の解説と、記録用のシート</h2>{card_pillar(TOOL_GUIDES[slug])}' if slug in TOOL_GUIDES else "")
                + (f'<h2>早見表</h2><ul class="tools">{HAYAMI_LI}</ul>' if slug in HAYAMI_TOOLS else "")
                + f'<h2>ほかのツール</h2><ul class="tools">{others}</ul>')
        (OUT / slug).mkdir()
        (OUT / slug / "index.html").write_text(page(f"{slug}/", title, desc, body, slug, crumbs=[(title, f"{slug}/")], ld=[app_ld]), encoding="utf-8")

    top_desc = "和暦変換・年齢計算・日数計算・消費税・割り勘など暮らしと仕事の計算と、トレカのPSA鑑定の損益計算を、登録なし・無料で。"
    (OUT / "index.html").write_text(
        page("", "登録なしで使える無料の計算ツール集", top_desc,
             f'<h1>{e(SITE["name"])}</h1><p class="lead">{e(top_desc)}</p>{links}{AD_SLOT}',
             ld=[{**SITE_LD, "description": top_desc, "inLanguage": "ja"}]),
        encoding="utf-8")

    guide_desc = "トレカをPSA鑑定に出して売るときの、1枚あたり費用の数え方・損益分岐の仕入れ値・記録の付け方を説明した解説記事の一覧です。"
    (OUT / "guide").mkdir()
    (OUT / "guide" / "index.html").write_text(
        page("guide/", GUIDE_INDEX_TITLE, guide_desc,
             f'<h1>{GUIDE_INDEX_TITLE}</h1><p class="lead">{e(guide_desc)}料金や税率の実際の額ではなく、計算の考え方を説明しています。</p>'
             f'<ul class="tools">{guide_items([s for s, *_ in GUIDES])}</ul>'
             f'<h2>関連するツール</h2><ul class="tools">{tool_items([s for s, *_ in CARD_TOOLS])}</ul>'
             f'<h2>記録用のシート</h2><ul class="tools">{SHEET_LI}</ul>', crumbs=[GUIDE_CRUMB]),
        encoding="utf-8")

    for slug, title, desc, body, tools in GUIDES:
        others = guide_items([s for s, *_ in GUIDES if s != slug])
        body = (f'<h1>{e(title)}</h1>{body}{AD_SLOT}'
                f'<h2>関連するツール</h2><ul class="tools">{tool_items(tools)}</ul>'
                f'<h2>記録用のシートと、ほかの解説</h2><ul class="tools">{SHEET_LI}{others}</ul>')
        # 公開日・著者は確認できる値が無いので入れない
        article_ld = {"@type": "Article", "headline": title, "description": desc, "url": f"{BASE}/guide/{slug}/",
                      "mainEntityOfPage": f"{BASE}/guide/{slug}/", "inLanguage": "ja", "isPartOf": SITE_LD,
                      **({"image": OG_IMAGE_URL} if OG_IMAGE_URL else {})}
        (OUT / "guide" / slug).mkdir()
        (OUT / "guide" / slug / "index.html").write_text(
            page(f"guide/{slug}/", title, desc, body, crumbs=[GUIDE_CRUMB, (title, f"guide/{slug}/")], ld=[article_ld], og_type="article"),
            encoding="utf-8")

    (OUT / "sheet").mkdir()
    shots = []
    if SHEET_IMAGES.is_dir():   # 商品画像が無くても（psa-sheet が無い環境でも）ページは成立する
        for png in sorted(SHEET_IMAGES.glob("*.png")):
            shots.append(export_shot(png, OUT / "sheet"))
    (OUT / "sheet" / "index.html").write_text(
        page("sheet/", f"{SHEET_NAME}（Excel / Googleスプレッドシート用）", SHEET_DESC, sheet_body(shots),
             crumbs=[(SHEET_NAME, "sheet/")]), encoding="utf-8")

    contact = f'<p>お問い合わせ: {e(SITE["contact"])}</p>' if SITE["contact"] else ""
    ads = ("<h2>広告について</h2><p>当サイトは第三者配信の広告サービス（Google アドセンス）を利用しています。"
           "広告配信事業者は、利用者の興味に応じた広告を表示するために Cookie を使用することがあります。"
           'Cookie を無効にする方法は <a href="https://policies.google.com/technologies/ads?hl=ja">Google の広告に関するポリシー</a> をご覧ください。</p>'
           ) if SITE["adsense_client"] else ""
    privacy = (f'<h1>プライバシーポリシー・運営者情報</h1><h2>運営者</h2><p>{e(SITE["operator"])}</p>{contact}'
               "<h2>入力内容の扱い</h2><p>各ツールに入力された内容は、お使いのブラウザの中だけで処理され、"
               f"当サイトのサーバーには送信・保存されません。</p>{ads}"
               "<h2>免責事項</h2><p>計算結果の正確さには注意を払っていますが、内容を保証するものではありません。"
               "当サイトの利用によって生じた損害について、運営者は責任を負いません。</p>")
    (OUT / "privacy").mkdir()
    (OUT / "privacy" / "index.html").write_text(
        page("privacy/", "プライバシーポリシー・運営者情報", "当サイトのプライバシーポリシーと運営者情報です。", privacy,
             crumbs=[("プライバシーポリシー・運営者情報", "privacy/")]),
        encoding="utf-8")

    # 存在しないURL用。GitHub Pages や Cloudflare Pages は、公開物のルートにある 404.html を自動で返す。検索には載せない（noindex、sitemap にも入れない）
    # どの階層のURLで表示されても壊れないよう、リンクと CSS・JS は（ほかのページと同じく）ベースパスつきの絶対パスで出す
    not_found = ('<h1>ページが見つかりません</h1><p>お探しのページは、移動または削除されたか、URLが間違っている可能性があります。</p>'
                 '<a class="btn" href="/">トップ（ツール一覧）へ</a>'
                 + "".join(f'<h2>{e(g)}</h2><ul class="tools">{compact(tools)}</ul>' for g, tools in GROUPS)
                 + '<h2>早見表</h2><ul class="tools"><li><a href="/born/"><b>生まれ年の早見表</b></a></li><li><a href="/era/"><b>和暦の年の早見</b></a></li></ul>'
                 + f'<h2>解説記事</h2><ul class="tools"><li><a href="/guide/"><b>{GUIDE_INDEX_TITLE}</b></a></li></ul>')
    (OUT / "404.html").write_text(
        page("404.html", "ページが見つかりません", "お探しのページは見つかりませんでした。トップのツール一覧からお探しください。", not_found, index=False),
        encoding="utf-8")

    hayami_paths, n_born, n_era, hayami_year = build_hayami()

    for i, name in ((1, "title"), (2, "description")):   # 空・重複は検索結果で区別がつかなくなるので、生成を止める
        seen = {}
        for p in PAGES:
            if not p[i].strip() or p[i] in seen:
                raise SystemExit(f"{name} が空か重複しています: /{p[0]}" + (f" と /{seen[p[i]]}" if p[i] in seen else ""))
            seen[p[i]] = p[0]

    urls = [""] + [f"{s}/" for s, *_ in TOOLS] + ["guide/"] + [f"guide/{s}/" for s, *_ in GUIDES] + ["sheet/", "privacy/"] + hayami_paths
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{e(BASE)}/{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    # クローラーが読む robots.txt はドメイン直下のものだけ。ベースパスがあるとき（GitHub のプロジェクトページ）はこのファイルは読まれないが、害は無いので出しておく
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    if shots:
        before = sum(p.stat().st_size for p in SHEET_IMAGES.glob("*.png"))
        after = sum((OUT / "sheet" / n).stat().st_size for n, *_ in shots)
        print(f"商品画像 {len(shots)} 枚: 元 {before / 1024:,.0f} KB → 出力 {after / 1024:,.0f} KB")
    print(f"{len(TOOLS)} ツール + 解説 {len(GUIDES)} 本 + 商品紹介（画像 {len(shots)} 枚、"
          f"{'購入ボタンあり' if PRODUCT_URL else '販売準備中'}）+ トップ + 解説の一覧 + プライバシー + 404 を {OUT} に生成しました")
    print(f"早見ページ: 生まれ年 {n_born} + 和暦の年 {n_era} + 一覧 2（{hayami_year}年時点の年齢。年が変わったら再ビルドしてください）／ 全 {len(PAGES)} ページ")
    must = sum(k == "要対応" for k, _ in check())
    if must:
        print(f"公開前に直す項目が {must} 件あります。一覧は python build.py --check")


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        print_check()
    else:
        main()
