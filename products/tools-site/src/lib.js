// 計算ロジック（ブラウザと Node のテストで共用）

export const ERAS = [
  { name: "令和", start: [2019, 5, 1] },
  { name: "平成", start: [1989, 1, 8] },
  { name: "昭和", start: [1926, 12, 25] },
  { name: "大正", start: [1912, 7, 30] },
  { name: "明治", start: [1873, 1, 1] }, // 太陽暦採用以降のみ対応
];
const key = (y, m, d) => y * 10000 + m * 100 + d;

// 入力チェック用。*Error 関数は、問題があれば画面に出すエラー文を、無ければ null を返す。
const isInt = (v, lo, hi) => Number.isSafeInteger(v) && v >= lo && v <= hi;
const isRate = (v) => typeof v === "number" && v >= 0 && v <= 100; // NaN は比較で落ちる

// 年・月・日の UTC 0時（ミリ秒）。Date.UTC は 0〜99 年を 1900 年代に読み替えるので使わない。
const utc = (y, m, d) => new Date(0).setUTCFullYear(y, m - 1, d);

export function validDate(y, m, d) {
  if (![y, m, d].every(Number.isInteger)) return false;
  const dt = new Date(utc(y, m, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}
// "2026-11-27" → [2026, 11, 27]。存在しない日付・西暦1〜9999年以外は null。
export function parseDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s));
  if (!m) return null;
  const a = [Number(m[1]), Number(m[2]), Number(m[3])];
  return a[0] >= 1 && validDate(...a) ? a : null;
}

export function toWareki(y, m = 12, d = 31) {
  const era = ERAS.find((e) => key(y, m, d) >= key(...e.start));
  if (!era) return null;
  const base = era.name === "明治" ? 1868 : era.start[0];
  const n = y - base + 1;
  return { era: era.name, year: n, label: `${era.name}${n === 1 ? "元" : n}年` };
}

// 対応する西暦の範囲（和暦→西暦も同じ範囲に限る）
export const SEIREKI_MIN = 1873, SEIREKI_MAX = 2200;
export function seirekiError(y) {
  return isInt(y, SEIREKI_MIN, SEIREKI_MAX) ? null : `西暦は${SEIREKI_MIN}〜${SEIREKI_MAX}の整数で入力してください。`;
}
// その元号で入力できる年の範囲 [最小, 最大]（明治は太陽暦採用の6年から）
export function eraYearRange(eraName) {
  const i = ERAS.findIndex((e) => e.name === eraName);
  if (i < 0) return null;
  const base = eraName === "明治" ? 1868 : ERAS[i].start[0];
  const lastYear = i === 0 ? SEIREKI_MAX : ERAS[i - 1].start[0];
  return [ERAS[i].start[0] - base + 1, lastYear - base + 1];
}
export function eraYearError(eraName, eraYear) {
  const r = eraYearRange(eraName);
  if (!r) return "元号を選んでください。";
  if (!Number.isSafeInteger(eraYear) || eraYear < 1) return "年は1以上の整数で入力してください。";
  return eraYear < r[0] || eraYear > r[1] ? `${eraName}は${r[0]}〜${r[1]}年の範囲で入力してください。` : null;
}
export function toSeireki(eraName, eraYear) {
  if (eraYearError(eraName, eraYear)) return null;
  return (eraName === "明治" ? 1868 : ERAS.find((e) => e.name === eraName).start[0]) + eraYear - 1;
}
// 「2026年（令和8年）」。和暦の対応範囲より前は西暦だけ。
export function yearLabel(y, m = 12, d = 31) {
  const w = toWareki(y, m, d);
  return w ? `${y}年（${w.label}）` : `${y}年`;
}

const ETO = ["申", "酉", "戌", "亥", "子", "丑", "寅", "卯", "辰", "巳", "午", "未"];
export const eto = (y) => ETO[((y % 12) + 12) % 12];

export function age(birth, on) {
  // birth, on: [y, m, d]
  let a = on[0] - birth[0];
  if (on[1] * 100 + on[2] < birth[1] * 100 + birth[2]) a -= 1;
  return a;
}
export function ageError(birth, on) {
  return daysBetween(birth, on) < 0 ? "生年月日は基準日以前の日付にしてください。" : null;
}

export function schoolYears(y, m, d) {
  // 4月2日〜翌4月1日生まれが同学年。小学校入学は満6歳になった後の最初の4月。
  const early = m < 4 || (m === 4 && d === 1);
  const es = y + (early ? 6 : 7);
  return [
    ["小学校", es, es + 6],
    ["中学校", es + 6, es + 9],
    ["高校", es + 9, es + 12],
    ["大学（4年制）", es + 12, es + 16],
  ].map(([name, enter, grad]) => ({ name, enter, grad }));
}

