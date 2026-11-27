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

// フリマと買取の手取り比較。期待値は products/kaitori-kit/計算例.md の例1・3・4・5 と手計算
const FK = (...a) => L.furimaVsKaitori(...a);
assert.deepEqual(FK(10000, 10, 210, 93), { fee: 1000, furima: 8790, kaitoriGaku: 9300, kaitori: 9300, diff: 510, breakevenRate: 87.9 });
assert.deepEqual(FK(10000, 10, 210, 93, 0, 0), FK(10000, 10, 210, 93));                       // 省略時は売り手負担 0
assert.deepEqual(FK(10000, 10, 210, 93, 520), { fee: 1000, furima: 8790, kaitoriGaku: 9300, kaitori: 8780, diff: -10, breakevenRate: 93.1 });
assert.deepEqual(FK(60000, 10, 2100, 93), { fee: 6000, furima: 51900, kaitoriGaku: 55800, kaitori: 55800, diff: 3900, breakevenRate: 86.5 });
assert.deepEqual(FK(3000, 10, 210, 93), { fee: 300, furima: 2490, kaitoriGaku: 2790, kaitori: 2790, diff: 300, breakevenRate: 83 });
assert.deepEqual(FK(10000, 10, 210, 93, 300, 220), { fee: 1000, furima: 8790, kaitoriGaku: 9300, kaitori: 8780, diff: -10, breakevenRate: 93.1 }); // (8790+520)÷10000
// 端数: 999×10%=99.9→99、999×93%=929.07→929。同じになる率 690÷999=69.069…→69.1
assert.deepEqual(FK(999, 10, 210, 93), { fee: 99, furima: 690, kaitoriGaku: 929, kaitori: 929, diff: 239, breakevenRate: 69.1 });
// 浮動小数の誤差: 10000×4.35 は JS では 43499.99… になるが、手数料は 435円
assert.equal(FK(10000, 4.35, 0, 0).fee, 435);
assert.equal(FK(1000, 0.1, 0, 0).fee, 1);
assert.equal(FK(999, 0.1, 0, 0).fee, 0);                                                      // 0.999 → 0
assert.equal(FK(300, 33.3333, 0, 33.3334).fee, 99);                                           // 99.9999 → 99
assert.equal(FK(300, 33.3333, 0, 33.3334).kaitoriGaku, 100);                                  // 100.0002 → 100
// 手取りが同じ・境界
assert.deepEqual(FK(10000, 10, 210, 87.9), { fee: 1000, furima: 8790, kaitoriGaku: 8790, kaitori: 8790, diff: 0, breakevenRate: 87.9 });
assert.deepEqual(FK(1, 0, 0, 0), { fee: 0, furima: 1, kaitoriGaku: 0, kaitori: 0, diff: -1, breakevenRate: 100 });
assert.deepEqual(FK(1, 100, 0, 100), { fee: 1, furima: 0, kaitoriGaku: 1, kaitori: 1, diff: 1, breakevenRate: 0 });
assert.equal(FK(10000, 0, 0, 1000).kaitori, 100000);                                          // 買取率の上限
assert.equal(FK(2000, 0, 5, 0).breakevenRate, 99.8);                                          // 99.75 → 99.8（四捨五入）
assert.equal(FK(2000, 0, 6, 0).breakevenRate, 99.7);                                          // 99.70
assert.equal(FK(3000, 0, 1, 0).breakevenRate, 100);                                           // 99.966… → 100.0
// フリマの手取りがマイナス（送料が相場を上回る）: 金額はそのまま出し、同じになる買取率は「なし」
assert.deepEqual(FK(100, 10, 210, 93), { fee: 10, furima: -120, kaitoriGaku: 93, kaitori: 93, diff: 213, breakevenRate: null });
assert.equal(FK(100, 10, 210, 93, 120).breakevenRate, 0);                                     // −120 + 120 = 0
assert.equal(FK(100, 0, 0, 50, 80).kaitori, -30);                                             // 買取の手取りもマイナスになりうる
// 上限いっぱいでも桁あふれしない
assert.deepEqual(FK(L.MAX_YEN, 100, L.MAX_YEN, 1000, L.MAX_YEN, L.MAX_YEN),
  { fee: 1e12, furima: -1e12, kaitoriGaku: 1e13, kaitori: 8e12, diff: 9e12, breakevenRate: 100 });
