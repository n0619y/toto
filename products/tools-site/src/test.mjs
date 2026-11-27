import assert from "node:assert/strict";
import * as L from "./lib.js";

assert.equal(L.toWareki(2019, 4, 30).label, "平成31年");
assert.equal(L.toWareki(2019, 5, 1).label, "令和元年");
assert.equal(L.toWareki(2026, 11, 27).label, "令和8年");
assert.equal(L.toWareki(1989, 1, 7).label, "昭和64年");
assert.equal(L.toWareki(1926, 12, 25).label, "昭和元年");
assert.equal(L.toWareki(1912, 7, 29).label, "明治45年");
assert.equal(L.toWareki(1872, 12, 31), null);
assert.equal(L.toSeireki("令和", 8), 2026);
assert.equal(L.toSeireki("昭和", 64), 1989);
assert.equal(L.toSeireki("昭和", 65), null);
assert.equal(L.toSeireki("平成", 31), 2019);
assert.equal(L.toSeireki("明治", 45), 1912);
assert.equal(L.eto(2026), "午");
assert.equal(L.eto(2024), "辰");
assert.equal(L.age([2000, 11, 28], [2026, 11, 27]), 25);
assert.equal(L.age([2000, 11, 27], [2026, 11, 27]), 26);
assert.equal(L.schoolYears(2020, 4, 1)[0].enter, 2026);
assert.equal(L.schoolYears(2020, 4, 2)[0].enter, 2027);
assert.equal(L.schoolYears(2019, 12, 1)[0].enter, 2026);
assert.equal(L.schoolYears(2020, 4, 2)[3].grad, 2043);
assert.equal(L.daysBetween([2026, 11, 27], [2027, 1, 1]), 35);
assert.deepEqual(L.addDays([2024, 2, 28], 2), [2024, 3, 1]);
assert.equal(L.weekday([2026, 11, 27]), "金");
assert.ok(L.validDate(2024, 2, 29) && !L.validDate(2026, 2, 29));
assert.deepEqual(L.countText("あい う\nえ"), { all: 6, noSpace: 4, lines: 2, bytes: 14, pages: 1 });
assert.deepEqual(L.splitBill(10000, 3, 100), { each: 3400, surplus: 200 });
assert.deepEqual(L.taxFromNet(999, 10), { net: 999, tax: 99, gross: 1098 });
assert.deepEqual(L.taxFromGross(1100, 10), { net: 1000, tax: 100, gross: 1100 });
assert.deepEqual(L.taxFromGross(1080, 8), { net: 1000, tax: 80, gross: 1080 });
assert.deepEqual(L.discount(1980, 30, 10), { pay: 1386, saved: 594, points: 138, effective: 1248 });
assert.ok(Math.abs(L.convert("面積", 1, "坪", "㎡") - 3.305785) < 1e-5);
assert.ok(Math.abs(L.convert("長さ", 1, "インチ", "cm") - 2.54) < 1e-9);
assert.equal(L.toHalf("ＡＢＣ１２３　！"), "ABC123 !");
assert.equal(L.toFull("abc 1"), "ａｂｃ　１");
let i = 0;
const pw = L.password(12, ["abc", "XYZ", "123"], (n) => i++ % n);
assert.equal(pw.length, 12);
// ---- トレカ・PSA鑑定（期待値は手計算） ----
const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);
const COST = { feeUsd: 20, fx: 150, shipOut: 6000, shipBack: 40, cards: 20, duty: 10, taxRate: 10, misc: 100 };
// 鑑定 20×150=3000 / 往路 6000÷20=300 / 復路 40×150÷20=300 / 輸入税 (3000+300)×10%=330 / 関税 10×150÷20=75 / 諸経費 100
assert.deepEqual(L.psaCosts(COST), { grading: 3000, shipOut: 300, shipBack: 300, importTax: 330, usDuty: 75, misc: 100, total: 4105 });
// 初期値: 79.99×155=12398.45 / 385 / 69.99×155÷20=542.4225 / (12398.45+542.4225)×10%=1294.08725 / 30×155÷20=232.5 / 150
const DEF = L.psaCosts({ feeUsd: 79.99, fx: 155, shipOut: 7700, shipBack: 69.99, cards: 20, duty: 30, taxRate: 10, misc: 150 });
near(DEF.grading, 12398.45); near(DEF.shipBack, 542.4225); near(DEF.importTax, 1294.08725); near(DEF.usDuty, 232.5);
near(DEF.total, 15002.45975);
assert.equal(L.psaCosts({ ...COST, taxRate: 0, duty: 0, misc: 0, shipOut: 0, shipBack: 0 }).total, 3000);
assert.equal(L.psaCosts({ ...COST, cards: 1 }).total, 3000 + 6000 + 6000 + 900 + 1500 + 100);
for (const bad of [{ cards: 0 }, { cards: 1.5 }, { fx: 0 }, { fx: -1 }, { feeUsd: NaN }, { misc: -1 }, { taxRate: 101 }, { shipOut: Infinity }, { duty: undefined }])
  assert.equal(L.psaCosts({ ...COST, ...bad }), null);