export const daysBetween = (a, b) => Math.round((utc(...b) - utc(...a)) / 86400000);
// a から b までの日数の内訳。b が a より前なら before = true で、日数・週は絶対値で返す。
export function daySpan(a, b) {
  const days = daysBetween(a, b), abs = Math.abs(days);
  return { days, abs, before: days < 0, inclusive: abs + 1, weeks: Math.floor(abs / 7), rest: abs % 7 };
}
export const DAY_OFFSET_MAX = 3660000; // 約1万年
export function dayOffsetError(n) {
  if (!Number.isSafeInteger(n)) return "◯日後の日数は整数で入力してください（◯日前はマイナスの整数）。";
  return Math.abs(n) > DAY_OFFSET_MAX ? `◯日後の日数は−${DAY_OFFSET_MAX.toLocaleString("ja-JP")}〜${DAY_OFFSET_MAX.toLocaleString("ja-JP")}の範囲で入力してください。` : null;
}
// n 日後（負なら前）の日付。n が整数でない・結果が西暦1〜9999年を外れるときは null。
export function addDays(a, n) {
  if (dayOffsetError(n)) return null;
  const dt = new Date(utc(...a) + n * 86400000);
  const y = dt.getUTCFullYear();
  return y >= 1 && y <= 9999 ? [y, dt.getUTCMonth() + 1, dt.getUTCDate()] : null;
}
export const weekday = (a) => "日月火水木金土"[new Date(utc(...a)).getUTCDay()];

export function countText(s) {
  const chars = [...s];
  return {
    all: chars.length,
    noSpace: chars.filter((c) => !/\s/.test(c)).length,
    lines: s === "" ? 0 : s.split(/\r\n|\r|\n/).length,
    bytes: new TextEncoder().encode(s).length,
    pages: Math.ceil(chars.filter((c) => c !== "\n" && c !== "\r").length / 400),
  };
}

export const MAX_YEN = 1e12, MAX_PEOPLE = 1e6;
export function yenError(v, name = "金額") {
  if (!Number.isSafeInteger(v) || v < 0) return `${name}は0以上の整数で入力してください。`;
  return v > MAX_YEN ? `${name}は1兆円以下で入力してください。` : null;
}
export function splitBillError(total, people, unit = 1) {
  const e = yenError(total, "合計金額");
  if (e) return e;
  if (!Number.isSafeInteger(people) || people < 1) return "人数は1以上の整数で入力してください。";
  if (people > MAX_PEOPLE) return "人数は100万人以下で入力してください。";
  return isInt(unit, 1, MAX_YEN) ? null : "切り上げ単位は1以上の整数で指定してください。";
}
export function splitBill(total, people, unit = 1) {
  if (splitBillError(total, people, unit)) return null;
  const each = Math.ceil(total / people / unit) * unit;
  return { each, surplus: each * people - total };
}

const ROUND = { floor: Math.floor, ceil: Math.ceil, round: Math.round };
export function taxError(amount, rate, mode = "floor") {
  const e = yenError(amount);
  if (e) return e;
  if (!isRate(rate)) return "税率は0〜100の範囲で指定してください。";
  return Object.hasOwn(ROUND, mode) ? null : "端数処理は切り捨て・四捨五入・切り上げから選んでください。";
}
export function taxFromNet(net, rate, mode = "floor") {
  if (taxError(net, rate, mode)) return null;
  const tax = ROUND[mode]((net * rate) / 100);
  return { net, tax, gross: net + tax };
}
export function taxFromGross(gross, rate, mode = "floor") {
  // 税込 → 税抜: 税額は「税込 × 税率 / (100 + 税率)」を端数処理
  if (taxError(gross, rate, mode)) return null;
  const tax = ROUND[mode]((gross * rate) / (100 + rate));
  return { net: gross - tax, tax, gross };
}

export function discountError(price, offPercent, pointPercent = 0) {
  const e = yenError(price, "元の価格");
  if (e) return e;
  if (!isRate(offPercent)) return "割引率は0〜100の範囲で入力してください。";
  return isRate(pointPercent) ? null : "ポイント還元率は0〜100の範囲で入力してください。";
}
export function discount(price, offPercent, pointPercent = 0) {
  if (discountError(price, offPercent, pointPercent)) return null;
  // 66.4% などは 2進小数で誤差が出る（125円の33.6% = 41.99999…）ので、小数6桁に丸めてから切り捨てる
  const floor = (x) => Math.floor(Number(x.toFixed(6)));
  const pay = floor((price * (100 - offPercent)) / 100);
  const points = floor((pay * pointPercent) / 100);
  return { pay, saved: price - pay, points, effective: pay - points };
}

