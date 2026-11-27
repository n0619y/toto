// 実行: node --test src/test.mjs
// tejori.js が products/kaitori-kit/tejori.py と同じ結果になることを確かめる。
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { furimaTejori, hikaku, kaitoriGaku, kaitoriTejori } from "./tejori.js";

test("計算例 例1: 相場10,000・手数料10%・送料210・買取率93%", () => {
  const h = hikaku(10000, 10, 210, 93);
  assert.equal(h.furimaTejori, 8790);
  assert.equal(h.kaitoriTejori, 9300);
  assert.equal(h.kaitoriGaku, 9300);
  assert.equal(h.uriteSagaku, 510);
  assert.equal(h.gyakutenRitsu, "87.90");
  assert.equal(h.saiteiRitsu, "87.9");
});

test("計算例 例3: 売り手が送料520円を負担すると、フリマのほうが10円多い", () => {
  const h = hikaku(10000, 10, 210, 93, 520);
  assert.equal(h.kaitoriTejori, 8780);
  assert.equal(h.uriteSagaku, -10);
  assert.equal(h.gyakutenRitsu, "93.10");
});

test("計算例 例4・例5", () => {
  const h4 = hikaku(60000, 10, 2100, 93);
  assert.deepEqual([h4.furimaTejori, h4.kaitoriTejori, h4.uriteSagaku, h4.gyakutenRitsu], [51900, 55800, 3900, "86.50"]);
  const h5 = hikaku(3000, 10, 210, 93);
  assert.deepEqual([h5.furimaTejori, h5.kaitoriTejori, h5.uriteSagaku, h5.gyakutenRitsu], [2490, 2790, 300, "83.00"]);
});

test("小数の率でも1円ずれない（浮動小数点では 10000×87.9% が 8789 になる）", () => {
  assert.equal(kaitoriGaku(10000, "87.9"), 8790);
  assert.equal(kaitoriGaku(10000, 87.9), 8790);
  assert.equal(hikaku(10000, 10, 210, "87.9").uriteSagaku, 0);
  assert.equal(furimaTejori(9999, "3.3", 0), 9999 - 329);
  assert.equal(kaitoriTejori(1, 99.9), 0);
});

test("文字列の入力（画面からの値）も同じ結果", () => {
  assert.deepEqual(hikaku("10000", "10", "210", "93", "0", "0"), hikaku(10000, 10, 210, 93));
});

test("入力の誤りは RangeError", () => {
  for (const args of [[0, 10, 210, 93], [-1, 10, 210, 93], [10000.5, 10, 210, 93], [10000, 101, 210, 93], [10000, -1, 210, 93],
    [10000, 10, -1, 93], [10000, 10, 210, -1], [10000, 10, 210, "abc"], [10000, 10, 210, "1e2"], ["", 10, 210, 93],
    [10000, 10, 210, 93, -1], [10000, 10, 210, 93, 0, 1.5]]) {
    assert.throws(() => hikaku(...args), RangeError, JSON.stringify(args));
  }
});

test("tejori.py と突き合わせる（乱数 500 件）", (t) => {
  const kit = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "kaitori-kit");
  if (!existsSync(join(kit, "tejori.py"))) return t.skip("kaitori-kit/tejori.py が無い");
  let seed = 20261127;
  const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
  const cases = [];
  for (let i = 0; i < 500; i++) {
    const soba = 1 + rnd(i % 5 === 0 ? 300 : 200000);
    const d = () => (rnd(3) === 0 ? String(rnd(101)) : `${rnd(100)}.${rnd(10)}${rnd(4) === 0 ? rnd(10) : ""}`);
    cases.push([soba, d(), rnd(3) === 0 ? 0 : rnd(1200), d(), rnd(2) ? 0 : rnd(900), rnd(2) ? 0 : rnd(500)]);
  }
  const py = `
import json, sys
sys.path.insert(0, sys.argv[1])
from decimal import Decimal
import tejori
out = []
for s, t, fs, k, us, uf in json.load(sys.stdin):
    h = tejori.hikaku(s, Decimal(t), fs, Decimal(k), us, uf)
    out.append([h.furima_tejori, h.kaitori_gaku, h.kaitori_tejori, h.urite_sagaku, f"{h.gyakuten_ritsu:.2f}", f"{h.saitei_ritsu:.1f}"])
print(json.dumps(out))
`;
  const expected = JSON.parse(execFileSync("python3", ["-B", "-c", py, kit], { input: JSON.stringify(cases), encoding: "utf8" }));
  cases.forEach((c, i) => {
    const h = hikaku(...c);
    assert.deepEqual([h.furimaTejori, h.kaitoriGaku, h.kaitoriTejori, h.uriteSagaku, h.gyakutenRitsu, h.saiteiRitsu], expected[i], JSON.stringify(c));
  });
});