for (const a of [[0, 10, 210, 93], [-1, 10, 210, 93], [1000.5, 10, 210, 93], [L.MAX_YEN + 1, 10, 210, 93], [NaN, 10, 210, 93], [Infinity, 10, 210, 93],
  [10000, -0.1, 210, 93], [10000, 100.1, 210, 93], [10000, NaN, 210, 93], [10000, 10, -1, 93], [10000, 10, 210.5, 93], [10000, 10, L.MAX_YEN + 1, 93],
  [10000, 10, 210, -1], [10000, 10, 210, 1000.1], [10000, 10, 210, NaN], [10000, 10, 210, Infinity],
  [10000, 10, 210, 93, -1], [10000, 10, 210, 93, 0.5], [10000, 10, 210, 93, 0, -1], [10000, 10, 210, 93, 0, NaN], [10000, "10", 210, 93], [null, 10, 210, 93]])
  assert.equal(FK(...a), null, JSON.stringify(a));

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
// ---- 入力チェック（境界値: 0・負数・小数・空・範囲の両端とその外側） ----
// app.js は空欄を null、数字として読めない入力を NaN で渡す。lib はどちらも不正として扱う。
const JUNK = [NaN, Infinity, -Infinity, undefined, null, "", "5"];
// 金額: 0以上の整数、上限1兆円
for (const v of [0, 1, 999, L.MAX_YEN]) assert.equal(L.yenError(v), null);
for (const v of [-1, -0.5, 0.5, 1000.5, L.MAX_YEN + 1, ...JUNK]) assert.equal(typeof L.yenError(v), "string", String(v));
assert.equal(L.yenError(-1), "金額は0以上の整数で入力してください。");
assert.equal(L.yenError(1.5, "合計金額"), "合計金額は0以上の整数で入力してください。");
assert.equal(L.yenError(L.MAX_YEN + 1), "金額は1兆円以下で入力してください。");

// 割り勘
assert.deepEqual(L.splitBill(0, 1, 1), { each: 0, surplus: 0 });
assert.deepEqual(L.splitBill(1, 1, 1), { each: 1, surplus: 0 });
assert.deepEqual(L.splitBill(1000, 3), { each: 334, surplus: 2 });
assert.deepEqual(L.splitBill(100, 1000, 1), { each: 1, surplus: 900 });
assert.deepEqual(L.splitBill(L.MAX_YEN, L.MAX_PEOPLE, 1000), { each: 1000000, surplus: 0 });
assert.equal(L.splitBillError(10000, 3, 100), null);
assert.equal(L.splitBillError(-1, 3, 100), "合計金額は0以上の整数で入力してください。");
assert.equal(L.splitBillError(1000.5, 3, 100), "合計金額は0以上の整数で入力してください。");
assert.equal(L.splitBillError(L.MAX_YEN + 1, 3, 100), "合計金額は1兆円以下で入力してください。");
for (const p of [0, -1, 0.5, 2.5, ...JUNK]) {
  assert.equal(L.splitBillError(1000, p, 100), "人数は1以上の整数で入力してください。", String(p));
  assert.equal(L.splitBill(1000, p, 100), null);
}
assert.equal(L.splitBillError(1000, L.MAX_PEOPLE, 1), null);
assert.equal(L.splitBillError(1000, L.MAX_PEOPLE + 1, 1), "人数は100万人以下で入力してください。");
for (const u of [0, -100, 1.5, NaN]) assert.equal(L.splitBill(1000, 2, u), null);
for (const t of [-1, 0.5, 1000.5, L.MAX_YEN + 1, ...JUNK]) assert.equal(L.splitBill(t, 2, 100), null, String(t));

