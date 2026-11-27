import * as L from "./lib.js";

const $ = (id) => document.getElementById(id);
const num = (id) => Number($(id).value);
const yen = (n) => n.toLocaleString("ja-JP") + "円";
const fmt = (a) => `${a[0]}年${a[1]}月${a[2]}日（${L.weekday(a)}）`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const show = (html) => { $("result").innerHTML = html; };
const rows = (pairs) => "<table>" + pairs.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("") + "</table>";
const err = (msg) => show(`<p class="err">${esc(msg)}</p>`);
function date(id) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec($(id).value);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}
function today() {
  const t = new Date();
  return [t.getFullYear(), t.getMonth() + 1, t.getDate()];
}
const iso = (a) => `${a[0]}-${String(a[1]).padStart(2, "0")}-${String(a[2]).padStart(2, "0")}`;

const TOOLS = {
  wareki() {
    const run = () => {
      const y = num("seireki");
      if (!Number.isInteger(y) || y < 1873 || y > 2200) return err("1873年以降の西暦を入力してください。");
      const end = L.toWareki(y, 12, 31), start = L.toWareki(y, 1, 1);
      const label = start && start.label !== end.label ? `${start.label} ／ ${end.label}（年の途中で改元）` : end.label;
      show(rows([["西暦", `${y}年`], ["和暦", label], ["干支", L.eto(y) + "年"]]));
    };
    const run2 = () => {
      const y = L.toSeireki($("era").value, num("eraYear"));
      if (y === null) return err("その元号には存在しない年です。");
      show(rows([["和暦", `${$("era").value}${num("eraYear")}年`], ["西暦", `${y}年`], ["干支", L.eto(y) + "年"]]));
    };
    $("seireki").value = today()[0];
    $("seireki").addEventListener("input", run);
    $("era").addEventListener("change", run2);
    $("eraYear").addEventListener("input", run2);
    run();
  },
  age() {
    $("on").value = iso(today());
    const run = () => {
      const b = date("birth"), on = date("on");
      if (!b || !on) return show("");
      if (L.daysBetween(b, on) < 0) return err("基準日は生年月日より後にしてください。");
      const a = L.age(b, on);
      const next = [on[0] + (on[1] * 100 + on[2] >= b[1] * 100 + b[2] ? 1 : 0), b[1], b[2]];
      const nextOk = L.validDate(...next) ? next : [next[0], 3, 1];
      show(rows([
        ["満年齢", `${a}歳`], ["数え年", `${on[0] - b[0] + 1}歳`],
        ["生まれ年", `${L.toWareki(...b)?.label ?? ""}（${L.eto(b[0])}年）`],
        ["生まれてから", `${L.daysBetween(b, on).toLocaleString()}日`],
        ["次の誕生日まで", `${L.daysBetween(on, nextOk)}日`],
      ]));
    };
    ["birth", "on"].forEach((id) => $(id).addEventListener("input", run));
  },
  school() {
    $("birth").addEventListener("input", () => {
      const b = date("birth");
      if (!b) return show("");
      const w = (y) => `${y}年（${L.toWareki(y, 4, 1).label}）`;
      show("<table><tr><th></th><th>入学（4月）</th><th>卒業（3月）</th></tr>" +
        L.schoolYears(...b).map((s) => `<tr><th>${s.name}</th><td>${w(s.enter)}</td><td>${w(s.grad)}</td></tr>`).join("") +
        "</table>");
    });
  },
  days() {
    $("from").value = iso(today());
    const run = () => {
      const a = date("from"), b = date("to");
      const out = [];
      if (a && b) {
        const n = L.daysBetween(a, b);
        out.push(["日数（初日を含まない）", `${n.toLocaleString()}日`], ["日数（初日を含む）", `${(n + Math.sign(n || 1)).toLocaleString()}日`],
          ["週に換算", `${Math.trunc(n / 7)}週と${n % 7}日`]);
      }
      if (a && $("n").value !== "") out.push([`${num("n")}日後`, fmt(L.addDays(a, num("n")))]);
      show(out.length ? rows(out) : "");
    };
    ["from", "to", "n"].forEach((id) => $(id).addEventListener("input", run));
  },
  count() {
    const run = () => {
      const c = L.countText($("text").value);
      show(rows([["文字数", c.all.toLocaleString()], ["空白・改行を除く", c.noSpace.toLocaleString()], ["行数", c.lines.toLocaleString()],
        ["原稿用紙（400字）", `${c.pages}枚`], ["バイト数（UTF-8）", c.bytes.toLocaleString()]]));
    };
    $("text").addEventListener("input", run);
    run();
  },
  warikan() {
    const run = () => {
      const r = L.splitBill(num("total"), num("people"), num("unit"));
      if (!r || !num("total")) return show("");
      show(rows([["1人あたり", yen(r.each)], ["集まる金額", yen(r.each * num("people"))], ["おつり（余り）", yen(r.surplus)]]));
    };
    ["total", "people", "unit"].forEach((id) => $(id).addEventListener("input", run));
  },
  tax() {
    const run = () => {
      const v = num("price");
      if (!v) return show("");
      const r = ($("dir").value === "net" ? L.taxFromNet : L.taxFromGross)(v, num("rate"), $("mode").value);
      show(rows([["税抜価格", yen(r.net)], ["消費税", yen(r.tax)], ["税込価格", yen(r.gross)]]));
    };
    ["price", "dir", "rate", "mode"].forEach((id) => $(id).addEventListener("input", run));
  },
  discount() {
    const run = () => {
      if (!num("price")) return show("");
      const r = L.discount(num("price"), num("off"), num("point"));
      show(rows([["割引後の支払額", yen(r.pay)], ["値引き額", yen(r.saved)], ["もらえるポイント", r.points.toLocaleString() + "pt"], ["実質価格", yen(r.effective)]]));
    };
    ["price", "off", "point"].forEach((id) => $(id).addEventListener("input", run));
  },
  unit() {
    const fill = () => {
      const names = Object.keys(L.UNITS[$("group").value]);
      for (const id of ["from", "to"]) $(id).innerHTML = names.map((n) => `<option>${n}</option>`).join("");
      $("to").selectedIndex = 1;
      run();
    };
    const run = () => {
      if ($("value").value === "") return show("");
      const v = L.convert($("group").value, num("value"), $("from").value, $("to").value);
      show(rows([[`${num("value")} ${$("from").value}`, `${Number(v.toPrecision(8)).toLocaleString("ja-JP", { maximumFractionDigits: 6 })} ${$("to").value}`]]));
    };
    $("group").innerHTML = Object.keys(L.UNITS).map((g) => `<option>${g}</option>`).join("");
    $("group").addEventListener("change", fill);
    ["value", "from", "to"].forEach((id) => $(id).addEventListener("input", run));
    fill();
  },
  zenhan() {
    const set = (fn) => { $("out").value = fn($("text").value); };
    $("toHalf").addEventListener("click", () => set(L.toHalf));
    $("toFull").addEventListener("click", () => set(L.toFull));
    $("copy").addEventListener("click", () => navigator.clipboard.writeText($("out").value));
  },
  password() {
    const SETS = { lower: "abcdefghijkmnopqrstuvwxyz", upper: "ABCDEFGHJKLMNPQRSTUVWXYZ", digit: "23456789", symbol: "!#$%&*+-=?@_" };
    const rand = (n) => {
      const limit = Math.floor(0x100000000 / n) * n, buf = new Uint32Array(1);
      do crypto.getRandomValues(buf); while (buf[0] >= limit);
      return buf[0] % n;
    };
    const run = () => {
      const sets = Object.keys(SETS).filter((k) => $(k).checked).map((k) => SETS[k]);
      const pw = L.password(num("len"), sets, rand);
      show(pw ? `<p class="big">${esc(pw)}</p>` : `<p class="err">文字の種類を1つ以上選んでください。</p>`);
    };
    $("gen").addEventListener("click", run);
    $("copy").addEventListener("click", () => navigator.clipboard.writeText($("result").textContent));
    run();
  },
};

const tool = document.body.dataset.tool;
if (TOOLS[tool]) TOOLS[tool]();
