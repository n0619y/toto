"""未鑑定カード（素体）の郵送買取の受付サイトを public/ に生成する。  使い方: python build.py

運営者が決める値はすべて site.json に書く。空の項目は、ページのその箇所に「準備中」と出る。
python build.py --check は、公開前に直す項目を一覧表示する（生成はしない。警告だけで、エラーでは止めない）。

古物商許可（公安委員会名・番号）、本人確認の方法、申込フォームのURL のどれかが空のあいだは、
申込ボタンを出さず「受付準備中」と表示する。
"""

import hashlib
import html
import json
import re
import shutil
import sys
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).parent
SITE_TEXT = (ROOT / "site.json").read_text(encoding="utf-8")
SITE = json.loads(SITE_TEXT)
STAMP = hashlib.sha256(SITE_TEXT.encode("utf-8")).hexdigest()[:16]   # public/ がいまの site.json から作られたかを --check で確かめる
OUT = ROOT / "public"
DEFAULT_URL = "https://example.com"
_CSS = (ROOT / "src" / "style.css").read_text(encoding="utf-8")
THEME_LIGHT, THEME_DARK = re.findall(r"--bg:(#[0-9a-fA-F]{3,8})", _CSS)[:2]
ACCENT = re.search(r"--acc:(#[0-9a-fA-F]{3,8})", _CSS).group(1)

e = html.escape
TBD = '<span class="tbd">準備中</span>'

# site.json の項目: (キー, 何を書くか, どこに確認して決めるか)。--check と README の表はこの順。
KEYS = [
    ("name", "屋号", "許可・届出の名義との書き分けは、所轄の警察署（古物の担当窓口）に確認する"),
    ("url", "公開URL（https:// から。末尾の / は不要）", "公開先のサービスで決まる"),
    ("kobutsu_iinkai", "古物商許可を受けた公安委員会の名前（例: ◯◯県公安委員会）", "許可証のとおりに書く"),
    ("kobutsu_bango", "古物商許可の番号（例: 第◯◯◯◯◯◯◯◯◯◯◯◯号）", "許可証のとおりに書く"),
    ("shozaichi", "所在地（都道府県と市まで。番地は書かない）", "表示が求められる範囲は所轄の警察署に確認する"),
    ("eigyobi", "営業日（例: 平日。土日祝は休み）", "自分で決める"),
    ("contact", "連絡先（問い合わせ用のメールアドレスなど。個人の電話番号は書かない）", "自分で決める"),
    ("form_url", "申込フォームのURL（https:// から）", "kaitori-kit/申込フォーム項目.md の手順で作ったフォームの公開リンク"),
    ("honnin_kakunin", "本人確認の方法（売り手に見せる文）", "所轄の警察署（古物の担当窓口）に、郵送買取で認められる方法を確認して書く"),
    ("honnin_nikaime", "2回目以降のお取引での本人確認の扱い（売り手に見せる文。例: 2回目以降も、お取引のたびに同じ方法で確認します）", "所轄の警察署に確認した内容に合わせて、自分で決める"),
    ("honnin_hiyo", "本人確認の郵便（本人限定受取郵便）の費用の負担（売り手に見せる文。例: 当店が負担します）", "自分で決める"),
    ("miseinen", "未成年の方の扱い（売り手に見せる文）", "所轄の警察署と、都道府県の条例の担当窓口に確認して決める"),
    ("kaitoriritsu", "買取率（%。数字だけ。状態 A の場合）", "自社の数字から決める（kaitori-kit/確認事項.md の 7）"),
    ("jotai_b", "状態 B の買取額（例: 状態 A の買取額の 80%）", "自社の数字から決める"),
    ("soba_name", "基準にする相場の名前（出典は1つに固定する）", "出典側の利用規約で、名前と数字を載せてよいかを確認する"),
    ("soba_hoho", "基準相場の出し方（例: 直近5件の成約価格の中央値）", "自分で決める"),
    ("soba_taishogai", "基準相場を出せない条件（例: 直近30日の成約が3件未満）", "自分で決める"),
    ("taisho_list_url", "対象カードのリストのURL（https:// から）", "自分で作る（10〜30種から）"),
    ("soba_kagen", "対象とする1枚あたり相場の下限（円。数字だけ）", "鑑定の1枚あたり費用から決める"),
    ("min_lot", "最低ロット（例: 仮査定の合計が◯万円以上、かつ対象カード◯枚以上）", "自分で決める"),
    ("soryo", "当店への発送の送料の扱い（例: 当店負担。指定の方法の着払いで）", "自分で決める。配送方法は配送会社の補償の条件を確認する"),
    ("henkyaku_soryo", "返却の送料の扱い（納得できない場合・対象外の品・発送後のキャンセルのそれぞれ）", "自分で決める"),
    ("furikomi_days", "承諾から振込までの営業日数（数字だけ）", "自分で決める"),
    ("furikomi_tesuryo", "振込手数料の扱い（例: 当店が負担します）", "自分で決める"),
    ("saifurikomi_tesuryo", "口座情報の誤りで再振込になったときの手数料の扱い", "自分で決める"),
    ("kigen_karisatei", "申込から仮査定の連絡までの営業日数（数字だけ）", "自分で決める"),
    ("kigen_hasso", "発送のご案内（初回は本人確認の完了後に送る）から発送までの日数（数字だけ）", "自分で決める"),
    ("kigen_kenpin", "到着から検品結果の連絡までの営業日数（数字だけ）", "自分で決める"),
    ("kigen_henshin", "検品結果の連絡から承諾・返却の返信までの日数（数字だけ）", "自分で決める"),
    ("kigen_henkyaku", "返却の確定から返却発送までの営業日数（数字だけ）", "自分で決める"),
    ("jotai.kizu_b", "状態 B: 光を当てると見える線傷の本数（例: 1〜2本）", "自分で決める"),
    ("jotai.shirokake_b", "状態 B: 点状の白かけの数（例: 2か所まで）", "自分で決める"),
    ("jotai.shirokake_c", "状態 C: 白かけの数（例: 3か所以上）", "自分で決める"),
    ("jotai.sori_a", "状態 A: 反りの浮き（例: 1mm 未満）", "自分で決める"),
    ("jotai.sori_b", "状態 B: 反りの浮き（例: 1mm 以上 3mm 未満）", "自分で決める"),
    ("jotai.sori_c", "状態 C: 反りの浮き（例: 3mm 以上）", "自分で決める"),
    ("jotai.center_a", "状態 A: 余白の比（例: 60:40 以内）", "自分で決める"),
    ("jotai.center_b", "状態 B: 余白の比（例: 60:40 を超え 70:30 以内）", "自分で決める"),
    ("jotai.center_c", "状態 C: 余白の比（例: 70:30 を超える）", "自分で決める"),
    ("jotai.hantei", "判定のしかた（例: 白色 LED ライトの下で、肉眼とルーペ(10倍)）", "自分で決める"),
    ("koshinbi", "買取ルールの最終更新日（例: 2026年12月1日）", "ルールを変えた日"),
]
GATE = ("kobutsu_iinkai", "kobutsu_bango", "honnin_kakunin", "form_url")   # これが揃うまで申込ボタンを出さない
INT_KEYS = ("soba_kagen", "furikomi_days", "kigen_karisatei", "kigen_hasso", "kigen_kenpin", "kigen_henshin", "kigen_henkyaku")
URL_KEYS = ("form_url", "taisho_list_url")
# サイトに書かないと決めている言い回し。site.json の値に入っていたら --check が知らせる
NG_WORDS = ("必ず", "絶対", "最高値", "No.1", "No.１", "ナンバーワン", "業界", "PSA", "保証します", "プレゼント", "抽選")