// 消費税
assert.deepEqual(L.taxFromNet(0, 10), { net: 0, tax: 0, gross: 0 });
assert.deepEqual(L.taxFromGross(0, 10), { net: 0, tax: 0, gross: 0 });
assert.deepEqual(L.taxFromNet(1, 10), { net: 1, tax: 0, gross: 1 });
assert.deepEqual(L.taxFromNet(999, 10, "round"), { net: 999, tax: 100, gross: 1099 });
assert.deepEqual(L.taxFromNet(991, 10, "ceil"), { net: 991, tax: 100, gross: 1091 });
assert.deepEqual(L.taxFromNet(500, 0), { net: 500, tax: 0, gross: 500 });
assert.deepEqual(L.taxFromNet(500, 100), { net: 500, tax: 500, gross: 1000 });
assert.deepEqual(L.taxFromGross(L.MAX_YEN, 10), { net: 909090909091, tax: 90909090909, gross: L.MAX_YEN });
for (const f of [L.taxFromNet, L.taxFromGross]) {
  for (const v of [-1, -100, 0.5, 99.9, L.MAX_YEN + 1, ...JUNK]) assert.equal(f(v, 10), null, String(v));
  for (const r of [-1, -0.1, 100.1, 101, NaN, Infinity, undefined]) assert.equal(f(100, r), null, String(r));
  assert.equal(f(100, 10, "trunc"), null);
  assert.equal(f(100, 10, "constructor"), null);
}
assert.equal(L.taxError(100, 10, "floor"), null);
assert.equal(L.taxError(-100, 10), "金額は0以上の整数で入力してください。");
assert.equal(L.taxError(100.5, 10), "金額は0以上の整数で入力してください。");
assert.equal(L.taxError(100, 101), "税率は0〜100の範囲で指定してください。");

// 割引・ポイント還元
assert.deepEqual(L.discount(0, 30, 10), { pay: 0, saved: 0, points: 0, effective: 0 });
assert.deepEqual(L.discount(1000, 0, 0), { pay: 1000, saved: 0, points: 0, effective: 1000 });
assert.deepEqual(L.discount(1000, 100, 10), { pay: 0, saved: 1000, points: 0, effective: 0 });
assert.deepEqual(L.discount(1000, 0, 100), { pay: 1000, saved: 0, points: 1000, effective: 0 });
assert.deepEqual(L.discount(1000, 12.5, 0.5), { pay: 875, saved: 125, points: 4, effective: 871 });
assert.deepEqual(L.discount(125, 66.4, 0), { pay: 42, saved: 83, points: 0, effective: 42 }); // 125×0.336 = 42 ちょうど（浮動小数では 41.99…）
assert.equal(L.discountError(1980, 30, 10), null);
assert.equal(L.discountError(1980, 0, 0), null);
assert.equal(L.discountError(1980, 100, 100), null);
assert.equal(L.discountError(-1, 0, 0), "元の価格は0以上の整数で入力してください。");
assert.equal(L.discountError(1980.5, 0, 0), "元の価格は0以上の整数で入力してください。");
for (const r of [-0.1, -1, 100.1, 101, 150, NaN, Infinity, undefined, null, "5"]) {
  assert.equal(L.discountError(1000, r, 0), "割引率は0〜100の範囲で入力してください。", String(r));
  assert.equal(L.discount(1000, r, 0), null);
  if (r === undefined) continue; // ポイント還元率は省略すると0%
  assert.equal(L.discountError(1000, 0, r), "ポイント還元率は0〜100の範囲で入力してください。", String(r));
  assert.equal(L.discount(1000, 0, r), null);
}
for (const v of [-1, 0.5, L.MAX_YEN + 1, ...JUNK]) assert.equal(L.discount(v, 10, 1), null, String(v));

// 日付
assert.deepEqual(L.parseDate("2026-11-27"), [2026, 11, 27]);
assert.deepEqual(L.parseDate("2024-02-29"), [2024, 2, 29]);
assert.deepEqual(L.parseDate("0001-01-01"), [1, 1, 1]);
assert.deepEqual(L.parseDate("9999-12-31"), [9999, 12, 31]);
for (const s of ["", "2026-02-29", "2026-02-30", "2026-13-01", "2026-00-10", "2026-04-31", "0000-01-01", "10000-01-01", "+010000-01-01", "2026/11/27", "2026-1-1", "abc", undefined, null])
  assert.equal(L.parseDate(s), null, String(s));