const SALE = { v10: 30000, v9: 10000, vLow: 3000, p10: 50, p9: 40, pLow: 10 };
assert.equal(L.psaExpected(SALE), 19300); // 15000 + 4000 + 300
assert.equal(L.psaExpected({ ...SALE, p10: 100, p9: 0, pLow: 0 }), 30000);
assert.equal(L.psaExpected({ ...SALE, pLow: 5 }), null);   // 合計95
assert.equal(L.psaExpected({ ...SALE, p10: 60 }), null);   // 合計110
assert.equal(L.psaExpected({ ...SALE, p10: 110, pLow: -50 }), null);
assert.equal(L.psaExpected({ ...SALE, p10: 33.3, p9: 33.3, pLow: 33.4 }) !== null, true);
const P = L.psaProfit({ ...COST, ...SALE, buy: 5000 });
assert.equal(P.expected, 19300); assert.equal(P.costs.total, 4105);
assert.equal(P.profit, 10195);          // 19300 − 4105 − 5000
near(P.marginOnBuy, 203.9);             // 10195 ÷ 5000
near(P.marginOnSpend, 111.9714442613948, 1e-9); // 10195 ÷ 9105
assert.equal(P.breakevenBuy, 15195);
assert.deepEqual([P.if10, P.if9, P.ifLow], [20895, 895, -6105]);
assert.equal(L.psaProfit({ ...COST, ...SALE, buy: 15195 }).profit, 0);
assert.equal(L.psaProfit({ ...COST, ...SALE, buy: 0 }).marginOnBuy, null);
assert.equal(L.psaProfit({ ...COST, ...SALE, buy: -1 }), null);
assert.equal(L.psaProfit({ ...COST, ...SALE, buy: NaN }), null);
assert.equal(L.psaProfit({ ...COST, ...SALE, pLow: 0, buy: 1 }), null);
const M = L.psaMaxBuy({ ...COST, ...SALE, target: 20 });
near(M.exact, 12662.5);                 // 15195 ÷ 1.2
assert.equal(M.maxBuy, 12600); assert.equal(M.breakevenBuy, 15195);
assert.equal(L.psaMaxBuy({ ...COST, ...SALE, target: 0 }).maxBuy, 15100);
assert.equal(L.psaMaxBuy({ ...COST, v10: 1000, v9: 1000, vLow: 1000, p10: 50, p9: 40, pLow: 10, target: 20 }).maxBuy, 0); // 費用倒れ
assert.equal(L.psaMaxBuy({ ...COST, ...SALE, target: -10 }), null);
assert.equal(L.psaMaxBuy({ ...COST, ...SALE }), null);
// 仕入れ上限ちょうどで買うと、仕入れ値に対する利益率が目標と一致する
near(L.psaProfit({ ...COST, ...SALE, buy: M.exact }).marginOnBuy, 20);

assert.deepEqual(L.gradingFee(10, 25, 150, 3000, 40),
  { grading: 37500, shipping: 9000, total: 46500, perCard: 4650, perCardGrading: 3750, perCardShipping: 900 });
assert.equal(L.gradingFee(1, 79.99, 155).total, 79.99 * 155);
assert.equal(L.gradingFee(3, 0, 150, 0, 0).perCard, 0);
for (const a of [[0, 25, 150], [2.5, 25, 150], [10, 25, 0], [10, -1, 150], [10, NaN, 150], [10, 25, 150, -1]]) assert.equal(L.gradingFee(...a), null);

const R = L.cardRoi(3000, 5000, 10, 200);
assert.deepEqual([R.fee, R.net, R.profit, R.marginOnSell], [500, 4300, 1300, 26]);
near(R.roi, 43.333333333, 1e-6); near(R.breakevenSell, 3555.555555556, 1e-6);
assert.equal(L.cardRoi(1000, 1000, 0, 0).profit, 0);
assert.deepEqual(L.cardRoi(0, 0, 10, 0), { fee: 0, net: 0, profit: 0, marginOnSell: null, roi: null, breakevenSell: 0 });
assert.equal(L.cardRoi(1000, 500, 10, 0).profit, -550);
for (const a of [[1000, 2000, 100, 0], [1000, 2000, -1, 0], [-1, 2000, 10, 0], [1000, NaN, 10, 0], [1000, 2000, 10, -5]]) assert.equal(L.cardRoi(...a), null);

