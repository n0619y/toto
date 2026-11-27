"""autofill.js からブックマークレットと、スマホ用の手順ページ (page.html) を作る。  python pokeca/psa/build_page.py"""

import html
import re
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
src = (HERE / "autofill.js").read_text(encoding="utf-8")
code = "\n".join(line for line in src.splitlines() if not line.strip().startswith("//"))
code = re.sub(r"\n\s+", "\n", code).strip()
bookmarklet = "javascript:" + urllib.parse.quote(code, safe="()=>;:,.!?*'[]{}+-/&|<~")

PAGE = """<title>PSA入力アシスト</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* 1カラムの手順書。上から順に「初回の登録 → 毎回のリスト作り → PSAで実行」 */
:root{--bg:#f6f7f9;--card:#ffffff;--fg:#16202b;--mut:#5a6878;--line:#d6dce4;--accent:#c8102e;--ok:#0f7a4f;--code:#eef1f5;
  --body:"Inter",system-ui,"Hiragino Sans","Noto Sans JP",sans-serif;--head:"Space Grotesk","Inter",system-ui,sans-serif;--mono:ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11161c;--card:#1a2129;--fg:#e8edf2;--mut:#9aa8b8;--line:#2e3945;--accent:#ff5a73;--ok:#4fd19c;--code:#232c36;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#11161c;--card:#1a2129;--fg:#e8edf2;--mut:#9aa8b8;--line:#2e3945;--accent:#ff5a73;--ok:#4fd19c;--code:#232c36;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--body);font-size:16px;line-height:1.75;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:24px 48px}
main{max-width:640px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
h1{font-family:var(--head);font-size:1.6rem;line-height:1.25;margin:0;text-wrap:balance}
h2{font-family:var(--head);font-size:1.1rem;margin:0 0 6px;text-wrap:balance}
p{margin:0}.lead{color:var(--mut)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;display:flex;flex-direction:column;gap:12px;min-width:0}
.step{font-family:var(--head);font-size:.75rem;letter-spacing:.08em;color:var(--accent);font-weight:700}
ol{margin:0;padding-left:1.3em;display:flex;flex-direction:column;gap:6px}
textarea,.out{font-family:var(--mono);font-size:.9rem;background:var(--code);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:10px;width:100%;box-sizing:border-box}
textarea{min-height:130px}.out{overflow-wrap:anywhere;min-height:2.6em}
#bm{max-height:5.5em;overflow:auto;font-size:.7rem;color:var(--mut)}
button{font:inherit;font-weight:700;background:var(--accent);color:var(--card);border:0;border-radius:8px;padding:12px 16px;cursor:pointer}
button:focus-visible,textarea:focus-visible{outline:3px solid var(--ok);outline-offset:2px}
.done{color:var(--ok);font-weight:700;min-height:1.5em}
.note{color:var(--mut);font-size:.9rem}
code{font-family:var(--mono);background:var(--code);padding:1px 5px;border-radius:4px}
</style>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Space+Grotesk:wght@700&display=swap">
<main>
<header><h1>PSA入力アシスト</h1>
<p class="lead">PSAの「Enter Items」画面で、カードの検索・選択・枚数入力・Saveを順番に自動で行います。Proceed to Checkout と Place Order、規約のチェックは押しません。</p></header>

<section><div class="step">初回だけ</div><h2>ブックマークに登録する(Android の Chrome)</h2>
<ol><li>下のボタンでコードをコピーする。</li>
<li>Chrome で適当なページを開き、メニュー(⋮)の ☆ でブックマークに追加する。</li>
<li>メニュー → ブックマーク → いま追加したものの「編集」を開く。</li>
<li>名前を <code>psa</code> に、URL を消してコピーしたコードを貼り付けて保存する。</li></ol>
<button id="copyBm" type="button">コードをコピー</button><div class="done" id="bmDone" role="status"></div>
<div class="out" id="bm">__BOOKMARKLET__</div></section>

<section><div class="step">毎回 1</div><h2>入力リストを作る</h2>
<p>1行に1種類。「セット記号 カード番号 x枚数」の順で書きます。記号と番号はカード左下に印刷されています。枚数が1なら省略できます。</p>
<textarea id="list" aria-label="入力リスト">M3 061
M3 045 x2
M6a 012</textarea>
<button id="copyList" type="button">リストをコピー</button><div class="done" id="listDone" role="status"></div>
<div class="out" id="line" aria-live="polite"></div>
<p class="note">上の3行は記入例です。消して自分のカードを書いてください。</p></section>

<section><div class="step">毎回 2</div><h2>PSAの画面で実行する</h2>
<ol><li>PSAで Start Submission → Grade with PSA → Classic Submission → Trading Cards → Grading → プランを選び、「Enter Items」まで進む。</li>
<li>アドレスバーをタップして <code>psa</code> と打ち、候補に出る ☆ 付きの「psa」をタップする。</li>
<li>出てきた入力欄にリストを貼り付けて OK を押す。</li>
<li>終わると「追加 ◯件 / 飛ばした ◯件」と表示される。飛ばしたカードは手で入力する。</li>
<li>一覧と枚数を確認してから、自分で Proceed to Checkout に進む。</li></ol>
<p class="note">候補が1件に絞れないカード(同じ番号で通常版とミラー版があるなど)は、間違いを避けるため選ばずに飛ばします。</p>
<p class="note">実際のPSAの画面ではまだ試していません。うまく動かない場合は、表示されたメッセージか画面のスクリーンショットを送ってください。</p></section>
</main>
<script>
const $=(id)=>document.getElementById(id);
function copy(text,box,doneEl){
  const ok=()=>{doneEl.textContent="コピーしました";setTimeout(()=>doneEl.textContent="",2500)};
  const fallback=()=>{const r=document.createRange();r.selectNodeContents(box);const s=getSelection();s.removeAllRanges();s.addRange(r);doneEl.textContent="選択しました。長押しでコピーしてください"};
  try{navigator.clipboard.writeText(text).then(ok,fallback)}catch(e){fallback()}
}
function normalize(){
  const rows=$("list").value.split(/[\\n;]+/).map(s=>s.trim().replace(/\\s+/g," ")).filter(Boolean);
  $("line").textContent=rows.join("; ");
}
$("list").addEventListener("input",normalize);normalize();
$("copyBm").addEventListener("click",()=>copy($("bm").textContent,$("bm"),$("bmDone")));
$("copyList").addEventListener("click",()=>copy($("line").textContent,$("line"),$("listDone")));
</script>
"""
(HERE / "bookmarklet.txt").write_text(bookmarklet + "\n", encoding="utf-8")
(HERE / "page.html").write_text(PAGE.replace("__BOOKMARKLET__", html.escape(bookmarklet)), encoding="utf-8")
print(len(bookmarklet), "文字のブックマークレットを作成")
