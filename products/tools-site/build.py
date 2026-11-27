"""静的サイトを public/ に生成する。  使い方: python build.py

site.json を書き換えて再実行すると、サイト名・URL・広告IDが全ページに反映される。
"""

import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
SITE = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
OUT = ROOT / "public"

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


def page(path, title, desc, body, tool=""):
    full = f"{title}｜{SITE['name']}" if path else f"{SITE['name']}｜{title}"
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(SITE['url'])}/{path}">
<link rel="stylesheet" href="/style.css">{AD_HEAD}
</head><body data-tool="{tool}">
<header><a href="/">{e(SITE['name'])}</a></header>
<main>{body}</main>
<footer><a href="/">ツール一覧</a> ・ <a href="/privacy/">プライバシーポリシー・運営者情報</a><br>
計算結果は参考値です。重要な判断の前には公式の情報でご確認ください。</footer>
<script type="module" src="/app.js"></script>
</body></html>
"""


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for f in ("lib.js", "app.js", "style.css"):
        shutil.copy(ROOT / "src" / f, OUT / f)

    links = "".join(
        f'<h2>{e(g)}</h2><ul class="tools">'
        + "".join(f'<li><a href="/{s}/"><b>{e(t)}</b><span>{e(d)}</span></a></li>' for s, t, d, *_ in tools) + "</ul>"
        for g, tools in GROUPS)
    for slug, title, desc, form, note in TOOLS:
        others = "".join(f'<li><a href="/{s}/"><b>{e(t)}</b></a></li>' for s, t, *_ in TOOLS if s != slug)
        body = (f'<h1>{e(title)}</h1><p class="lead">{e(desc)}</p>'
                f'<div class="card">{form}</div><div class="card" id="result" aria-live="polite"></div>{AD_SLOT}'
                f'<h2>このツールについて</h2>{"".join(f"<p>{e(p)}</p>" for p in note.split(chr(10)))}'
                f'<h2>ほかのツール</h2><ul class="tools">{others}</ul>')
        (OUT / slug).mkdir()
        (OUT / slug / "index.html").write_text(page(f"{slug}/", title, desc, body, slug), encoding="utf-8")

    top_desc = "和暦変換・年齢計算・日数計算・消費税・割り勘など暮らしと仕事の計算と、トレカのPSA鑑定の損益計算を、登録なし・無料で。"
    (OUT / "index.html").write_text(
        page("", "登録なしで使える無料の計算ツール集", top_desc,
             f'<h1>{e(SITE["name"])}</h1><p class="lead">{e(top_desc)}</p>{links}{AD_SLOT}'),
        encoding="utf-8")

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
        page("privacy/", "プライバシーポリシー・運営者情報", "当サイトのプライバシーポリシーと運営者情報です。", privacy),
        encoding="utf-8")

    urls = [""] + [f"{s}/" for s, *_ in TOOLS] + ["privacy/"]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{e(SITE['url'])}/{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE['url']}/sitemap.xml\n", encoding="utf-8")
    print(f"{len(TOOLS)} ツール + トップ + プライバシーを {OUT} に生成しました")


if __name__ == "__main__":
    main()