assert.ok(L.validDate(50, 1, 1) && L.validDate(1900, 2, 28) && !L.validDate(1900, 2, 29) && L.validDate(2000, 2, 29));
assert.ok(!L.validDate(2026, 1.5, 1) && !L.validDate(NaN, 1, 1) && !L.validDate(2026, 0, 1) && !L.validDate(2026, 1, 32));
assert.equal(L.daysBetween([50, 1, 1], [50, 12, 31]), 364);      // 西暦50年を1950年と読み替えない
assert.equal(L.daysBetween([99, 12, 31], [100, 1, 1]), 1);
assert.equal(L.weekday([2024, 2, 29]), "木");

// 日数計算
assert.deepEqual(L.daySpan([2026, 11, 27], [2026, 11, 27]), { days: 0, abs: 0, before: false, inclusive: 1, weeks: 0, rest: 0 });
assert.deepEqual(L.daySpan([2026, 11, 27], [2026, 11, 28]), { days: 1, abs: 1, before: false, inclusive: 2, weeks: 0, rest: 1 });
assert.deepEqual(L.daySpan([2026, 11, 27], [2026, 12, 4]), { days: 7, abs: 7, before: false, inclusive: 8, weeks: 1, rest: 0 });
assert.deepEqual(L.daySpan([2026, 11, 27], [2027, 1, 1]), { days: 35, abs: 35, before: false, inclusive: 36, weeks: 5, rest: 0 });
assert.deepEqual(L.daySpan([2026, 11, 27], [2026, 11, 26]), { days: -1, abs: 1, before: true, inclusive: 2, weeks: 0, rest: 1 });
assert.deepEqual(L.daySpan([2026, 11, 27], [2026, 11, 17]), { days: -10, abs: 10, before: true, inclusive: 11, weeks: 1, rest: 3 }); // 以前は「-1週と-3日」
assert.deepEqual(L.daySpan([2026, 11, 27], [2026, 11, 20]), { days: -7, abs: 7, before: true, inclusive: 8, weeks: 1, rest: 0 });  // 以前は「-1週と-0日」
assert.deepEqual(L.addDays([2026, 11, 27], 0), [2026, 11, 27]);
assert.deepEqual(L.addDays([2026, 11, 27], -0), [2026, 11, 27]);
assert.deepEqual(L.addDays([2026, 11, 27], 100), [2027, 3, 7]);
assert.deepEqual(L.addDays([2026, 3, 1], -1), [2026, 2, 28]);
assert.deepEqual(L.addDays([2024, 3, 1], -1), [2024, 2, 29]);
assert.deepEqual(L.addDays([9999, 12, 30], 1), [9999, 12, 31]);
assert.equal(L.addDays([9999, 12, 31], 1), null);
assert.deepEqual(L.addDays([1, 1, 2], -1), [1, 1, 1]);
assert.equal(L.addDays([1, 1, 1], -1), null);
for (const n of [0.5, -1.5, 1e300, L.DAY_OFFSET_MAX + 1, -L.DAY_OFFSET_MAX - 1, ...JUNK]) {
  assert.equal(L.addDays([2026, 11, 27], n), null, String(n));
  assert.equal(typeof L.dayOffsetError(n), "string", String(n));
}
for (const n of [0, 1, -1, L.DAY_OFFSET_MAX, -L.DAY_OFFSET_MAX]) assert.equal(L.dayOffsetError(n), null);
assert.equal(L.dayOffsetError(1.5), "◯日後の日数は整数で入力してください（◯日前はマイナスの整数）。");

// 和暦変換
for (const y of [1873, 2019, 2026, 2200]) assert.equal(L.seirekiError(y), null);
for (const y of [1872, 2201, 0, -1, 2026.5, ...JUNK]) assert.equal(L.seirekiError(y), "西暦は1873〜2200の整数で入力してください。", String(y));
assert.deepEqual(L.eraYearRange("令和"), [1, 182]);
assert.deepEqual(L.eraYearRange("平成"), [1, 31]);
assert.deepEqual(L.eraYearRange("昭和"), [1, 64]);
assert.deepEqual(L.eraYearRange("大正"), [1, 15]);
assert.deepEqual(L.eraYearRange("明治"), [6, 45]);
assert.equal(L.eraYearRange("慶応"), null);
assert.equal(L.toSeireki("令和", 1), 2019);
assert.equal(L.toSeireki("平成", 1), 1989);
assert.equal(L.toSeireki("大正", 15), 1926);
assert.equal(L.toSeireki("明治", 6), 1873);
assert.equal(L.toSeireki("令和", 182), 2200);
for (const [e, n] of [["令和", 183], ["平成", 32], ["大正", 16], ["明治", 5], ["明治", 46], ["令和", 0], ["令和", -1], ["令和", 1.5], ["平成", 30.5], ["慶応", 1], ["令和", NaN], ["令和", undefined], ["令和", null], ["令和", "8"]])
  assert.equal(L.toSeireki(e, n), null, `${e}${n}`);
