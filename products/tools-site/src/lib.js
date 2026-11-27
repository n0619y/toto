// 計算ロジック（ブラウザと Node のテストで共用）

export const ERAS = [
  { name: "令和", start: [2019, 5, 1] },
  { name: "平成", start: [1989, 1, 8] },
  { name: "昭和", start: [1926, 12, 25] },
  { name: "大正", start: [1912, 7, 30] },
  { name: "明治", start: [1873, 1, 1] }, // 太陽暦採用以降のみ対応
];
const key = (y, m, d) => y * 10000 + m * 100 + d;

export function validDate(y, m, d) {
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

export function toWareki(y, m = 12, d = 31) {
  const era = ERAS.find((e) => key(y, m, d) >= key(...e.start));
  if (!era) return null;
  const base = era.name === "明治" ? 1868 : era.start[0];
  const n = y - base + 1;
  return { era: era.name, year: n, label: `${era.name}${n === 1 ? "元" : n}年` };
}

export function toSeireki(eraName, eraYear) {
  const i = ERAS.findIndex((e) => e.name === eraName);
  if (i < 0 || eraYear < 1) return null;
  const base = eraName === "明治" ? 1868 : ERAS[i].start[0];
  const y = base + eraYear - 1;
  const lastYear = i === 0 ? Infinity : ERAS[i - 1].start[0];
  if (y > lastYear || y < ERAS[i].start[0]) return null;
  return y;
}

const ETO = ["申", "酉", "戌", "亥", "子", "丑", "寅", "卯", "辰", "巳", "午", "未"];
export const eto = (y) => ETO[y % 12];

export function age(birth, on) {
  // birth, on: [y, m, d]
  let a = on[0] - birth[0];
  if (on[1] * 100 + on[2] < birth[1] * 100 + birth[2]) a -= 1;
  return a;
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

const utc = (y, m, d) => Date.UTC(y, m - 1, d);
export const daysBetween = (a, b) => Math.round((utc(...b) - utc(...a)) / 86400000);
export function addDays(a, n) {
  const dt = new Date(utc(...a) + n * 86400000);
  return [dt.getUTCFullYear(), dt.getUTCMonth() + 1, dt.getUTCDate()];
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

export function splitBill(total, people, unit = 1) {
  if (people < 1 || unit < 1 || total < 0) return null;
  const each = Math.ceil(total / people / unit) * unit;
  return { each, surplus: each * people - total };
}

const ROUND = { floor: Math.floor, ceil: Math.ceil, round: Math.round };
export function taxFromNet(net, rate, mode = "floor") {
  const tax = ROUND[mode]((net * rate) / 100);
  return { net, tax, gross: net + tax };
}
export function taxFromGross(gross, rate, mode = "floor") {
  // 税込 → 税抜: 税額は「税込 × 税率 / (100 + 税率)」を端数処理
  const tax = ROUND[mode]((gross * rate) / (100 + rate));
  return { net: gross - tax, tax, gross };
}

export function discount(price, offPercent, pointPercent = 0) {
  const pay = Math.floor((price * (100 - offPercent)) / 100);
  const points = Math.floor((pay * pointPercent) / 100);
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
  return (value * u[from]) / u[to];
}

export function toHalf(s) {
  return s.replace(/[！-～]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0)).replace(/　/g, " ");
}
export function toFull(s) {
  return s.replace(/[!-~]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 0xfee0)).replace(/ /g, "　");
}

export function password(len, sets, rand) {
  // rand(n) は 0 以上 n 未満の一様な整数を返す関数
  const pool = sets.join("");
  if (!pool || len < sets.length) return "";
  for (;;) {
    let out = "";
    for (let i = 0; i < len; i++) out += pool[rand(pool.length)];
    if (sets.every((s) => [...out].some((c) => s.includes(c)))) return out;
  }
}