export const UNITS = {
  面積: { "㎡": 1, "坪": 400 / 121, "畳（中京間・目安）": 1.6562, "a（アール）": 100, "ha": 10000 },
  長さ: { "cm": 1, "m": 100, "インチ": 2.54, "フィート": 30.48, "尺": 100 / 3.3, "寸": 10 / 3.3 },
  容量: { "mL": 1, "L": 1000, "合": 180.39, "升": 1803.9, "カップ（日本）": 200, "大さじ": 15, "小さじ": 5 },
  重さ: { "g": 1, "kg": 1000, "ポンド": 453.59237, "オンス": 28.349523125, "貫": 3750, "匁": 3.75 },
};
export function convert(group, value, from, to) {
  const u = UNITS[group];
  if (!u || !Object.hasOwn(u, from) || !Object.hasOwn(u, to)) return null;
  const v = (value * u[from]) / u[to];
  return typeof value === "number" && Number.isFinite(v) ? v + 0 : null; // + 0 は -0 を 0 にするため
}

export function toHalf(s) {
  return s.replace(/[！-～]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0)).replace(/　/g, " ");
}
export function toFull(s) {
  return s.replace(/[!-~]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 0xfee0)).replace(/ /g, "　");
}

export const PASSWORD_MIN = 4, PASSWORD_MAX = 64;
export function passwordError(len, sets) {
  if (!isInt(len, PASSWORD_MIN, PASSWORD_MAX)) return `長さは${PASSWORD_MIN}〜${PASSWORD_MAX}の整数で入力してください。`;
  return Array.isArray(sets) && sets.length && sets.every((s) => s) ? null : "文字の種類を1つ以上選んでください。";
}
export function password(len, sets, rand) {
  // rand(n) は 0 以上 n 未満の一様な整数を返す関数。入力が不正なら ""。
  if (passwordError(len, sets) || len < sets.length) return "";
  const pool = sets.join("");
  for (;;) {
    let out = "";
    for (let i = 0; i < len; i++) out += pool[rand(pool.length)];
    if (sets.every((s) => [...out].some((c) => s.includes(c)))) return out;
  }
}

// ---- ここから下: トレカ・PSA鑑定 ----
// 画面の数値欄で受け付ける絶対値の上限（これを超えると桁あふれや極端に長い表示になる）
export const MAX_ABS = 1e15;
export const tooLarge = (v) => Math.abs(v) > MAX_ABS;
const fin = (...a) => a.every((v) => typeof v === "number" && Number.isFinite(v));
const nonNeg = (...a) => fin(...a) && a.every((v) => v >= 0);
const finOrNull = (v) => (fin(v) ? v : null);

// 1枚あたりの鑑定費用（円）。pokeca/core.py の per_card_costs と同じ式。
// c: { feeUsd, fx, shipOut(円/箱), shipBack(USD/箱), cards, duty(USD/箱), taxRate(%), misc(円/枚) }
export function psaCosts(c) {
  const { feeUsd, fx, shipOut, shipBack, cards, duty, taxRate, misc } = c;
  if (!nonNeg(feeUsd, fx, shipOut, shipBack, cards, duty, taxRate, misc)) return null;
  if (fx <= 0 || !Number.isInteger(cards) || cards < 1 || taxRate > 100) return null;
  const grading = feeUsd * fx;
  const back = (shipBack * fx) / cards;
  const r = {
    grading, shipOut: shipOut / cards, shipBack: back,
    importTax: ((grading + back) * taxRate) / 100,
    usDuty: (duty * fx) / cards, misc,
  };
  r.total = r.grading + r.shipOut + r.shipBack + r.importTax + r.usDuty + r.misc;
  return fin(r.total) ? r : null;
}

// 期待売値 = Σ 確率 × 売値。確率は % で、合計が 100 でなければ null。
export function psaExpected(c) {
  const { v10, v9, vLow, p10, p9, pLow } = c;
  if (!nonNeg(v10, v9, vLow, p10, p9, pLow) || Math.abs(p10 + p9 + pLow - 100) > 1e-6) return null;
  const x = (p10 * v10 + p9 * v9 + pLow * vLow) / 100;
  return fin(x) ? x : null;
}