// ---- くらし・仕事 ----
assert.equal(L.percentOf(30, 120), 25);
assert.equal(L.percentOf(0, 5), 0);
assert.equal(L.percentOf(5, 0), null);
assert.equal(L.percentage(200, 15), 30);
assert.equal(L.percentage(1980, 0), 0);
assert.equal(L.changeRate(80, 100), 25);
assert.equal(L.changeRate(100, 80), -20);
assert.equal(L.changeRate(-50, -25), 50);
assert.equal(L.changeRate(0, 10), null);
assert.equal(L.percentage(1e308, 1e308), null);
assert.equal(L.percentOf(NaN, 1), null);

assert.equal(L.parseDuration("1:30"), 90);
assert.equal(L.parseDuration(" -0:15 "), -15);
assert.equal(L.parseDuration("１：３０"), 90);
assert.equal(L.parseDuration("100:00"), 6000);
assert.equal(L.parseDuration("-0:00"), 0);
for (const s of ["1:60", "90", "", "1:5", "a:10", "1:30:00", "--1:00"]) assert.equal(L.parseDuration(s), null);
assert.equal(L.formatDuration(-65), "-1:05");
assert.equal(L.formatDuration(0), "0:00");
assert.equal(L.formatDuration(1500), "25:00");
assert.equal(L.formatDuration(1.5), "");
assert.deepEqual(L.sumDurations("1:30\n2:45\n\n-0:15"), { total: 240, count: 3, bad: [] }); // 90+165−15
assert.deepEqual(L.sumDurations("1:30\nabc\n0:10\n9"), { total: 100, count: 2, bad: [2, 4] });
assert.deepEqual(L.sumDurations(""), { total: 0, count: 0, bad: [] });
assert.deepEqual(L.timeDiff(540, 1050, 60), { minutes: 510, work: 450, overnight: false });  // 9:00〜17:30 休憩60分
assert.deepEqual(L.timeDiff(1320, 300, 60), { minutes: 420, work: 360, overnight: true });   // 22:00〜翌5:00
assert.deepEqual(L.timeDiff(600, 600), { minutes: 0, work: 0, overnight: false });
assert.deepEqual(L.timeDiff(1439, 0), { minutes: 1, work: 1, overnight: true });
for (const a of [[540, 600, 61], [1440, 0], [-1, 0], [0.5, 10], [0, 10, -1]]) assert.equal(L.timeDiff(...a), null);

assert.deepEqual(L.wageConvert(1200, "hour", 8, 20), { hourly: 1200, daily: 9600, monthly: 192000, yearly: 2304000 });
assert.deepEqual(L.wageConvert(3000000, "year", 8, 20), { hourly: 1562.5, daily: 12500, monthly: 250000, yearly: 3000000 });
assert.deepEqual(L.wageConvert(250000, "month", 8, 20), { hourly: 1562.5, daily: 12500, monthly: 250000, yearly: 3000000 });
assert.deepEqual(L.wageConvert(10000, "day", 8, 20), { hourly: 1250, daily: 10000, monthly: 200000, yearly: 2400000 });
assert.equal(L.wageConvert(0, "hour", 8, 20).yearly, 0);
for (const a of [[1200, "hour", 0, 20], [1200, "hour", 25, 20], [1200, "hour", 8, 0], [1200, "hour", 8, 32], [-1, "hour", 8, 20], [1200, "week", 8, 20], [NaN, "hour", 8, 20]])
  assert.equal(L.wageConvert(...a), null);