def raw(key):
    """site.json の値を文字列で返す。無い・空なら ""。jotai.kizu_b のように . で入れ子をたどる。"""
    cur = SITE
    for part in key.split("."):
        cur = cur.get(part, "") if isinstance(cur, dict) else ""
    return "" if cur is None or isinstance(cur, (dict, list, bool)) else str(cur).strip()


def num(key):
    """数字の項目を Decimal で返す。空・数字でない・負なら None。"""
    try:
        d = Decimal(raw(key).replace(",", ""))
    except InvalidOperation:
        return None
    return d if d.is_finite() and d >= 0 else None


def is_https(key):
    return bool(re.fullmatch(r"https://[^\s\"'<>]+", raw(key)))


def valid(key):
    """その項目が、ページに出せる値になっているか。"""
    if key in INT_KEYS:
        n = num(key)
        return n is not None and n == n.to_integral_value()
    if key == "kaitoriritsu":
        n = num(key)
        return n is not None and 0 < n <= 100
    if key in URL_KEYS or key == "url":
        return is_https(key)
    return bool(raw(key))


USED = {}   # キー -> そのキーを使ったページのパス。--check で「どのページに準備中が出るか」を示す
_now = [""]


def v(key, fmt="{}"):
    """site.json の値を出す。出せる値でなければ「準備中」。"""
    USED.setdefault(key, [])
    if _now[0] not in USED[key]:
        USED[key].append(_now[0])
    if not valid(key):
        return TBD
    val = raw(key)
    if key in INT_KEYS:
        val = f"{int(num(key)):,}"
    elif key == "kaitoriritsu":
        val = format(num(key).normalize(), "f")
    return e(fmt.format(val))


def link(key, text):
    USED.setdefault(key, [])
    if _now[0] not in USED[key]:
        USED[key].append(_now[0])
    return f'<a href="{e(raw(key))}" rel="noopener">{e(text)}</a>' if valid(key) else f"{e(text)}（{TBD}）"


def contact_html():
    c = raw("contact")
    USED.setdefault("contact", [])
    if _now[0] not in USED["contact"]:
        USED["contact"].append(_now[0])
    if not c:
        return TBD
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", c):
        return f'<a href="mailto:{e(c)}">{e(c)}</a>'
    if re.fullmatch(r"https://[^\s\"'<>]+", c):
        return f'<a href="{e(c)}" rel="noopener">{e(c)}</a>'
    return e(c)


NAME = raw("name") or "未鑑定カードの郵送買取"   # 屋号が空のあいだの表示名
BASE = raw("url").rstrip("/") or DEFAULT_URL
READY = all(valid(k) for k in GATE)
STOPPED = SITE.get("uketsuke_teishi") is True


def kyoka():
    """古物商許可の表示。どちらかが空なら準備中。"""
    for k in ("kobutsu_iinkai", "kobutsu_bango"):
        v(k)
    if valid("kobutsu_iinkai") and valid("kobutsu_bango"):
        return e(f'{raw("kobutsu_iinkai")} {raw("kobutsu_bango")}')
    return TBD


def cta():
    """申込ボタン。許可番号・本人確認の方法・フォームURL が揃うまでは出さない。"""
    for k in GATE:
        v(k)
    if not READY:
        return ('<p class="btn off" id="apply-off">受付準備中</p>'
                '<p class="lead">古物商許可の表示と本人確認の方法の準備ができしだい、受付を始めます。'
                'それまでは、買取ルールと手取りシミュレーターをご覧いただけます。</p>')
    if STOPPED:
        return ('<p class="btn off" id="apply-off">現在、新規の受付を停止しています</p>'
                '<p class="lead">お受けできる件数に達したため、新しいお申し込みを止めています。再開はこのページでお知らせします。</p>')
    return (f'<a class="btn" id="apply" href="{e(raw("form_url"))}" rel="noopener">申込フォームへ</a>'
            '<p class="lead">お申し込みの前に、<a href="/rules/">買取ルール</a>をお読みください。'
            'フォームでは、カードの一覧と写真のリンクをお送りいただきます。</p>')


def yen_floor(soba, pct):
    return int((Decimal(soba) * pct / 100).to_integral_value(rounding=ROUND_FLOOR))


def table(rows, cls=""):
    return f'<table{" class=" + chr(34) + cls + chr(34) if cls else ""}>' + "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in rows) + "</table>"


def grid(head, rows):
    return ('<table class="grid"><tr>' + "".join(f"<th>{h}</th>" for h in head) + "</tr>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>")


NAV = [("simulator/", "手取りシミュレーター"), ("rules/", "買取ルール"), ("condition/", "状態基準"),
       ("flow/", "買取の流れ"), ("faq/", "よくある質問"), ("about/", "運営者情報")]
STEPS = ('<ol class="steps"><li>申込</li><li>仮査定</li><li>本人確認（初回）</li><li>発送</li><li>検品</li>'
         '<li>承諾</li><li>振込</li></ol>')
REI_SOBA_DEFAULT = 30000   # 計算例に使う基準相場。soba_kagen（対象の下限）が未設定のときの値


def rei_soba():
    """計算例・シミュレーターの初期値に使う基準相場。対象の下限（soba_kagen）があればその金額。"""
    n = num("soba_kagen") if valid("soba_kagen") else None
    return int(n) if n else REI_SOBA_DEFAULT