export function psaProfit(c) {
  const costs = psaCosts(c), expected = psaExpected(c);
  if (!costs || expected === null || !nonNeg(c.buy)) return null;
  const spend = c.buy + costs.total;
  const profit = expected - spend;
  return {
    costs, expected, profit,
    marginOnBuy: c.buy > 0 ? finOrNull((profit / c.buy) * 100) : null,   // 仕入れ値に対する利益率（core.py の目標利益率と同じ分母）
    marginOnSpend: spend > 0 ? finOrNull((profit / spend) * 100) : null, // 仕入れ値＋費用に対する利益率
    breakevenBuy: expected - costs.total,
    if10: c.v10 - spend, if9: c.v9 - spend, ifLow: c.vLow - spend,
  };
}

// 仕入れ上限 = (期待売値 − 費用) ÷ (1 + 目標利益率)。core.py の recommend と同じ式で、100円単位に切り下げ。
export function psaMaxBuy(c) {
  const costs = psaCosts(c), expected = psaExpected(c);
  if (!costs || expected === null || !nonNeg(c.target)) return null;
  const room = expected - costs.total;
  const exact = room / (1 + c.target / 100);
  return { costs, expected, breakevenBuy: room, exact, maxBuy: Math.max(0, Math.floor(exact / 100) * 100) };
}

// 鑑定料の円換算。送料は枚数で按分する。
export function gradingFee(count, unitUsd, fx, shipOutJpy = 0, shipBackUsd = 0) {
  if (!nonNeg(count, unitUsd, fx, shipOutJpy, shipBackUsd) || !Number.isInteger(count) || count < 1 || fx <= 0) return null;
  const grading = count * unitUsd * fx;
  const shipping = shipOutJpy + shipBackUsd * fx;
  const total = grading + shipping;
  if (!fin(total)) return null;
  return { grading, shipping, total, perCard: total / count, perCardGrading: unitUsd * fx, perCardShipping: shipping / count };
}

// 売買の利益。手数料は売値 × 手数料率（端数処理なし）。
export function cardRoi(buy, sell, feePercent, shipping = 0) {
  if (!nonNeg(buy, sell, feePercent, shipping) || feePercent >= 100) return null;
  const fee = (sell * feePercent) / 100;
  const profit = sell - fee - shipping - buy;
  const breakevenSell = (buy + shipping) / (1 - feePercent / 100);
  if (!fin(profit, breakevenSell)) return null;
  return {
    fee, net: sell - fee - shipping, profit,
    marginOnSell: sell > 0 ? finOrNull((profit / sell) * 100) : null,
    roi: buy > 0 ? finOrNull((profit / buy) * 100) : null,
    breakevenSell,
  };
}

// ---- くらし・仕事 ----
export const percentOf = (a, b) => (fin(a, b) && b !== 0 ? finOrNull((a / b) * 100) : null); // A は B の何%
export const percentage = (a, b) => (fin(a, b) ? finOrNull((a * b) / 100) : null);            // A の B%
export const changeRate = (a, b) => (fin(a, b) && a !== 0 ? finOrNull(((b - a) / Math.abs(a)) * 100) : null); // A→B の増減率

// "1:30" "-0:15" → 分。分は 00〜59。全角の数字・コロンも受け付ける。
export function parseDuration(s) {
  const m = /^([-+])?\s*(\d{1,7}):([0-5]\d)$/.exec(toHalf(String(s)).trim());
  if (!m) return null;
  const v = Number(m[2]) * 60 + Number(m[3]);
  return m[1] === "-" && v !== 0 ? -v : v;
}
export function formatDuration(min) {
  if (!Number.isInteger(min)) return "";
  const a = Math.abs(min);
  return `${min < 0 ? "-" : ""}${Math.floor(a / 60)}:${String(a % 60).padStart(2, "0")}`;
}
// 複数行の合計。空行は無視し、読めない行は bad に行番号（1始まり）を入れる。
export function sumDurations(text) {
  let total = 0, count = 0;
  const bad = [];
  String(text).split(/\r\n|\r|\n/).forEach((line, i) => {
    if (line.trim() === "") return;
    const v = parseDuration(line);
    if (v === null) bad.push(i + 1);
    else { total += v; count += 1; }
  });
  return { total, count, bad };
}
// 開始〜終了の差（分）。終了が開始より前なら翌日とみなす。
export function timeDiff(start, end, breakMin = 0) {
  const ok = (v) => Number.isInteger(v) && v >= 0 && v < 1440;
  if (!ok(start) || !ok(end) || !Number.isInteger(breakMin) || breakMin < 0) return null;
  const overnight = end < start;
  const minutes = end - start + (overnight ? 1440 : 0);
  if (breakMin > minutes) return null;
  return { minutes, work: minutes - breakMin, overnight };
}

