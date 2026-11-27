import * as L from "./lib.js";

const $ = (id) => document.getElementById(id);
const num = (id) => Number($(id).value);
const yen = (n) => (n + 0).toLocaleString("ja-JP") + "円"; // + 0 は -0 を 0 にするため
const fmt = (a) => `${a[0]}年${a[1]}月${a[2]}日（${L.weekday(a)}）`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const show = (html) => { $("result").innerHTML = html; };
const rows = (pairs) => "<table>" + pairs.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("") + "</table>";
const err = (msg) => show(`<p class="err">${esc(msg)}</p>`);
const date = (id) => L.parseDate($(id).value);
// 日付欄に何か入っているのに日付として読めない（存在しない日・年が5桁以上など）
const badDate = (id) => !date(id) && ($(id).value !== "" || $(id).validity.badInput);
const dateErr = (name) => err(`${name}は実在する日付を、西暦1〜9999年の範囲で入力してください。`);
// 数値欄の読み取り: 空欄は null、数字として読めない入力は NaN（lib の *Error がエラー文にする）
function read(id) {
  const s = $(id).value.trim();
  if (s === "") return $(id).validity.badInput ? NaN : null;
  return Number(s) + 0; // + 0 は "-0" を 0 にするため
}
const copy = (text) => { if (text && navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {}); };
function today() {
  const t = new Date();
  return [t.getFullYear(), t.getMonth() + 1, t.getDate()];
}
const iso = (a) => `${a[0]}-${String(a[1]).padStart(2, "0")}-${String(a[2]).padStart(2, "0")}`;
// 空欄・数値でない入力は null（Number("") が 0 になるのを避ける）
function val(id) {
  const s = $(id).value.trim(), n = Number(s) + 0;
  return s !== "" && Number.isFinite(n) ? n : null;
}
const TOO_LARGE = "数値は±1,000兆以内で入力してください。";
// 全欄を読む。空欄があれば結果を消し、桁が大きすぎる欄があればエラー文を出して、どちらも null を返す。
function vals(ids) {
  const o = {};
  for (const id of ids) if ((o[id] = val(id)) === null) return show(""), null;
  if (Object.values(o).some(L.tooLarge)) return err(TOO_LARGE), null;
  return o;
}
const on = (ids, run) => ids.forEach((id) => $(id).addEventListener("input", run));
const yenR = (n) => yen(Math.round(n) || 0); // || 0 は -0 を 0 にするため
// 小数6桁まで。丸めて 0 になる負の数が "-0" と表示されないようにする。
const n6 = (v) => { const s = Number(v.toPrecision(12)).toLocaleString("ja-JP", { maximumFractionDigits: 6 }); return s === "-0" ? "0" : s; };
const pct = (v) => (v === null || !Number.isFinite(v) ? "—" : (Number(v.toFixed(2)) + 0).toLocaleString("ja-JP", { maximumFractionDigits: 2 }) + "%");
// 0 以上 n 未満の一様な整数（剰余の偏りが出ないよう、範囲外の値は引き直す）
const rand = (n) => {
  const limit = Math.floor(0x100000000 / n) * n, buf = new Uint32Array(1);
  do crypto.getRandomValues(buf); while (buf[0] >= limit);
  return buf[0] % n;
};
const PSA_COST = ["feeUsd", "fx", "shipOut", "shipBack", "cards", "duty", "taxRate", "misc"];
const PSA_SALE = ["v10", "v9", "vLow", "p10", "p9", "pLow"];
const PSA_BAD = "入力を確認してください（金額・確率は0以上、為替は0より大きく、1箱の枚数は1以上の整数、税率は100%以下）。";
const psaProbErr = (v) => (Math.abs(v.p10 + v.p9 + v.pLow - 100) > 1e-6 ? `確率の合計が100%になるようにしてください（いまは${n6(v.p10 + v.p9 + v.pLow)}%）。` : PSA_BAD);
const psaCostRows = (c) => [
  ["鑑定料", yenR(c.grading)], ["往路送料", yenR(c.shipOut)], ["復路送料", yenR(c.shipBack)],
  ["輸入時の税", yenR(c.importTax)], ["米国関税", yenR(c.usDuty)], ["諸経費", yenR(c.misc)], ["費用の合計（1枚あたり）", yenR(c.total)],
];

