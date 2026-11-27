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

TOOLS = [
    ("wareki", "和暦・西暦 変換", "西暦から和暦、和暦から西暦へすぐ変換。改元のあった年や干支も表示します。",
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
     "「初日を含む」は開始日を1日目として数える方法です。マイナスの日数を入れると◯日前を計算できます。"),
    ("count", "文字数カウント", "入力した文章の文字数・空白を除いた文字数・行数・原稿用紙換算をその場で数えます。",
     """<label>文章<textarea id="text" placeholder="ここに入力または貼り付け"></textarea></label>""",
     "入力した文章は外部に送信されず、お使いのブラウザの中だけで数えます。絵文字なども1文字として数えます。"),
    ("warikan", "割り勘計算", "合計金額と人数から1人あたりの金額を計算。100円・500円単位の切り上げにも対応。",
     """<label>合計金額（円）<input id="total" type="number" inputmode="numeric"></label>
<div class="row"><label>人数<input id="people" type="number" inputmode="numeric" value="2" min="1"></label>
<label>切り上げ単位<select id="unit"><option value="1">1円</option><option value="10">10円</option><option value="100" selected>100円</option><option value="500">500円</option><option value="1000">1000円</option></select></label></div>""",
     "指定した単位で切り上げるため、集めた金額が合計を上回ります。その差額を「おつり」として表示します。"),
    ("tax", "消費税計算", "税抜から税込、税込から税抜を計算。8%・10%と端数処理を選べます。",
     """<label>金額（円）<input id="price" type="number" inputmode="numeric"></label>
<div class="row"><label>入力額<select id="dir"><option value="net">税抜</option><option value="gross">税込</option></select></label>
<label>税率<select id="rate"><option value="10">10%</option><option value="8">8%（軽減税率）</option></select></label>
<label>端数<select id="mode"><option value="floor">切り捨て</option><option value="round">四捨五入</option><option value="ceil">切り上げ</option></select></label></div>""",
     "消費税の1円未満の端数処理は事業者が決められます。多くの店舗では切り捨てです。"),
    ("discount", "割引・ポイント還元 計算", "◯%オフの支払額と、ポイント還元を含めた実質価格を計算します。",
     """<label>元の価格（円）<input id="price" type="number" inputmode="numeric"></label>
<div class="row"><label>割引率（%）<input id="off" type="number" inputmode="decimal" value="0"></label>
<label>ポイント還元率（%）<input id="point" type="number" inputmode="decimal" value="0"></label></div>""",
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
]

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

    links = "".join(f'<li><a href="/{s}/"><b>{e(t)}</b><span>{e(d)}</span></a></li>' for s, t, d, *_ in TOOLS)
    for slug, title, desc, form, note in TOOLS:
        others = "".join(f'<li><a href="/{s}/"><b>{e(t)}</b></a></li>' for s, t, *_ in TOOLS if s != slug)
        body = (f'<h1>{e(title)}</h1><p class="lead">{e(desc)}</p>'
                f'<div class="card">{form}</div><div class="card" id="result" aria-live="polite"></div>{AD_SLOT}'
                f'<h2>このツールについて</h2><p>{e(note)}</p>'
                f'<h2>ほかのツール</h2><ul class="tools">{others}</ul>')
        (OUT / slug).mkdir()
        (OUT / slug / "index.html").write_text(page(f"{slug}/", title, desc, body, slug), encoding="utf-8")

    top_desc = "和暦変換・年齢計算・日数計算・消費税・割り勘など、暮らしと仕事でよく使う計算を登録なし・無料で。"
    (OUT / "index.html").write_text(
        page("", "登録なしで使える無料の計算ツール集", top_desc,
             f'<h1>{e(SITE["name"])}</h1><p class="lead">{e(top_desc)}</p><ul class="tools">{links}</ul>{AD_SLOT}'),
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