assert.equal(L.eraYearError("令和", 8), null);
for (const n of [0, -1, 1.5, 0.5, NaN, Infinity, undefined, null]) assert.equal(L.eraYearError("平成", n), "年は1以上の整数で入力してください。", String(n));
assert.equal(L.eraYearError("平成", 32), "平成は1〜31年の範囲で入力してください。");
assert.equal(L.eraYearError("明治", 5), "明治は6〜45年の範囲で入力してください。");
assert.equal(L.eraYearError("令和", 183), "令和は1〜182年の範囲で入力してください。");
assert.equal(L.yearLabel(2026, 4, 1), "2026年（令和8年）");
assert.equal(L.yearLabel(2019, 4, 1), "2019年（平成31年）");
assert.equal(L.yearLabel(1872, 4, 1), "1872年");
assert.equal(L.yearLabel(1873, 1, 1), "1873年（明治6年）");
assert.equal(L.eto(1), "酉");
assert.equal(L.eto(-1), L.eto(11));

// 年齢・入学卒業年
assert.equal(L.ageError([2000, 1, 1], [2026, 11, 27]), null);
assert.equal(L.ageError([2026, 11, 27], [2026, 11, 27]), null);                 // 当日は0歳
assert.equal(L.age([2026, 11, 27], [2026, 11, 27]), 0);
assert.equal(L.ageError([2026, 11, 28], [2026, 11, 27]), "生年月日は基準日以前の日付にしてください。");
assert.equal(L.ageError([2030, 1, 1], [2026, 11, 27]), "生年月日は基準日以前の日付にしてください。");
assert.equal(L.age([2024, 2, 29], [2025, 2, 28]), 0);
assert.equal(L.age([2024, 2, 29], [2025, 3, 1]), 1);
assert.equal(L.schoolYears(1850, 5, 1)[0].enter, 1857);
assert.equal(L.schoolYears(2030, 4, 1)[3].grad, 2052);

// 単位変換
assert.equal(L.convert("長さ", 0, "m", "cm"), 0);
assert.ok(Object.is(L.convert("長さ", -0, "m", "cm"), 0));                     // -0 を返さない
assert.equal(L.convert("長さ", -1, "m", "cm"), -100);
assert.equal(L.convert("面積", 1e308, "ha", "㎡"), null);                       // 桁あふれ
for (const v of [NaN, Infinity, "1", undefined, null]) assert.equal(L.convert("長さ", v, "m", "cm"), null, String(v));
assert.equal(L.convert("長さ", 1, "m", "里"), null);
assert.equal(L.convert("時間", 1, "m", "cm"), null);

// パスワード
const SETS3 = ["abc", "XYZ", "123"];
for (const n of [4, 5, 16, 63, 64]) {
  assert.equal(L.passwordError(n, SETS3), null);
  assert.equal(L.password(n, SETS3, mr).length, n);
}
for (const n of [3, 0, -1, 65, 100, 4.5, 16.5, 63.9, 1e9, ...JUNK]) {
  assert.equal(L.passwordError(n, SETS3), "長さは4〜64の整数で入力してください。", String(n));
  assert.equal(L.password(n, SETS3, mr), "", String(n));
}
assert.equal(L.passwordError(16, []), "文字の種類を1つ以上選んでください。");
assert.equal(L.password(16, [], mr), "");
const p4 = L.password(4, ["abc", "XYZ", "123", "!#"], mr);                       // 4種類・4文字: 各種類が1文字ずつ
assert.ok(["abc", "XYZ", "123", "!#"].every((s) => [...p4].some((c) => s.includes(c))), p4);