const TOOLS = {
  wareki() {
    const run = () => {
      const y = read("seireki");
      if (y === null) return show("");
      const e = L.seirekiError(y);
      if (e) return err(e);
      const end = L.toWareki(y, 12, 31), start = L.toWareki(y, 1, 1);
      const label = start && start.label !== end.label ? `${start.label} ／ ${end.label}（年の途中で改元）` : end.label;
      show(rows([["西暦", `${y}年`], ["和暦", label], ["干支", L.eto(y) + "年"]]));
    };
    const run2 = (ev) => {
      const era = $("era").value, n = read("eraYear");
      if (n === null) return ev.target.id === "eraYear" ? show("") : undefined; // 年が空欄のまま元号だけ変えたときは何もしない
      const e = L.eraYearError(era, n);
      if (e) return err(e);
      const y = L.toSeireki(era, n);
      show(rows([["和暦", `${era}${n}年`], ["西暦", `${y}年`], ["干支", L.eto(y) + "年"]]));
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
      if (badDate("birth")) return dateErr("生年月日");
      if (badDate("on")) return dateErr("基準日");
      const b = date("birth"), on = date("on");
      if (!b || !on) return show("");
      const e = L.ageError(b, on);
      if (e) return err(e);
      const a = L.age(b, on);
      const next = [on[0] + (on[1] * 100 + on[2] >= b[1] * 100 + b[2] ? 1 : 0), b[1], b[2]];
      const nextOk = L.validDate(...next) ? next : [next[0], 3, 1];
      show(rows([
        ["満年齢", `${a}歳`], ["数え年", `${on[0] - b[0] + 1}歳`],
        ["生まれ年", `${L.toWareki(...b)?.label ?? b[0] + "年"}（${L.eto(b[0])}年）`],
        ["生まれてから", `${L.daysBetween(b, on).toLocaleString("ja-JP")}日`],
        ["次の誕生日まで", `${L.daysBetween(on, nextOk)}日`],
      ]));
    };
    ["birth", "on"].forEach((id) => $(id).addEventListener("input", run));
  },
  school() {
    $("birth").addEventListener("input", () => {
      if (badDate("birth")) return dateErr("生年月日");
      const b = date("birth");
      if (!b) return show("");
      const w = (y) => L.yearLabel(y, 4, 1);
      show("<table><tr><th></th><th>入学（4月）</th><th>卒業（3月）</th></tr>" +
        L.schoolYears(...b).map((s) => `<tr><th>${s.name}</th><td>${w(s.enter)}</td><td>${w(s.grad)}</td></tr>`).join("") +
        "</table>");
    });
  },
  days() {
    $("from").value = iso(today());
    const run = () => {
      if (badDate("from")) return dateErr("開始日");
      if (badDate("to")) return dateErr("終了日");
      const a = date("from"), b = date("to"), n = read("n");
      if (!a) return b || n !== null ? err("開始日を入力してください。") : show("");
      const out = [], d = (v) => v.toLocaleString("ja-JP");
      let bad = "";
      if (b) {
        const s = L.daySpan(a, b);
        out.push(["日数（初日を含まない）", s.before ? `${d(s.abs)}日前（終了日が開始日より前です）` : `${d(s.abs)}日`],
          [s.before ? "日数（終了日・開始日の両方を含む）" : "日数（初日を含む）", `${d(s.inclusive)}日`],
          ["週に換算", `${d(s.weeks)}週と${s.rest}日`]);
      }
      if (n !== null) {
        const r = L.addDays(a, n);
        if (r) out.push([n < 0 ? `${d(-n)}日前` : `${d(n + 0)}日後`, fmt(r)]);
        else bad = L.dayOffsetError(n) || "結果が西暦1〜9999年の範囲に収まる日数を入力してください。";
      }
      show((out.length ? rows(out) : "") + (bad ? `<p class="err">${esc(bad)}</p>` : ""));
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
      const total = read("total"), people = read("people"), unit = num("unit");
      if (total === null || people === null) return show("");
      const e = L.splitBillError(total, people, unit);
      if (e) return err(e);
      const r = L.splitBill(total, people, unit);
      show(rows([["1人あたり", yen(r.each)], ["集まる金額", yen(r.each * people)], ["おつり（余り）", yen(r.surplus)]]));
    };
    ["total", "people", "unit"].forEach((id) => $(id).addEventListener("input", run));
  },
  tax() {
    const run = () => {
      const v = read("price");
      if (v === null) return show("");
      const e = L.taxError(v, num("rate"), $("mode").value);
      if (e) return err(e);
      const r = ($("dir").value === "net" ? L.taxFromNet : L.taxFromGross)(v, num("rate"), $("mode").value);
      show(rows([["税抜価格", yen(r.net)], ["消費税", yen(r.tax)], ["税込価格", yen(r.gross)]]));
    };
    ["price", "dir", "rate", "mode"].forEach((id) => $(id).addEventListener("input", run));
  },
  discount() {
    const run = () => {
      const price = read("price"), off = read("off") ?? 0, point = read("point") ?? 0; // 率の空欄は0%として扱う
      if (price === null) return show("");
      const e = L.discountError(price, off, point);
      if (e) return err(e);
      const r = L.discount(price, off, point);
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
      const x = read("value");
      if (x === null) return show("");
      if (!Number.isFinite(x)) return err("数値は半角の数字で入力してください。");
      if (L.tooLarge(x)) return err(TOO_LARGE);
      const v = L.convert($("group").value, x, $("from").value, $("to").value);
      if (v === null) return err("数値が大きすぎます。桁数を減らしてください。");
      show(rows([[`${n6(x)} ${$("from").value}`, `${n6(Number(v.toPrecision(8)))} ${$("to").value}`]]));
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
    $("copy").addEventListener("click", () => copy($("out").value));
  },
  password() {
    const SETS = { lower: "abcdefghijkmnopqrstuvwxyz", upper: "ABCDEFGHJKLMNPQRSTUVWXYZ", digit: "23456789", symbol: "!#$%&*+-=?@_" };
    let current = ""; // 最後に生成に成功したパスワード（エラー表示中は ""）
    const run = () => {
      const sets = Object.keys(SETS).filter((k) => $(k).checked).map((k) => SETS[k]);
      const len = read("len") ?? NaN; // 空欄も長さのエラーにする
      const e = L.passwordError(len, sets);
      current = e ? "" : L.password(len, sets, rand);
      if (e) return err(e);
      show(`<p class="big">${esc(current)}</p>`);
    };
    $("gen").addEventListener("click", run);
    $("copy").addEventListener("click", () => copy(current));
    run();
  },
  "psa-profit"() {
    const ids = ["buy", ...PSA_SALE, ...PSA_COST];
    const run = () => {
      const v = vals(ids);
      if (!v) return;
      const r = L.psaProfit(v);
      if (!r) return err(psaProbErr(v));
      show(rows([
        ...psaCostRows(r.costs),
        ["期待売値", yenR(r.expected)], ["期待利益（1枚あたり）", yenR(r.profit)],
        ["利益率（仕入れ値に対して）", pct(r.marginOnBuy)], ["利益率（仕入れ値＋費用に対して）", pct(r.marginOnSpend)],
        ["損益分岐の仕入れ値", r.breakevenBuy > 0 ? yen(Math.floor(r.breakevenBuy)) : "なし（費用が期待売値を上回ります）"],
        ["PSA10だった場合の損益", yenR(r.if10)], ["PSA9だった場合の損益", yenR(r.if9)], ["それ以下だった場合の損益", yenR(r.ifLow)],
      ]) + "<p>1円未満は四捨五入して表示しています（損益分岐の仕入れ値は切り捨て）。</p>");
    };
    on(ids, run);
    run();
  },
  "psa-max-buy"() {
    const ids = [...PSA_SALE, ...PSA_COST, "target"];
    const run = () => {
      const v = vals(ids);
      if (!v) return;
      const r = L.psaMaxBuy(v);
      if (!r) return err(v.target < 0 ? "目標利益率は0%以上で入力してください。" : psaProbErr(v));
      show(rows([
        ["仕入れ上限（100円単位に切り下げ）", yen(r.maxBuy)],
        ["仕入れ上限（切り下げ前）", yen(Math.max(0, Math.floor(r.exact)))],
        ["期待売値", yenR(r.expected)], ["費用の合計（1枚あたり）", yenR(r.costs.total)],
        ["損益分岐の仕入れ値（利益0円）", r.breakevenBuy > 0 ? yen(Math.floor(r.breakevenBuy)) : "なし"],
      ]) + (r.breakevenBuy <= 0 ? '<p class="err">費用が期待売値を上回るため、いくらで仕入れても期待値では利益が出ません。</p>' : ""));
    };
    on(ids, run);
    run();
  },
  "grading-fee"() {
    const ids = ["count", "unitUsd", "fx", "shipOut", "shipBack"];
    const run = () => {
      const v = vals(ids);
      if (!v) return;
      const r = L.gradingFee(v.count, v.unitUsd, v.fx, v.shipOut, v.shipBack);
      if (!r) return err("枚数は1以上の整数、為替は0より大きい数、金額は0以上で入力してください。");
      show(rows([
        ["1枚あたり", yenR(r.perCard)], ["　うち鑑定料", yenR(r.perCardGrading)], ["　うち送料", yenR(r.perCardShipping)],
        ["鑑定料の合計", yenR(r.grading)], ["送料の合計", yenR(r.shipping)], ["合計", yenR(r.total)],
      ]));
    };
    on(ids, run);
    run();
  },
  "card-roi"() {
    const ids = ["buy", "sell", "fee", "ship"];
    const run = () => {
      const v = vals(ids);
      if (!v) return;
      const r = L.cardRoi(v.buy, v.sell, v.fee, v.ship);
      if (!r) return err("金額は0以上、手数料率は0%以上100%未満で入力してください。");
      show(rows([
        ["販売手数料", yenR(r.fee)], ["手取り（売値−手数料−送料）", yenR(r.net)], ["利益", yenR(r.profit)],
        ["利益率（売値に対して）", pct(r.marginOnSell)], ["利益率（仕入れ値に対して）", pct(r.roi)],
        ["損益分岐の売値", yen(Math.ceil(Number(r.breakevenSell.toFixed(6))))],
      ]));
    };
    on(ids, run);
  },
  percent() {
    const run = () => {
      const v = vals(["a", "b"]);
      if (!v) return;
      const f = (x, unit, why) => (x === null ? why : n6(x) + unit);
      show(rows([
        [`${n6(v.a)} は ${n6(v.b)} の何%`, f(L.percentOf(v.a, v.b), "%", v.b === 0 ? "計算できません（Bが0）" : "計算できません（数が大きすぎます）")],
        [`${n6(v.a)} の ${n6(v.b)}%`, f(L.percentage(v.a, v.b), "", "計算できません（数が大きすぎます）")],
        [`${n6(v.a)} から ${n6(v.b)} への増減率`, f(L.changeRate(v.a, v.b), "%", v.a === 0 ? "計算できません（Aが0）" : "計算できません（数が大きすぎます）")],
      ]));
    };
    on(["a", "b"], run);
  },
  "time-calc"() {
    const hm = (m) => `${L.formatDuration(m)}（${n6(m / 60)}時間・${m.toLocaleString("ja-JP")}分）`;
    const run = () => {
      const out = [];
      const s = L.sumDurations($("list").value);
      if (s.bad.length) return err(`${s.bad.join("・")}行目を読めません。「1:30」のように 時:分（分は00〜59）で入力してください。`);
      if (s.count) out.push([`合計（${s.count}件）`, hm(s.total)]);
      const a = L.parseDuration($("start").value), b = L.parseDuration($("end").value);
      if (a !== null && b !== null) {
        const brk = $("brk").value.trim() === "" ? 0 : val("brk");
        const d = brk === null ? null : L.timeDiff(a, b, brk);
        if (!d) return err("休憩は0以上の整数（分）で、開始〜終了の時間以内にしてください。");
        out.push([d.overnight ? "開始〜終了（翌日の終了として計算）" : "開始〜終了", hm(d.minutes)]);
        if (brk) out.push(["休憩を引いた時間", hm(d.work)]);
      }
      show(out.length ? rows(out) : "");
    };
    on(["list", "start", "end", "brk"], run);
  },
  "hourly-wage"() {
    const run = () => {
      const v = vals(["amount", "hours", "days"]);
      if (!v) return;
      const r = L.wageConvert(v.amount, $("kind").value, v.hours, v.days);
      if (!r) return err("金額は0以上、1日の労働時間は0より大きく24以下、月の勤務日数は0より大きく31以下で入力してください。");
      show(rows([["時給", yenR(r.hourly)], ["日給", yenR(r.daily)], ["月給", yenR(r.monthly)], ["年収（月給×12）", yenR(r.yearly)],
        ["月の労働時間", `${n6(v.hours * v.days)}時間`]]));
    };
    on(["amount", "kind", "hours", "days"], run);
  },
  random() {
    $("draw").addEventListener("click", () => {
      const v = vals(["min", "max", "n"]);
      const r = v && L.randomUnique(v.min, v.max, v.n, rand);
      if (!r) return err(`最小・最大・個数は整数で、個数は1以上かつ範囲に含まれる数の個数以下（最大${L.RANDOM_MAX_COUNT.toLocaleString("ja-JP")}個）にしてください。範囲の広さは約42億までです。`);
      if ($("sort").checked) r.sort((a, b) => a - b);
      show(`<p class="big">${esc(r.join("、"))}</p>`);
    });
    $("pick").addEventListener("click", () => {
      const items = $("list").value.split(/\r\n|\r|\n/).map((s) => s.trim()).filter(Boolean);
      const k = val("k");
      const r = k === null ? null : L.pickFromList(items, k, rand);
      if (!r) return err(`選ぶ数は1以上、リストの件数（いま${items.length}件）以下の整数にしてください。`);
      show("<table>" + r.map((s, i) => `<tr><th>${i + 1}番目</th><td>${esc(s)}</td></tr>`).join("") + "</table>");
    });
  },
  "base-convert"() {
    const run = () => {
      if ($("value").value.trim() === "") return show("");
      const r = L.baseConvert($("value").value, num("from"));
      if (!r) return err(`${num("from")}進数として読めません。使える文字と桁数（${L.BASE_MAX_DIGITS.toLocaleString("ja-JP")}桁まで）を確認してください。`);
      show(rows([["2進数", r[2]], ["8進数", r[8]], ["10進数", r[10]], ["16進数", r[16]]]));
    };
    on(["value", "from"], run);
  },
  kana() {
    const set = (fn) => { $("out").value = fn($("text").value); };
    $("toKata").addEventListener("click", () => set(L.toKatakana));
    $("toHira").addEventListener("click", () => set(L.toHiragana));
    $("copy").addEventListener("click", () => copy($("out").value));
  },
  aspect() {
    const run = () => {
      const v = vals(["w", "h"]);
      if (!v) return;
      const r = L.aspectRatio(v.w, v.h);
      if (!r) return err("幅と高さは0より大きい数で入力してください。");
      const out = [["比率", r.rw ? `${r.rw}:${r.rh}` : `${n6(r.decimal)}:1`], ["幅÷高さ", n6(r.decimal)]];
      for (const [id, key, name, other] of [["newW", "width", "幅", "高さ"], ["newH", "height", "高さ", "幅"]]) {
        if ($(id).value.trim() === "") continue;
        const x = val(id), y = x === null ? null : L.aspectScale(v.w, v.h, { [key]: x });
        if (x !== null && L.tooLarge(x)) return err(TOO_LARGE);
        if (y === null) return err(`新しい${name}は0より大きい数で入力してください。`);
        out.push([`${name} ${n6(x)} のときの${other}`, Number.isInteger(Number(y.toPrecision(12))) ? n6(y) : `${n6(Number(y.toFixed(2)))}（整数にすると ${n6(Math.round(y))}）`]);
      }
      show(rows(out));
    };
    on(["w", "h", "newW", "newH"], run);
    run();
  },
};

const tool = document.body.dataset.tool;
if (TOOLS[tool]) TOOLS[tool]();