# 本人確認の待ち時間と、基準相場が確定する日の関係（価格を据え置くとは書かない）
SOBA_MACHI = ('基準相場は、カードが当店に届いた日の値で確定します。本人確認の郵便をお待ちいただくあいだに相場が動くことがあり、'
              '仮査定の金額はそのあいだ据え置かれるものではありません。')


def crumbs_html(title):
    return ('<nav aria-label="パンくずリスト"><ol class="crumbs"><li><a href="/">トップ</a></li>'
            f'<li aria-current="page">{e(title)}</li></ol></nav>')


def page(path, title, desc, body, script=False, index=True):
    """共通テンプレート。index=False は検索に載せないページ（404）で、canonical を出さない。"""
    full = f"{title}｜{NAME}" if path else f"{NAME}｜{title}"
    url = f"{BASE}/{path}"
    head = (f'<link rel="canonical" href="{e(url)}">\n<meta property="og:url" content="{e(url)}">' if index
            else '<meta name="robots" content="noindex">')
    _now[0] = path
    foot_kyoka = kyoka()
    nav = "".join(f'<a href="/{p}">{e(t)}</a>' for p, t in NAV)
    return full, desc, f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full)}</title>
<meta name="description" content="{e(desc)}">
{head}
<meta property="og:title" content="{e(title if path else full)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(NAME)}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="{THEME_LIGHT}" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="{THEME_DARK}" media="(prefers-color-scheme: dark)">
<meta name="site-config" content="{STAMP}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/style.css">
</head><body>
<header><a class="brand" href="/">{e(NAME)}</a><nav aria-label="サイト内">{nav}</nav></header>
<main>{crumbs_html(title) if path and index else ""}{body}</main>
<footer>{nav.replace("</a><a", "</a> ・ <a")}<br>
古物商許可: {foot_kyoka}<br>
当店は鑑定会社の公認店・提携店ではありません。状態の区分は当店の基準によるものです。</footer>
{'<script type="module" src="/app.js"></script>' if script else ""}
</body></html>
"""


# ---- 各ページの本文 ---------------------------------------------------------------

def top_body():
    r = num("kaitoriritsu") if valid("kaitoriritsu") else None
    s = rei_soba()
    example = (f'<p class="lead" id="example">例: 基準相場が {s:,}円のカード（状態 A）なら、{s:,}円 × {v("kaitoriritsu")}% ＝ {yen_floor(s, r):,}円。</p>'
               if r is not None else "")
    return (
        '<h1>ポケモンカード未鑑定品の郵送買取</h1>'
        '<p class="lead">鑑定に出していないカード（素体）を、郵送で買い取ります。価格は公開されている相場から式で決まり、お申し込みの前にご自身で計算できます。</p>'
        '<div class="card"><p class="formula">買取額 ＝ 基準相場 × 買取率</p>'
        + table([
            ("買取率", f'{v("kaitoriritsu", "{}%")}（状態 A。状態 B は{v("jotai_b")}）'),
            ("基準相場", f'{v("soba_name")}の{v("soba_hoho")}。カードが当店に届いた日の値で確定します'),
            ("対象", f'{link("taisho_list_url", "対象リスト")}に載っている未鑑定のカードで、1枚あたりの基準相場が{v("soba_kagen", "{}円")}以上のもの'),
            ("対象外", "リストに無いカード、鑑定済みのカード（ケース入り）、状態 C のカード、加工や補修のあるカード"),
            ("最低ロット", v("min_lot")),
            ("送料", v("soryo")),
            ("本人確認", '初回のお取引では、発送の前に、お申し込みのご住所あての本人限定受取郵便をご本人が受け取られたことを確認します'),
            ("お振込", f'承諾のご連絡から{v("furikomi_days", "{}営業日以内")}。振込手数料: {v("furikomi_tesuryo")}'),
        ]) + example + "</div>"
        f'<h2>流れ</h2>{STEPS}'
        '<ul><li>初回のお取引では、仮査定のあとに本人確認を行います。お申し込みのご住所あてに本人限定受取郵便をお送りし、ご本人の受け取りを確認できてから、発送のご案内をします。郵便が届いて受け取られるまで、日数がかかります。</li>'
        f'<li>{SOBA_MACHI}</li></ul>'
        '<p>お申し込み後の金額は仮査定（参考価格）です。検品の結果は1枚ごとに理由を添えてお知らせし、1枚単位で「承諾」か「返却」を選べます。'
        '各段階の期限は<a href="/flow/">買取の流れ</a>に書いています。</p>'
        f'<div class="card">{cta()}</div>'
        '<h2>お申し込みの前に</h2><ul class="tools">'
        '<li><a href="/simulator/"><b>手取りシミュレーター</b><span>フリマで売った場合の手取りと、この買取の手取りを比べます。フリマのほうが多い条件では、そのとおり表示します。</span></a></li>'
        '<li><a href="/rules/"><b>買取ルール</b><span>価格の決め方、対象、減額と返却、送料、お振込、キャンセル、禁止事項。</span></a></li>'
        '<li><a href="/condition/"><b>状態基準と写真の撮り方</b><span>A・B・C の3段階の見分け方と、仮査定に使う写真の撮り方。</span></a></li>'
        '<li><a href="/flow/"><b>買取の流れ</b><span>申込・仮査定・本人確認・発送・検品・承諾・振込。だれが・いつまでに・何をするか。</span></a></li>'
        '<li><a href="/faq/"><b>よくある質問</b><span>減額されたら、返却の送料、相場が動いたら、本人確認の日数、何枚から、など。</span></a></li>'
        '<li><a href="/about/"><b>運営者情報・個人情報の扱い</b><span>古物商許可の表示、連絡先、お預かりする情報の使い道。</span></a></li>'
        "</ul>")


def sim_body():
    r = v("kaitoriritsu")
    rv = f' value="{r}"' if valid("kaitoriritsu") else ""
    rnote = ("" if valid("kaitoriritsu") else
             f'<p class="lead">この買取の買取率は{TBD}です。数字を入れると計算できます。</p>')

    def n(id_, label, value="", mode="numeric", extra=""):
        val = f' value="{value}"' if value != "" else ""
        return f'<label>{label}<input id="{id_}" type="number" inputmode="{mode}" min="0" step="any"{val}{extra}></label>'

    return (
        '<h1>手取りシミュレーター</h1>'
        '<p class="lead">同じカードを、フリマで売った場合と、この買取に出した場合の手取りを比べます。数字はすべて書き換えられます。</p>'
        f'<div class="card" id="sim">{n("soba", "相場価格（円）", rei_soba())}'
        f'<div class="row">{n("tesuryo", "フリマの販売手数料率（%）", 10, "decimal")}{n("fsoryo", "フリマの送料（円）", 210)}</div>'
        f'<label>買取率（%）<input id="ritsu" type="number" inputmode="decimal" min="0" step="any"{rv}></label>{rnote}'
        '<details><summary>買取で、ご自身が負担する費用がある場合</summary>'
        f'<div class="row">{n("usoryo", "買取で負担する送料（円）", 0)}{n("ufuri", "買取で負担する振込手数料（円）", 0)}</div></details></div>'
        '<div class="card" id="result" aria-live="polite"><p>相場価格と買取率を入れると計算します。</p></div>'
        '<h2>計算の式</h2><ul>'
        '<li>フリマの手取り ＝ 相場 − 販売手数料（相場 × 手数料率、1円未満切り捨て） − フリマの送料</li>'
        '<li>この買取の手取り ＝ 買取額（相場 × 買取率、1円未満切り捨て） − ご自身が負担する送料 − ご自身が負担する振込手数料</li>'
        '<li>手取りが同じになる買取率 ＝（フリマの手取り ＋ ご自身が負担する送料・振込手数料）÷ 相場</li></ul>'
        '<p>買取率が「手取りが同じになる買取率」より低いときは、フリマで売るほうが手取りは多くなります。'
        'その場合は、結果の欄にそのとおり表示します。</p>'
        '<h2>初期値について</h2>'
        f'<p>相場価格の初期値（{rei_soba():,}円）は、'
        + (f'この買取の対象になる1枚あたりの基準相場の下限です（対象: {v("soba_kagen", "{}円")}以上）。' if valid("soba_kagen") and num("soba_kagen")
           else f'一例です（対象とする基準相場の下限は{v("soba_kagen")}）。') +
        '販売手数料率 10%・送料 210円は一例です。手数料率と送料は、お使いのサービスと発送方法で変わります。お使いのサービスの表示で確かめて書き換えてください。'
        f'この買取の送料の扱いは「{v("soryo")}」、振込手数料の扱いは「{v("furikomi_tesuryo")}」です。ご自身の負担がある場合は、上の欄を開いて金額を入れてください。</p>'
        '<h2>この計算に入っていないもの</h2><ul>'
        '<li>フリマで売れるまでの日数、値下げの交渉、梱包材の費用、売上金を引き出すときの手数料</li>'
        f'<li>状態 B になった場合の減額（状態 B は{v("jotai_b")}）</li>'
        '<li>仮査定からカードが届く日までの相場の動き（買取額は到着日の基準相場で確定します。初回は本人確認の郵便を待つ日数が加わります）</li>'
        '<li>フリマでは相場どおりの価格で売れるものとして計算しています</li></ul>'
        '<p>結果は入力した数字をそのまま計算した参考値です。入力内容は外部に送信されません。</p>')


def jotai_rows():
    """状態基準。項目ごとに (項目, A, B, C)。"""
    return [
        ("表面の傷", "光を当てて傾けても線傷が見えない",
         f'光を当てると見える線傷が{v("jotai.kizu_b")}。爪で引っかからない', "正面から見える傷、爪で引っかかる傷、へこみ"),
        ("裏面の白かけ", "四隅・四辺に白かけが見えない",
         f'点状の白かけが{v("jotai.shirokake_b")}', f'白かけが{v("jotai.shirokake_c")}、または線状の白かけ'),
        ("角", "4つの角がつぶれていない", "角1つにわずかな丸まり", "角のつぶれ、めくれ、はがれ"),
        ("反り", f'平らな台に置いて浮きが{v("jotai.sori_a")}', f'浮きが{v("jotai.sori_b")}', f'浮きが{v("jotai.sori_c")}、折れ、波打ち'),
        ("センタリング", f'表面の左右・上下の余白の比が{v("jotai.center_a")}', v("jotai.center_b"), v("jotai.center_c")),
        ("汚れ・印刷", "汚れ、指紋の跡、印刷のずれ・線が見えない", "拭いて取れない小さな汚れ、小さな印刷線が1か所",
         "水ぬれ跡、変色、におい、書き込み、シールの跡"),
    ]


PHOTO = ('<ol><li>表面の全体（真上から。カード全体と四辺の余白が写るように）</li>'
         '<li>裏面の全体（真上から。暗い色の無地の台に置くと白かけが見やすくなります）</li>'
         '<li>表面を斜めから（照明を反射させて、傷が見える角度で1枚）</li>'
         '<li>気になる箇所があれば、その拡大</li></ol>'
         '<ul><li>スリーブやローダーから出して撮影してください（反射で傷が見えなくなるため）。</li>'
         '<li>加工アプリやフィルターは使わないでください。</li>'
         '<li>明るい場所で、影がカードにかからないようにしてください。</li></ul>')


def jotai_tables():
    return "".join(f'<h3>{e(k)}</h3>' + table([("A", a), ("B", b), ("C", c)]) for k, a, b, c in jotai_rows())


def condition_body():
    return (
        '<h1>状態基準と写真の撮り方</h1>'
        '<p class="lead">状態は当店の基準で A・B・C の3段階に分けます。鑑定会社の基準とは別のもので、鑑定の結果を予測したり保証したりするものではありません。</p>'
        + table([("A", f'買取率どおり（{v("kaitoriritsu", "{}%")}）'), ("B", f'減額（{v("jotai_b")}）'), ("C", "買い取れません。返却します")])
        + '<h2>項目ごとの基準</h2>' + jotai_tables()
        + '<ul><li>1枚の中で項目ごとに区分が違う場合は、いちばん低い区分をそのカードの状態とします。</li>'
        f'<li>判定のしかた: {v("jotai.hantei")}</li>'
        '<li>検品の結果は、1枚ごとに状態区分・確定額・理由（該当箇所の写真つき）をお知らせします。納得できないカードは1枚単位で返却を選べます。</li></ul>'
        '<h2>写真の撮り方（お申し込み時）</h2>'
        '<p>仮査定を実際の検品結果に近づけるため、1枚につき次の写真をお願いします。</p>' + PHOTO
        + '<p>気になる点（傷、白かけ、反りなど）は、フォームの欄に書いてください。申告があれば仮査定に反映でき、検品後の行き違いが減ります。</p>')


def rules_body():
    r = num("kaitoriritsu") if valid("kaitoriritsu") else None
    example = (
        '<h3>計算例</h3>' + table([("基準相場", f"{rei_soba():,}円"), ("買取率", f'{v("kaitoriritsu")}%'),
                                 ("買取額（状態 A）", f"{yen_floor(rei_soba(), r):,}円")])
        if r is not None else f'<p>計算例は、買取率が決まりしだい載せます（{TBD}）。</p>')
    return (
        '<h1>買取ルール</h1>'
        f'<p class="lead">お申し込みの前にお読みください。最終更新日: {v("koshinbi")}</p>'
        '<h2 id="price">1. 価格の決め方</h2>'
        '<p>買取額は次の式で決まります。お申し込みの前に、ご自身で計算できます。</p>'
        '<div class="card"><p class="formula">買取額 ＝ 基準相場 × 買取率</p><p class="lead">1円未満は切り捨てます。</p></div>'
        f'<ul><li><b>基準相場</b>: {v("soba_name")}に掲載されている、同じカード（同じ型番・同じレアリティ・未鑑定）の{v("soba_hoho")}。</li>'
        f'<li><b>買取率</b>: {v("kaitoriritsu", "{}%")}（状態 A の場合）。状態 B は{v("jotai_b")}。</li>'
        f'<li>基準相場を出せないカード（{v("soba_taishogai")}）は、買取の対象外です。</li></ul>'
        + example +
        '<p>フリマで売った場合の手取りとの比較は、<a href="/simulator/">手取りシミュレーター</a>で計算できます。</p>'
        '<h3>見積と確定の違い</h3>'
        '<ul><li>お申し込み後にお伝えする金額は<b>仮査定（参考価格）</b>です。</li>'
        '<li>買取額は、<b>カードが当店に到着した日の基準相場</b>で計算し直して確定します。相場が動いた場合、確定額は仮査定より高くなることも低くなることもあります。</li>'
        '<li>初回のお取引では、仮査定のあと、本人確認（7. 参照）が済んでから発送のご案内をします。その待ち時間のあいだに相場が動くことがあり、仮査定の金額はそのあいだ据え置かれるものではありません。</li>'
        '<li>確定額にご納得いただけない場合は、1枚単位で返却を選べます（5. 参照）。</li></ul>'
        '<h2 id="target">2. 対象カードと対象外</h2>'
        f'<p>買い取るのは、{link("taisho_list_url", "対象リスト")}に載っている未鑑定のカードで、1枚あたりの基準相場が{v("soba_kagen", "{}円")}以上のものだけです。お申し込みの日のリストを適用します。</p>'
        '<p>対象外の例:</p><ul><li>対象リストに無いカード</li><li>鑑定済みのカード（ケース入り）</li>'
        f'<li>1枚あたりの基準相場が{v("soba_kagen", "{}円")}に満たないカード</li>'
        '<li>状態 C にあたるカード（4. 参照）</li><li>禁止事項にあたる品（12. 参照）</li></ul>'
        '<p>対象外のカードは買い取れません。同梱された場合は返却します（送料は 6. 参照）。</p>'
        '<h2 id="lot">3. 最低ロット</h2>'
        f'<p>1回のお申し込みは、次の条件からお受けします: {v("min_lot")}</p>'
        '<h2 id="condition">4. 状態基準</h2>'
        '<p>状態は当店の基準で A・B・C の3段階に分けます。鑑定会社の基準とは別のもので、鑑定の結果を予測したり保証したりするものではありません。'
        '項目ごとの基準と写真の撮り方は、<a href="/condition/">状態基準と写真の撮り方</a>に書いています。</p>'
        + table([("A", "買取率どおり"), ("B", f'減額（{v("jotai_b")}）'), ("C", "買取不可・返却")]) +
        '<p>1枚の中で項目ごとに区分が違う場合は、いちばん低い区分をそのカードの状態とします。</p>'
        '<h2 id="return">5. 減額と返却</h2>'
        '<ul><li>検品の結果は、<b>1枚ごとに</b>状態区分・確定額・理由（該当箇所の写真つき）をお知らせします。</li>'
        '<li>お客様は<b>1枚単位で「承諾」か「返却」</b>を選べます。全部を返却することもできます。</li>'
        f'<li>ご返信の期限は、検品結果のご連絡から{v("kigen_henshin", "{}日")}です。期限の前日に一度ご連絡します。期限を過ぎてもご返信が無い場合は、全点を返却します。</li>'
        '<li>承諾の後は、買取が成立します。成立後の取り消しはできません。</li></ul>'
        '<h2 id="shipping">6. 送料</h2>'
        + table([("当店への発送", v("soryo")), ("返却", v("henkyaku_soryo"))]) +
        '<ul><li>発送は、追跡ができて補償のある方法をお願いします。</li>'
        '<li>梱包: カードは1枚ずつスリーブとローダー（または同等の硬いケース）に入れ、水ぬれ防止の袋に入れてください。</li>'
        '<li>輸送中の事故（紛失・破損）は、配送会社の補償の範囲で対応します。当店に到着するまでの管理はお客様にお願いします。</li></ul>'
        '<h2 id="id">7. 本人確認</h2>'
        '<p>古物営業法にもとづき、お取引の前に本人確認を行います。初回のお取引では、仮査定のあと、カードを発送していただく前に行います。</p>'
        f'<ul><li>方法: {v("honnin_kakunin")}</li>'
        '<li>お申し込みのご住所とお名前は、本人確認書類と同じ表記でご記入ください。表記が違うと、郵便を受け取れないことがあります。</li>'
        '<li>郵便が届いて受け取られるまで、日数がかかります。受け取りを当店で確認できるまで、発送のご案内（発送先・方法・期限）には進みません。</li>'
        f'<li>2回目以降のお取引: {v("honnin_nikaime")}</li>'
        f'<li>本人確認の郵便の費用: {v("honnin_hiyo")}</li>'
        '<li>確認ができない場合、買取はできません。</li><li>お振込先は、ご本人名義の口座に限ります。</li></ul>'
        '<h2 id="minor">8. 未成年の方</h2>'
        f'<p>{v("miseinen")}</p>'
        '<h2 id="payment">9. お振込</h2>'
        f'<ul><li>期限: 承諾のご連絡をいただいてから{v("furikomi_days", "{}営業日以内")}に振り込みます。</li>'
        f'<li>振込手数料: {v("furikomi_tesuryo")}</li>'
        f'<li>口座情報の誤りで振込ができなかった場合の再振込の手数料: {v("saifurikomi_tesuryo")}</li></ul>'
        '<h2 id="cancel">10. キャンセル</h2>'
        + table([("発送の前", "いつでも可能です。ご連絡ください"),
                 ("本人確認の郵便をお送りした後、発送の前", "可能です。ご連絡ください"),
                 ("発送の後、検品結果のご連絡の前", "可能です。返送の送料は 6. の「返却」のとおりです"),
                 ("検品結果のご連絡の後、承諾の前", "1枚単位で返却を選べます（5. 参照）"),
                 ("承諾の後", "できません")]) +
        f'<p>発送のご案内（初回は本人確認が済んだあとにお送りします）から{v("kigen_hasso", "{}日")}以内に発送のご連絡が無い場合、お申し込みは取り消しとなります。あらためてお申し込みください。</p>'
        '<h2 id="privacy">11. 個人情報の扱い</h2>'
        '<p><a href="/about/#privacy">運営者情報・個人情報の扱い</a>に書いています。</p>'
        '<h2 id="ng">12. 禁止事項</h2>'
        '<p>次の品は買い取れません。お申し込み・同梱はご遠慮ください。</p>'
        '<ul><li>偽造品、複製品、その疑いがある品</li><li>盗品、拾得物、ご本人の所有でない品</li>'
        '<li>加工・補修された品（色を塗る、角を切る・削る、プレスする、表面を磨く、クリーニング剤を使う など）</li>'
        '<li>再シュリンクした品、開封済みを未開封と表示した品</li><li>申込内容と異なる品を意図して送ること</li></ul>'
        '<p>これらにあたる、またはその疑いがあると当店が判断した場合、買取をお断りします。法令にもとづき、警察に届け出ることがあります。</p>'
        '<h2 id="other">13. その他</h2>'
        '<ul><li>当店は鑑定会社の公認店・提携店ではありません。カードの状態区分は当店の基準によるもので、鑑定の結果を保証するものではありません。</li>'
        '<li>このルールを変更する場合は、このページで更新日とともにお知らせします。お取引には、お申し込みの時点のルールを適用します。</li>'
        '<li>買取額の個別の交渉はお受けしていません。価格は 1. の式で決まります。</li></ul>'
        f'<div class="card">{cta()}</div>')


def flow_body():
    steps = [
        ("1. 申込（お客様）", "申込フォームから、お名前・ご住所、カードの一覧（カード名・型番・枚数・ご自身で見た状態）と、写真の共有リンクを送ります。"
         'ご住所とお名前は、本人確認書類と同じ表記でご記入ください（本人確認の郵便をお送りする宛先になります）。'
         '写真の撮り方は<a href="/condition/">状態基準</a>をご覧ください。口座情報は、この段階ではお聞きしません。', "期限: なし"),
        ("2. 仮査定の連絡（当店）", "対象リストと照らし合わせ、写真から見た状態で仮査定（参考価格）をお知らせします。対象外の場合はその旨をお知らせします。"
         "お進みになる場合は、その旨をご返信ください。",
         f'期限: お申し込みから{v("kigen_karisatei", "{}営業日以内")}'),
        ("3. 本人確認（初回のお取引）", "お進みになる旨のご返信をいただいたら、お申し込みのご住所あてに本人限定受取郵便をお送りします。郵便局からの通知に従って、ご本人がお受け取りください。"
         "郵便が届いて受け取られるまで、日数がかかります。受け取りを当店で確認できるまで、発送のご案内には進みません。カードはまだ送らないでください。"
         f'<br>2回目以降のお取引: {v("honnin_nikaime")}<br>本人確認の郵便の費用: {v("honnin_hiyo")}',
         "期限: 郵便局での保管の期間内にお受け取りください。受け取りを確認できない場合、買取の手続きには進めません"),
        ("4. 発送（お客様）", f'受け取りを確認できたら、発送のご案内（発送先・方法・期限）をお送りします。ご案内に沿ってカードを発送してください。送料の扱い: {v("soryo")}。'
         f'{SOBA_MACHI}',
         f'期限: 発送のご案内から{v("kigen_hasso", "{}日以内")}。過ぎた場合、お申し込みは取り消しとなります'),
        ("5. 検品（当店）", "届いた日の基準相場で買取額を計算し直し、1枚ごとに状態区分・確定額・理由（該当箇所の写真つき）をお知らせします。到着したことは、届いた翌営業日までにお知らせします。",
         f'期限: 到着から{v("kigen_kenpin", "{}営業日以内")}'),
        ("6. 承諾または返却（お客様）", "1枚単位で「承諾」か「返却」を選んでご返信ください。承諾の後は買取が成立し、取り消しはできません。お振込先はこのときにお聞きします（ご本人名義の口座）。",
         f'期限: 検品結果のご連絡から{v("kigen_henshin", "{}日以内")}。期限の前日に一度ご連絡します。ご返信が無い場合は全点を返却します'),
        ("7. 振込（当店）", f'承諾いただいたカードの確定額を振り込み、振込のご連絡をします。振込手数料: {v("furikomi_tesuryo")}',
         f'期限: 承諾のご連絡から{v("furikomi_days", "{}営業日以内")}'),
    ]
    return (
        '<h1>買取の流れ</h1>'
        f'<p class="lead">申込から振込まで、だれが・いつまでに・何をするかをまとめました。営業日: {v("eigyobi")}</p>{STEPS}'
        '<ol class="flow" style="list-style:none;padding:0">'
        + "".join(f'<li class="card" id="step{i}"><b>{e(t)}</b>{d}<br><span class="lead">{k}</span></li>' for i, (t, d, k) in enumerate(steps, 1)) + "</ol>"
        '<h2>返却がある場合</h2>'
        f'<p>返却を選ばれたカードは、返却の確定から{v("kigen_henkyaku", "{}営業日以内")}に発送します。返却の送料の扱い: {v("henkyaku_soryo")}</p>'
        '<h2>ご連絡について</h2>'
        '<p>ご連絡は、段階ごとに決まった文面でお送りします。期限に間に合わない見込みのときは、期限の前にその旨をお知らせします。</p>'
        f'<div class="card">{cta()}</div>')


def faq_rei():
    """よくある質問に入れる計算例（買取率が決まっているときだけ）。"""
    if not valid("kaitoriritsu"):
        return ""
    s = rei_soba()
    return f'たとえば基準相場が {s:,}円なら、{s:,}円 × {v("kaitoriritsu")}% ＝ {yen_floor(s, num("kaitoriritsu")):,}円です。'


def faq_items():
    return [
        ("何枚から申し込めますか？", f'最低ロットは次のとおりです: {v("min_lot")}。対象は、{link("taisho_list_url", "対象リスト")}に載っていて、1枚あたりの基準相場が{v("soba_kagen", "{}円")}以上のカードです。'),
        ("買取額はどうやって決まりますか？", f'「基準相場 × 買取率」で決まります（1円未満切り捨て）。基準相場は{v("soba_name")}の{v("soba_hoho")}、買取率は状態 A で{v("kaitoriritsu", "{}%")}です。{faq_rei()}個別の交渉はお受けしていません。'),
        ("申し込んだあとに相場が動いたら、どうなりますか？", "お申し込み後にお伝えする金額は仮査定（参考価格）です。買取額は、カードが当店に届いた日の基準相場で計算し直して確定します。確定額は仮査定より高くなることも低くなることもあります。初回のお取引では、本人確認の郵便をお待ちいただくあいだにも相場が動くことがあり、仮査定の金額はそのあいだ据え置かれるものではありません。納得できない場合は、1枚単位で返却を選べます。"),
        ("検品で減額されたら、どうなりますか？", f'1枚ごとに、状態区分・確定額・理由（該当箇所の写真つき）をお知らせします。1枚単位で「承諾」か「返却」を選べます。全部を返却することもできます。状態 B の買取額は{v("jotai_b")}、状態 C は買い取れません。'),
        ("返却してもらう場合の送料は、どちらが負担しますか？", f'返却の送料の扱いは次のとおりです: {v("henkyaku_soryo")}'),
        ("送るときの送料は、どちらが負担しますか？", f'当店への発送の送料の扱いは次のとおりです: {v("soryo")}。追跡ができて補償のある方法でお送りください。'),
        ("未成年でも申し込めますか？", v("miseinen")),
        ("本人確認は、どのように行いますか？", f'古物営業法にもとづき、お取引の前に本人確認を行います。方法: {v("honnin_kakunin")} 初回のお取引では、仮査定のあと、カードを発送していただく前に行います。お申し込みのご住所とお名前は、本人確認書類と同じ表記でご記入ください。'),
        ("本人確認には、どのくらい日数がかかりますか？", '郵便が届いて、ご本人が受け取られるまでの日数がかかります（日数は、お住まいの地域と受け取りのご都合で変わります）。受け取りを当店で確認できるまで、発送のご案内には進みませんので、カードはまだ送らないでください。受け取りを確認できない場合、買取の手続きには進めません。'),
        ("2回目以降の取引でも、本人確認の郵便を受け取る必要がありますか？ 郵便の費用はどちらが負担しますか？", f'2回目以降のお取引の扱い: {v("honnin_nikaime")}。本人確認の郵便の費用: {v("honnin_hiyo")}'),
        ("振込はいつですか？ 手数料はかかりますか？", f'承諾のご連絡をいただいてから{v("furikomi_days", "{}営業日以内")}に振り込みます。振込手数料の扱い: {v("furikomi_tesuryo")}。お振込先はご本人名義の口座に限ります。'),
        ("対象リストに無いカードも、一緒に送っていいですか？", "対象リストに無いカードは買い取れません。同梱された場合は返却します。送料の扱いは「返却してもらう場合の送料」の項をご覧ください。"),
        ("鑑定に出せば高い評価が付きそうなカードは、高く買ってもらえますか？", "買取額は式のとおりで、鑑定の結果の見込みでは変わりません。当店の状態区分（A・B・C）は当店の基準によるもので、鑑定の結果を予測したり保証したりするものではありません。"),
        ("フリマで売るのと、どちらが手取りが多いですか？", '条件によって変わります。<a href="/simulator/">手取りシミュレーター</a>に、相場、お使いのフリマの手数料率と送料を入れて比べてください。フリマのほうが手取りが多い条件では、そのとおり表示します。'),
        ("申し込んだあとにキャンセルできますか？", '発送の前は、本人確認の郵便をお送りした後でも、いつでもできます。発送の後も、承諾の前までは返却を選べます（返送の送料の扱いは上の項のとおり）。承諾の後はできません。くわしくは<a href="/rules/#cancel">買取ルールの 10.</a> をご覧ください。'),
        ("このページに載っていないことを聞きたいときは？", f'<a href="/rules/">買取ルール</a>と<a href="/flow/">買取の流れ</a>もあわせてご覧ください。それでも分からないことは、こちらへご連絡ください: {contact_html()}（営業日: {v("eigyobi")}）'),
    ]


def faq_body():
    return ('<h1>よくある質問</h1><p class="lead">お申し込みの前によくいただく質問をまとめました。質問を押すと答えが開きます。</p>'
            + "".join(f"<details><summary>{e(q)}</summary><p>{a}</p></details>" for q, a in faq_items())
            + f'<div class="card">{cta()}</div>')


def about_body():
    return (
        '<h1>運営者情報・個人情報の扱い</h1>'
        '<h2>運営者</h2>'
        + table([("屋号", v("name")), ("古物商許可", kyoka()), ("所在地", v("shozaichi")),
                 ("連絡先", contact_html()), ("営業日", v("eigyobi"))]) +
        '<p>当店は鑑定会社の公認店・提携店ではありません。</p>'
        '<h2 id="privacy">個人情報の扱い</h2>'
        '<ul><li>いただいた情報（氏名、住所、連絡先、生年月日、職業、口座情報、本人確認の記録）は、買取のお取引、法令で定められた記録、お問い合わせへの対応のために使います。</li>'
        '<li>法令にもとづく場合を除き、ご本人の同意なく第三者に提供しません。</li>'
        '<li>法令で定められた期間、取引の記録を保存します。</li>'
        '<li>お客様の氏名・アカウント名・金額・カードの組み合わせなど、個人が特定される情報を公開することはありません。</li>'
        f'<li>開示・訂正・削除のご希望は、こちらへご連絡ください: {contact_html()}</li></ul>'
        '<h2>お聞きする情報と、その段階</h2>'
        + table([("お申し込みのとき", "メールアドレス、氏名とフリガナ、ご住所（本人確認の郵便をお送りする宛先）、カードの一覧と写真、入手の経緯"),
                 ("仮査定のあと、発送の前", "生年月日、職業、本人確認の郵便を受け取られたことの確認"),
                 ("承諾のとき", "お振込先（ご本人名義の口座）")]) +
        '<p>買取が成立しない場合に要らない情報は、その段階になるまでお聞きしません。</p>'
        '<h2>このサイトについて</h2>'
        '<p>手取りシミュレーターに入力した数字は、お使いのブラウザの中だけで計算され、当サイトには送信・保存されません。'
        'このサイトは、アクセス解析や広告のための Cookie を使っていません。お申し込みは外部のフォームサービスで受け付けます。</p>')


def not_found_body():
    return ('<h1>ページが見つかりません</h1><p>お探しのページは、移動または削除されたか、URLが間違っている可能性があります。</p>'
            '<a class="btn" href="/">トップへ</a><ul class="tools">'
            + "".join(f'<li><a href="/{p}"><b>{e(t)}</b></a></li>' for p, t in NAV) + "</ul>")


PAGES = [   # (パス, title, description, 本文を作る関数, シミュレーターのスクリプトを読むか, 検索に載せるか)
    ("", "ポケモンカード未鑑定品の郵送買取", "ポケモンカードの未鑑定品（素体）を郵送で買い取ります。買取額は公開相場×買取率。対象・最低ロット・振込までの日数と、申込から振込までの流れを1ページにまとめました。", top_body, False, True),
    ("simulator/", "手取りシミュレーター（フリマと買取の比較）", "相場・フリマの販売手数料率と送料・買取率を入れると、フリマで売った場合の手取りと、この買取の手取り、差額を計算します。フリマのほうが多い条件ではそのとおり表示します。", sim_body, True, True),
    ("rules/", "買取ルール", "郵送買取のルールです。価格の決め方（基準相場×買取率）、見積と確定の違い、対象と対象外、最低ロット、減額と返却、送料、本人確認、お振込、キャンセル、禁止事項。", rules_body, False, True),
    ("condition/", "状態基準と写真の撮り方", "未鑑定カードの状態を A・B・C の3段階に分ける当店の基準（傷・白かけ・角・反り・センタリング・汚れ）と、仮査定に使う写真の撮り方です。", condition_body, False, True),
    ("flow/", "買取の流れと期限", "申込 → 仮査定 → 本人確認（初回）→ 発送 → 検品 → 承諾 → 振込。郵送買取の各段階で、だれが・いつまでに・何をするかと、返却がある場合の進み方をまとめました。", flow_body, False, True),
    ("faq/", "よくある質問", "郵送買取についてのよくある質問です。減額されたら、返却の送料、相場が動いたら、未成年の申込、何枚から、本人確認の方法と日数、振込の時期、キャンセルなど。", faq_body, False, True),
    ("about/", "運営者情報・個人情報の扱い", "運営者の屋号・古物商許可の表示・所在地・連絡先と、お取引でお聞きする個人情報の使い道、お聞きする段階をまとめています。", about_body, False, True),
    ("404.html", "ページが見つかりません", "お探しのページは見つかりませんでした。トップからお探しください。", not_found_body, False, False),
]


def render():
    """全ページを {パス: HTML} で返す（ファイルには書かない）。title・description の空と重複はここで止める。"""
    USED.clear()
    out, seen_t, seen_d = {}, {}, {}
    for path, title, desc, body_fn, script, index in PAGES:
        _now[0] = path
        full, desc, text = page(path, title, desc, body_fn(), script, index)
        for name, val, seen in (("title", full, seen_t), ("description", desc, seen_d)):
            if not val.strip() or val in seen:
                raise SystemExit(f"{name} が空か重複しています: /{path}" + (f" と /{seen[val]}" if val in seen else ""))
            seen[val] = path
        out[path] = text
    return out


def favicon_svg():
    """角丸の四角に「＝」（式で決まる、の意）。外部ファイルを使わず、ここで生成する。"""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="{ACCENT}"/>'
            f'<rect x="16" y="21" width="32" height="8" rx="4" fill="{THEME_LIGHT}"/>'
            f'<rect x="16" y="35" width="32" height="8" rx="4" fill="{THEME_LIGHT}"/></svg>\n')


def check():
    """公開前に直す項目を [(区分, 文)] で返す。区分は「受付に必要」「要対応」。"""
    render()
    gate, must = [], []
    for key, what, where in KEYS:
        pages = "、".join("/" + p for p in USED.get(key, [])) or "—"
        if key == "url":
            if not is_https("url"):
                must.append(f"url: https:// で始まる公開URLを書いてください。｜{where}")
            elif "example.com" in BASE:
                must.append(f"url: 初期値（{BASE}）のままです。canonical・sitemap.xml・robots.txt に使われます。｜{where}")
            elif "/" in BASE[len("https://"):]:
                must.append(f"url: パスが含まれています（{BASE}）。robots.txt と 404.html はドメイン直下に置く前提です。")
            continue
        if valid(key):
            if key in URL_KEYS and "example.com" in raw(key):
                must.append(f"{key}: 仮のURL（{raw(key)}）のままです。｜{where}")
            continue
        state = "未記入" if not raw(key) else f"書き方が違います（{raw(key)}）"
        line = f"{key}: {state}。{what}｜決め方・確認先: {where}｜準備中と出るページ: {pages}"
        (gate if key in GATE else must).append(line)
    for key, *_ in KEYS:
        hit = [w for w in NG_WORDS if w in raw(key)]
        if hit:
            must.append(f"{key}: サイトに書かないと決めている言い回し（{'、'.join(hit)}）が入っています。")
    if STOPPED:
        must.append("uketsuke_teishi が true です。申込ボタンの代わりに「現在、新規の受付を停止しています」と表示されます。")
    built = OUT / "index.html"
    if not built.is_file():
        must.append("public/ がまだ生成されていません。python build.py を実行してください。")
    elif f'<meta name="site-config" content="{STAMP}">' not in built.read_text(encoding="utf-8"):
        must.append("public/ がいまの site.json から生成されていません。python build.py を実行し直してください。")
    return [("受付に必要", m) for m in gate] + [("要対応", m) for m in must]


def print_check():
    items = check()
    gate = sum(k == "受付に必要" for k, _ in items)
    print(f"公開前に直す項目: {len(items)} 件（うち、申込ボタンを出すのに必要な項目 {gate} 件）。site.json を直して python build.py")
    print(f"申込ボタン: {'受付停止中の表示' if READY and STOPPED else '表示される' if READY else '出ない（「受付準備中」と表示）'}")
    for k, m in items:
        print(f"  [{k}] {m}")
    if not items:
        print("  公開前に直す項目はありません。")


def main():
    pages = render()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for f in ("style.css", "tejori.js", "app.js"):
        shutil.copy(ROOT / "src" / f, OUT / f)
    (OUT / "favicon.svg").write_text(favicon_svg(), encoding="utf-8")
    for path, text in pages.items():
        target = OUT / path if path.endswith(".html") else OUT / path / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    urls = [p for p, *_, index in PAGES if index]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{e(BASE)}/{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    print(f"{len(pages)} ページ（404 を含む）を {OUT} に生成しました。申込ボタン: "
          f"{'受付停止中の表示' if READY and STOPPED else 'あり' if READY else 'なし（受付準備中）'}")
    n = len(check())
    if n:
        print(f"公開前に直す項目が {n} 件あります。一覧は python build.py --check")


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        print_check()
    else:
        main()