// 桁の上限と、ごく小さい数での桁あふれ
assert.ok(!L.tooLarge(L.MAX_ABS) && !L.tooLarge(-L.MAX_ABS) && !L.tooLarge(0) && L.tooLarge(L.MAX_ABS * 2) && L.tooLarge(-1e308) && L.tooLarge(Infinity));
assert.equal(L.psaProfit({ ...COST, ...SALE, buy: 1e-320 }).marginOnBuy, null);   // 以前は Infinity
assert.equal(L.cardRoi(1e-320, 5, 10, 0).roi, null);
assert.equal(L.cardRoi(5, 1e-320, 10, 0).marginOnSell, null);
assert.equal(L.changeRate(1e-320, 5), null);

// ---- 早見ページ（期待値は手計算） ----
import { hayamiData, BORN_MIN } from "./hayami.mjs";
// 改元の境界: 前日と当日
assert.equal(L.toWareki(1926, 12, 24).label, "大正15年");
assert.equal(L.toWareki(1926, 12, 25).label, "昭和元年");
assert.equal(L.toWareki(1989, 1, 7).label, "昭和64年");
assert.equal(L.toWareki(1989, 1, 8).label, "平成元年");
assert.equal(L.toWareki(2019, 4, 30).label, "平成31年");
assert.equal(L.toWareki(2019, 5, 1).label, "令和元年");
assert.equal(L.toWareki(1912, 7, 30).label, "大正元年");
const wy = (y) => L.warekiOfYear(y).map((w) => [w.label, w.from, w.to]);
assert.deepEqual(wy(1990), [["平成2年", [1, 1], [12, 31]]]);
assert.deepEqual(wy(1926), [["大正15年", [1, 1], [12, 24]], ["昭和元年", [12, 25], [12, 31]]]);
assert.deepEqual(wy(1989), [["昭和64年", [1, 1], [1, 7]], ["平成元年", [1, 8], [12, 31]]]);
assert.deepEqual(wy(2019), [["平成31年", [1, 1], [4, 30]], ["令和元年", [5, 1], [12, 31]]]);
assert.deepEqual(wy(1912), [["明治45年", [1, 1], [7, 29]], ["大正元年", [7, 30], [12, 31]]]);
assert.deepEqual(wy(1873), [["明治6年", [1, 1], [12, 31]]]);
assert.deepEqual(wy(1872), []);
assert.equal(L.warekiYearLabel(1989), "昭和64年・平成元年");
assert.equal(L.warekiYearLabel(1975), "昭和50年");
// 期間の端の日が、その元号に入っていること（全対象年）
for (let y = 1873; y <= 2100; y++) for (const w of L.warekiOfYear(y)) {
  assert.equal(L.toWareki(y, ...w.from).label, w.label, `${y} from`);
  assert.equal(L.toWareki(y, ...w.to).label, w.label, `${y} to`);
  assert.equal(L.toSeireki(w.era, w.year), y);
}
assert.equal(L.toSeireki("昭和", 50), 1975);
assert.equal(L.toSeireki("令和", 1), 2019);
assert.equal(L.toSeireki("平成", 1), 1989);
assert.equal(L.toSeireki("大正", 15), 1926);
assert.equal(L.toSeireki("昭和", 1), 1926);
assert.equal(L.toSeireki("明治", 6), 1873);
// 干支: 1990年は午、1989年は巳、2019年は亥、1926年は寅、1975年は卯
assert.deepEqual([1990, 1989, 2019, 1926, 1975].map((y) => L.eto(y) + L.etoKana(y)), ["午うま", "巳み", "亥い", "寅とら", "卯う"]);
// 年齢: 1990年生まれは2026年に、誕生日の前35歳・後36歳・数え年37歳
assert.deepEqual(L.ageInYear(1990, 2026), { before: 35, after: 36, kazoe: 37 });
assert.deepEqual(L.ageInYear(2026, 2026), { before: -1, after: 0, kazoe: 1 });
assert.equal(L.ageInYear(1990, 2026).before, L.age([1990, 11, 28], [2026, 11, 27]));
assert.equal(L.ageInYear(1990, 2026).after, L.age([1990, 11, 27], [2026, 11, 27]));
assert.equal(L.ageLabel(-1), "まだ生まれていません");
assert.equal(L.ageLabel(0), "0歳");
// 入学・卒業年の学年の境界: 4月1日までが早生まれ、4月2日からが次の学年。ページの2つの表は 4月1日 と 4月2日 で計算する
const sy = (y, m, d) => L.schoolYears(y, m, d).map((s) => [s.enter, s.grad]);
assert.deepEqual(sy(1990, 4, 2), [[1997, 2003], [2003, 2006], [2006, 2009], [2009, 2013]]);
assert.deepEqual(sy(1990, 4, 1), [[1996, 2002], [2002, 2005], [2005, 2008], [2008, 2012]]);
for (const y of [1926, 1989, 1990, 2019, 2026]) {
  assert.deepEqual(sy(y, 1, 1), sy(y, 4, 1));      // 1月1日〜4月1日は同じ学年
  assert.deepEqual(sy(y, 3, 31), sy(y, 4, 1));
  assert.deepEqual(sy(y, 12, 31), sy(y, 4, 2));    // 4月2日〜12月31日は同じ学年
  assert.deepEqual(sy(y, 4, 1), sy(y - 1, 4, 2));  // 早生まれは前の年の4月2日以降生まれと同じ学年
}
// 節目: 1990年生まれの還暦は2050年（満60歳・数え年61歳）、古希は数え年で2059年・満年齢で2060年
const ms = Object.fromEntries(L.milestones(1990).map((m) => [m.name, [m.yearKazoe, m.yearMan]]));
assert.deepEqual(ms, { 還暦: [2050, 2050], 古希: [2059, 2060], 喜寿: [2066, 2067], 傘寿: [2069, 2070], 米寿: [2077, 2078], 卒寿: [2079, 2080], 白寿: [2088, 2089] });
for (const m of L.milestones(1990)) {
  assert.equal(L.ageInYear(1990, m.yearKazoe).kazoe, m.kazoe, m.name);
  assert.equal(L.ageInYear(1990, m.yearMan).after, m.man, m.name);
}
assert.deepEqual(L.etoYears(1990), [2002, 2014, 2026, 2038, 2050, 2062, 2074, 2086]);
assert.ok(L.etoYears(1990).every((y) => L.eto(y) === L.eto(1990)));
// 日付で変わる値
assert.deepEqual(L.hayamiNow({ kind: "born", year: 1990 }, [2026, 11, 27]),
  { asof: "2026年11月時点", year: "2026年（令和8年）", before: "35歳", after: "36歳", kazoe: "37歳" });
