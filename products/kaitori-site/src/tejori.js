// フリマで売った場合と、郵送買取に出した場合の「売り手の手取り」を比べる計算。
// 式と端数処理は products/kaitori-kit/tejori.py と同じ（販売手数料と買取額は1円未満切り捨て）。
// 率は 87.9 のような小数を誤差なく扱うため、文字列から分数にして BigInt で計算する
// （10000 * 87.9 / 100 を浮動小数点で計算すると 8789.99… になり、切り捨てで1円ずれる）。

function dec(value, name) {
  const s = String(value).trim();
  if (!/^\d+(\.\d*)?$/.test(s)) throw new RangeError(`${name}は0以上の数字で入力してください`);
  const [i, f = ""] = s.split(".");
  return { n: BigInt(i + f), d: 10n ** BigInt(f.length) };
}

function yen(value, name) {
  const n = typeof value === "number" ? value : Number(String(value).trim() === "" ? NaN : String(value).trim());
  if (!Number.isSafeInteger(n)) throw new RangeError(`${name}は整数（円）で入力してください`);
  if (n < 0) throw new RangeError(`${name}に負の値は指定できません`);
  return BigInt(n);
}

function soba_(value) {
  const s = yen(value, "相場価格");
  if (s <= 0n) throw new RangeError("相場価格は1円以上で入力してください");
  return s;
}

const floorPct = (soba, r) => (soba * r.n) / (100n * r.d);   // どちらも0以上なので BigInt の割り算＝切り捨て

function furima_(soba, tesuryoPct, furimaSoryo) {
  const r = dec(tesuryoPct, "手数料率");
  if (r.n > 100n * r.d) throw new RangeError("手数料率は100%以下で入力してください");
  return soba - floorPct(soba, r) - yen(furimaSoryo, "フリマの送料");
}

/** フリマで相場どおりに売れた場合の手取り = 相場 − 販売手数料（切り捨て） − 送料 */
export function furimaTejori(soba, tesuryoPct, furimaSoryo) {
  return Number(furima_(soba_(soba), tesuryoPct, furimaSoryo));
}

/** 買取額 = 相場 × 買取率（1円未満切り捨て） */
export function kaitoriGaku(soba, kaitoriritsuPct) {
  return Number(floorPct(soba_(soba), dec(kaitoriritsuPct, "買取率")));
}

/** 買取の手取り = 買取額 − 売り手が負担する送料 − 売り手が負担する振込手数料 */
export function kaitoriTejori(soba, kaitoriritsuPct, uriteSoryo = 0, uriteFurikomi = 0) {
  return Number(floorPct(soba_(soba), dec(kaitoriritsuPct, "買取率"))
    - yen(uriteSoryo, "買取で負担する送料") - yen(uriteFurikomi, "買取で負担する振込手数料"));
}

// num/den を小数 digits 桁の文字列にする。丸めは偶数丸め（Python の Decimal の書式と同じ）
function ratio(num, den, digits) {
  const neg = num < 0n, a = neg ? -num : num, scale = 10n ** BigInt(digits);
  let q = (a * scale) / den;
  const r2 = 2n * ((a * scale) % den);
  if (r2 > den || (r2 === den && q % 2n === 1n)) q += 1n;
  const s = q.toString().padStart(digits + 1, "0");
  return (neg ? "-" : "") + s.slice(0, s.length - digits) + "." + s.slice(s.length - digits);
}

const ceilDiv = (a, b) => (a >= 0n ? (a + b - 1n) / b : -((-a) / b));   // b > 0

/**
 * 売り手の視点の比較。金額は円（整数）、率は%。
 * gyakutenRitsu: 手取りが同じになる買取率（小数2桁の文字列。端数処理前の理論値）
 * saiteiRitsu:   買取の手取りがフリマ以上になる最小の買取率（0.1%刻みで切り上げた文字列）
 */
export function hikaku(soba, tesuryoPct, furimaSoryo, kaitoriritsuPct, uriteSoryo = 0, uriteFurikomi = 0) {
  const s = soba_(soba);
  const f = furima_(s, tesuryoPct, furimaSoryo);
  const us = yen(uriteSoryo, "買取で負担する送料"), uf = yen(uriteFurikomi, "買取で負担する振込手数料");
  const gaku = floorPct(s, dec(kaitoriritsuPct, "買取率"));
  const k = gaku - us - uf;
  const need = f + us + uf;                      // 買取額がこれと同じなら手取りが同じ
  const tenths = ceilDiv(need * 1000n, s);       // 0.1% 単位
  return {
    soba: Number(s),
    furimaTejori: Number(f),
    kaitoriGaku: Number(gaku),
    kaitoriTejori: Number(k),
    uriteSagaku: Number(k - f),
    gyakutenRitsu: ratio(need * 100n, s, 2),
    saiteiRitsu: ratio(tenths, 10n, 1),
  };
}