// 時給・日給・月給・年収の換算。kind: hour / day / month / year。年収 = 月給 × 12。
export function wageConvert(amount, kind, hoursPerDay, daysPerMonth) {
  if (!nonNeg(amount, hoursPerDay, daysPerMonth) || hoursPerDay <= 0 || hoursPerDay > 24 || daysPerMonth <= 0 || daysPerMonth > 31) return null;
  const per = { hour: 1, day: hoursPerDay, month: hoursPerDay * daysPerMonth, year: hoursPerDay * daysPerMonth * 12 }[kind];
  if (!per) return null;
  const hourly = amount / per;
  const r = { hourly, daily: hourly * hoursPerDay, monthly: hourly * hoursPerDay * daysPerMonth, yearly: hourly * hoursPerDay * daysPerMonth * 12 };
  return fin(r.yearly) ? r : null;
}

// min〜max の整数から重複なしで n 個を、引いた順に返す。rand(k) は 0 以上 k 未満の一様な整数。
// Floyd の方法で一様な組を選び、Fisher–Yates で順番を混ぜる（範囲が広くても配列を作らない）。
export const RANDOM_MAX_COUNT = 10000;
export function randomUnique(min, max, n, rand) {
  if (![min, max, n].every(Number.isSafeInteger) || min > max) return null;
  const size = max - min + 1;
  if (size > 0x100000000 || n < 1 || n > size || n > RANDOM_MAX_COUNT) return null;
  const seen = new Set(), out = [];
  for (let j = max - n + 1; j <= max; j++) {
    const t = min + rand(j - min + 1);
    const pick = seen.has(t) ? j : t;
    seen.add(pick);
    out.push(pick);
  }
  for (let i = out.length - 1; i > 0; i--) {
    const k = rand(i + 1);
    [out[i], out[k]] = [out[k], out[i]];
  }
  return out;
}
export function pickFromList(items, n, rand) {
  const idx = randomUnique(0, items.length - 1, n, rand);
  return idx && idx.map((i) => items[i]);
}

// 2・8・10・16進の相互変換（BigInt）。0b / 0o / 0x の接頭辞、空白と _ の区切り、先頭の - を受け付ける。
const BASES = { 2: [/^[01]+$/, "0b"], 8: [/^[0-7]+$/, "0o"], 10: [/^[0-9]+$/, ""], 16: [/^[0-9a-f]+$/i, "0x"] };
export const BASE_MAX_DIGITS = 4096;
export function baseConvert(text, from) {
  if (!BASES[from]) return null;
  const [re, prefix] = BASES[from];
  let s = toHalf(String(text)).replace(/[\s_]/g, "");
  const neg = s.startsWith("-");
  if (neg || s.startsWith("+")) s = s.slice(1);
  if (prefix && s.toLowerCase().startsWith(prefix)) s = s.slice(2);
  if (!re.test(s) || s.length > BASE_MAX_DIGITS) return null;
  let v = BigInt(prefix + s);
  if (neg) v = -v;
  return { 2: v.toString(2), 8: v.toString(8), 10: v.toString(10), 16: v.toString(16).toUpperCase() };
}

// ひらがな ⇔ カタカナ（ゝゞ・ヽヾ を含む。ヷヸヹヺ は対応するひらがなが無いのでそのまま）
export function toKatakana(s) {
  return s.replace(/[ぁ-ゖゝゞ]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 0x60));
}
export function toHiragana(s) {
  return s.replace(/[ァ-ヶヽヾ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60));
}

// アスペクト比。幅・高さがどちらも整数なら最大公約数で約分した比も返す。
export function aspectRatio(w, h) {
  if (!fin(w, h) || w <= 0 || h <= 0 || !fin(w / h) || w / h === 0) return null;
  const r = { decimal: w / h, rw: null, rh: null };
  if (Number.isSafeInteger(w) && Number.isSafeInteger(h)) {
    let a = w, b = h;
    while (b) [a, b] = [b, a % b];
    r.rw = w / a; r.rh = h / a;
  }
  return r;
}
// 比 w:h を保ったまま、新しい幅（または高さ）に対するもう片方を返す。
export function aspectScale(w, h, { width, height }) {
  if (!aspectRatio(w, h)) return null;
  const v = width !== undefined ? (width * h) / w : (height * w) / h;
  const given = width !== undefined ? width : height;
  return fin(given, v) && given > 0 && v > 0 ? v : null;
}