assert.deepEqual(L.hayamiNow({ kind: "era", era: "昭和", n: 50 }, [2026, 11, 27]),
  { asof: "2026年11月時点", year: "2026年（令和8年）", before: "50歳", after: "51歳", kazoe: "52歳", ago: "51年前", ifCont: "昭和101年" });
assert.equal(L.hayamiNow({ kind: "era", era: "令和", n: 8 }, [2026, 1, 1]).ago, "今年");
assert.equal(L.hayamiNow({ kind: "era", era: "明治", n: 6 }, [2026, 1, 1]).ifCont, "明治159年");   // 1868年が明治元年
assert.equal(L.hayamiNow({ kind: "born", year: 1990 }, [2027, 1, 1]).after, "37歳");
assert.equal(L.hayamiNow({ kind: "born", year: 1989 }, [2019, 3, 1]).year, "2019年（平成31年・令和元年）");
assert.equal(L.hayamiNow({ kind: "born", year: 2027 }, [2026, 11, 27]), null);
assert.equal(L.hayamiNow({ kind: "era", era: "昭和", n: 65 }, [2026, 11, 27]), null);
// build.py に渡すデータ（2026-11-27 でビルドした場合）
const HD = hayamiData([2026, 11, 27]);
assert.equal(BORN_MIN, 1926);
assert.deepEqual([HD.born.length, HD.born[0].year, HD.born.at(-1).year], [101, 1926, 2026]);
assert.equal(HD.era.length, 40 + 15 + 64 + 31 + 8);   // 明治6〜45、大正1〜15、昭和1〜64、平成1〜31、令和1〜8
assert.deepEqual([HD.era[0].label, HD.era.at(-1).label], ["明治6年", "令和8年"]);
assert.equal(new Set(HD.era.map((x) => `${x.slug}/${x.n}`)).size, HD.era.length);
assert.ok(HD.era.every((x, i) => i === 0 || x.year >= HD.era[i - 1].year));   // 古い順
const b90 = HD.born.find((b) => b.year === 1990), b89 = HD.born.find((b) => b.year === 1989);
assert.deepEqual([b90.warekiLabel, b90.eto, b90.ages[36].year, b90.ages[100].year, b90.ages[100].wareki], ["平成2年", "午", 2026, 2090, "令和72年"]);
assert.deepEqual(b90.school.normal.map((s) => [s.enter, s.enterWareki, s.grad, s.gradWareki]),
  [[1997, "平成9年", 2003, "平成15年"], [2003, "平成15年", 2006, "平成18年"], [2006, "平成18年", 2009, "平成21年"], [2009, "平成21年", 2013, "平成25年"]]);