// rand が常に 0 のとき: Floyd で 1→(1が重複)4→5、混ぜると [5,4,1]→[4,5,1]
assert.deepEqual(L.randomUnique(1, 5, 3, () => 0), [4, 5, 1]);
assert.deepEqual(L.randomUnique(7, 7, 1, () => 0), [7]);
const mr = (n) => Math.floor(Math.random() * n);
for (let t = 0; t < 200; t++) {
  const r = L.randomUnique(-3, 6, 10, mr);
  assert.deepEqual([...r].sort((a, b) => a - b), [-3, -2, -1, 0, 1, 2, 3, 4, 5, 6]); // 全部引けば並べ替えになる
  const q = L.randomUnique(1, 1000000, 50, mr);
  assert.equal(new Set(q).size, 50);
  assert.ok(q.every((v) => Number.isInteger(v) && v >= 1 && v <= 1000000));
}
// 偏りの粗い確認: 1〜4 から2個を6000回、各数字はおよそ3000回（±5σ ≒ ±194）、先頭に来る回数はおよそ1500回
const hits = [0, 0, 0, 0], first = [0, 0, 0, 0];
for (let t = 0; t < 6000; t++) { const r = L.randomUnique(1, 4, 2, mr); r.forEach((v) => hits[v - 1]++); first[r[0] - 1]++; }
assert.ok(hits.every((h) => Math.abs(h - 3000) < 200), String(hits));
assert.ok(first.every((h) => Math.abs(h - 1500) < 170), String(first));
assert.equal(L.randomUnique(1, 0x100000000, 1, () => 0x100000000 - 1).length, 1);
for (const a of [[5, 1, 1], [1, 5, 6], [1, 5, 0], [1.5, 5, 1], [1, 5, NaN], [0, 0x100000000, 1], [1, 20000, 10001]]) assert.equal(L.randomUnique(...a, mr), null);
assert.deepEqual(L.pickFromList(["a", "b", "c", "d", "e"], 3, () => 0), ["d", "e", "a"]);
assert.equal(L.pickFromList([], 1, mr), null);
assert.equal(L.pickFromList(["a"], 2, mr), null);

assert.deepEqual(L.baseConvert("255", 10), { 2: "11111111", 8: "377", 10: "255", 16: "FF" });
assert.deepEqual(L.baseConvert("0xff", 16), { 2: "11111111", 8: "377", 10: "255", 16: "FF" });
assert.deepEqual(L.baseConvert("1111 1111", 2), { 2: "11111111", 8: "377", 10: "255", 16: "FF" });
assert.deepEqual(L.baseConvert("-1010", 2), { 2: "-1010", 8: "-12", 10: "-10", 16: "-A" });
assert.deepEqual(L.baseConvert("0", 8), { 2: "0", 8: "0", 10: "0", 16: "0" });
assert.equal(L.baseConvert("-0", 10)[10], "0");
assert.equal(L.baseConvert("１０", 10)[2], "1010");
assert.equal(L.baseConvert("0b1", 16)[10], "177"); // 16進では 0b1 は B1
assert.equal(L.baseConvert("18446744073709551616", 10)[16], "10000000000000000"); // 2^64
assert.equal(L.baseConvert("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", 16)[10], "340282366920938463463374607431768211455"); // 2^128−1
for (const a of [["12", 2], ["8", 8], ["1.5", 10], ["", 10], ["-", 10], ["0x", 16], ["G", 16], ["1e3", 10], ["10", 3], ["1".repeat(4097), 2]]) assert.equal(L.baseConvert(...a), null);

assert.equal(L.toKatakana("ひらがな ぁゔゖ ゝゞ ABC ー 漢字"), "ヒラガナ ァヴヶ ヽヾ ABC ー 漢字");
assert.equal(L.toHiragana("カタカナ ァヴヶ ヽヾ ABC ー ヷ ｶﾅ"), "かたかな ぁゔゖ ゝゞ ABC ー ヷ ｶﾅ");
assert.equal(L.toHiragana(L.toKatakana("ぱぴぷぺぽ、んっ")), "ぱぴぷぺぽ、んっ");
assert.equal(L.toKatakana(""), "");

assert.deepEqual(L.aspectRatio(1920, 1080), { decimal: 1920 / 1080, rw: 16, rh: 9 });
assert.deepEqual(L.aspectRatio(1080, 1920), { decimal: 0.5625, rw: 9, rh: 16 });
assert.deepEqual(L.aspectRatio(500, 500), { decimal: 1, rw: 1, rh: 1 });
assert.deepEqual(L.aspectRatio(2.35, 1), { decimal: 2.35, rw: null, rh: null });
for (const a of [[0, 1], [1, 0], [-16, 9], [NaN, 9], [Infinity, 9]]) assert.equal(L.aspectRatio(...a), null);
assert.equal(L.aspectScale(16, 9, { width: 1280 }), 720);
assert.equal(L.aspectScale(16, 9, { height: 1080 }), 1920);
assert.equal(L.aspectScale(4, 3, { width: 1000 }), 750);
assert.equal(L.aspectScale(16, 9, { width: 0 }), null);
assert.equal(L.aspectScale(0, 9, { width: 100 }), null);
assert.equal(L.aspectScale(16, 9, { height: NaN }), null);
console.log("lib ok");
