// 手取りシミュレーターの画面。計算は tejori.js（products/kaitori-kit/tejori.py と同じ式）。
import { hikaku } from "./tejori.js";

const $ = (id) => document.getElementById(id);
const out = $("result");
const yen = (n) => `${n.toLocaleString("ja-JP")}円`;
const signed = (n) => `${n > 0 ? "+" : n < 0 ? "−" : "±"}${Math.abs(n).toLocaleString("ja-JP")}円`;
const pct = (s) => s.replace(/(\.\d)0$/, "$1") + "%";

function show(html) { out.innerHTML = html; }

function calc() {
  const g = (id) => $(id).value.trim();
  if (g("soba") === "") return show("<p>相場価格を入れると計算します。</p>");
  if (g("ritsu") === "") return show("<p>買取率を入れると計算します。</p>");
  let h;
  try {
    h = hikaku(g("soba"), g("tesuryo") || "0", g("fsoryo") || "0", g("ritsu"), g("usoryo") || "0", g("ufuri") || "0");
  } catch (err) {
    const p = document.createElement("p");
    p.className = "err";
    p.textContent = err instanceof RangeError ? err.message : "計算できませんでした。入力を確かめてください。";
    out.replaceChildren(p);
    return;
  }
  const d = h.uriteSagaku;
  const verdict = d > 0
    ? `この条件では、この買取のほうが手取りが ${yen(d)} 多くなります。`
    : d < 0
      ? `この条件では、フリマで売るほうが手取りが ${yen(-d)} 多くなります。`
      : "この条件では、手取りは同じです。";
  show(`<table>
<tr><th>フリマで売った場合の手取り</th><td id="r-furima">${yen(h.furimaTejori)}</td></tr>
<tr><th>この買取の手取り</th><td id="r-kaitori">${yen(h.kaitoriTejori)}</td></tr>
<tr><th>差額（買取 − フリマ）</th><td id="r-sagaku" class="${d > 0 ? "plus" : d < 0 ? "minus" : ""}">${signed(d)}</td></tr>
<tr><th>手取りが同じになる買取率</th><td id="r-gyakuten">${pct(h.gyakutenRitsu)}</td></tr>
</table>
<p class="verdict" id="r-verdict">${verdict}</p>`);
}

if (out) {
  for (const el of document.querySelectorAll("#sim input")) el.addEventListener("input", calc);
  calc();
}