assert.deepEqual(b90.school.early.map((s) => [s.enter, s.grad]), [[1996, 2002], [2002, 2005], [2005, 2008], [2008, 2012]]);
// 入学・卒業の和暦はその月の元号。改元のあった年にかかる例で確かめる。
// 2012年4月2日生まれ: 小学校入学 2019年4月 = 平成31年（令和は5月から）。1982年4月2日生まれ: 小学校入学 1989年4月 = 平成元年。
assert.equal(HD.born.find((b) => b.year === 2012).school.normal[0].enterWareki, "平成31年");
assert.equal(HD.born.find((b) => b.year === 1982).school.normal[0].enterWareki, "平成元年");
assert.equal(HD.born.find((b) => b.year === 1983).school.early[0].enterWareki, "平成元年");
assert.deepEqual([1977].map((y) => HD.born.find((b) => b.year === y).school.early[0]).map((s) => [s.grad, s.gradWareki]), [[1989, "平成元年"]]);   // 1977年の早生まれ: 小学校卒業 1989年3月 = 平成元年（1月8日から）
assert.deepEqual(b89.wareki.map((w) => `${w.label} ${w.fromLabel}〜${w.toLabel}`), ["昭和64年 1月1日〜1月7日", "平成元年 1月8日〜12月31日"]);
// いまの学校制度になる前に小学校へ入学する年代（早生まれの入学が1947年より前）には表を出さない
assert.deepEqual([1926, 1940, 1941, 1990].map((y) => HD.born.find((b) => b.year === y).schoolOk), [false, false, true, true]);
const eraOf = (era, n) => HD.era.find((x) => x.era === era && x.n === n);
assert.deepEqual([eraOf("昭和", 50).year, eraOf("昭和", 50).eto, eraOf("昭和", 50).other], [1975, "卯", null]);
assert.deepEqual([eraOf("令和", 1).year, eraOf("令和", 1).from, eraOf("令和", 1).to, eraOf("令和", 1).other.label], [2019, "5月1日", "12月31日", "平成31年"]);
assert.deepEqual([eraOf("平成", 31).from, eraOf("平成", 31).to, eraOf("平成", 31).other.label], ["1月1日", "4月30日", "令和元年"]);
assert.deepEqual([eraOf("昭和", 64).to, eraOf("平成", 1).from], ["1月7日", "1月8日"]);
assert.deepEqual([eraOf("大正", 15).to, eraOf("昭和", 1).from, eraOf("昭和", 1).year], ["12月24日", "12月25日", 1926]);
assert.equal(eraOf("昭和", 65), undefined);
assert.equal(eraOf("令和", 9), undefined);
assert.equal(hayamiData([2027, 1, 1]).born.at(-1).year, 2027);   // 年が変わると対象年が1年増える
// 買取価格の比較ページ: 取得から48時間を過ぎたら「古い」
const T0 = Date.parse("2026-11-27T14:45:00+09:00");
assert.equal(L.isStale("2026-11-27T14:45:00+09:00", T0 + 48 * 3600e3, 48), false);   // ちょうど48時間はまだ出さない
assert.equal(L.isStale("2026-11-27T14:45:00+09:00", T0 + 48 * 3600e3 + 1, 48), true);
assert.equal(L.isStale("2026-11-27T05:45:00Z", T0 + 3600e3, 48), false);   // 時差の書き方が違っても同じ時刻
assert.equal(L.isStale("", T0, 48), true);   // 読めない日時は古いものとして扱う
console.log("lib ok");
