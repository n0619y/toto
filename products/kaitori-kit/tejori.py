#!/usr/bin/env python3
"""フリマで売った場合と、郵送買取に出した場合の「手取り」を比べる計算。

外部ライブラリは使わない。金額はすべて円の整数、率は Decimal で扱う。
端数の扱い(このキットの「案」):
  - フリマの販売手数料 = 相場 × 手数料率 の 1円未満切り捨て
  - 買取額            = 相場 × 買取率   の 1円未満切り捨て
実際の端数処理はフリマサービスごとに異なるので、利用するサービスの表示で確認すること。

使い方の例:
  python3 tejori.py --soba 10000 --tesuryo 10 --furima-soryo 210 --kaitoriritsu 93
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal


def _d(value) -> Decimal:
    """float の誤差を持ち込まないよう、文字列経由で Decimal にする。"""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _check(soba: int, *rates_and_costs) -> None:
    if soba <= 0:
        raise ValueError("相場価格は1円以上で指定してください")
    for v in rates_and_costs:
        if v < 0:
            raise ValueError("率・送料・手数料に負の値は指定できません")


def _yen_floor(amount: Decimal) -> int:
    return int(amount.to_integral_value(rounding=ROUND_FLOOR))


def furima_tejori(soba: int, tesuryo_pct, furima_soryo: int) -> int:
    """フリマで相場価格どおりに売れた場合の売り手の手取り(円)。

    手取り = 相場 − 販売手数料(切り捨て) − 送料
    """
    tesuryo_pct = _d(tesuryo_pct)
    _check(soba, tesuryo_pct, furima_soryo)
    if tesuryo_pct > 100:
        raise ValueError("手数料率は100%以下で指定してください")
    tesuryo = _yen_floor(Decimal(soba) * tesuryo_pct / 100)
    return soba - tesuryo - furima_soryo


def kaitori_gaku(soba: int, kaitoriritsu_pct) -> int:
    """買取額(円) = 相場 × 買取率 の1円未満切り捨て。"""
    kaitoriritsu_pct = _d(kaitoriritsu_pct)
    _check(soba, kaitoriritsu_pct)
    return _yen_floor(Decimal(soba) * kaitoriritsu_pct / 100)


def kaitori_tejori(
    soba: int,
    kaitoriritsu_pct,
    urite_soryo: int = 0,
    urite_furikomi_tesuryo: int = 0,
) -> int:
    """郵送買取に出した場合の売り手の手取り(円)。

    手取り = 買取額 − 売り手が負担する送料 − 売り手が負担する振込手数料
    """
    _check(soba, urite_soryo, urite_furikomi_tesuryo)
    return kaitori_gaku(soba, kaitoriritsu_pct) - urite_soryo - urite_furikomi_tesuryo


def gyakuten_ritsu(
    soba: int,
    tesuryo_pct,
    furima_soryo: int,
    urite_soryo: int = 0,
    urite_furikomi_tesuryo: int = 0,
) -> Decimal:
    """売り手の手取りがフリマと同じになる買取率(%)。端数処理前の理論値。

    相場 × 率 − 売り手送料 − 売り手振込手数料 = フリマ手取り  を率について解く。
    これより高い買取率なら買取のほうが手取りが多い。
    """
    target = furima_tejori(soba, tesuryo_pct, furima_soryo)
    _check(soba, urite_soryo, urite_furikomi_tesuryo)
    return Decimal(target + urite_soryo + urite_furikomi_tesuryo) * 100 / Decimal(soba)


def saitei_ritsu(
    soba: int,
    tesuryo_pct,
    furima_soryo: int,
    urite_soryo: int = 0,
    urite_furikomi_tesuryo: int = 0,
    kizami=Decimal("0.1"),
) -> Decimal:
    """買取の手取りがフリマの手取り以上になる最小の買取率(%)。kizami 刻みで切り上げ。"""
    kizami = _d(kizami)
    exact = gyakuten_ritsu(soba, tesuryo_pct, furima_soryo, urite_soryo, urite_furikomi_tesuryo)
    return (exact / kizami).to_integral_value(rounding=ROUND_CEILING) * kizami


def shiire_cost(
    soba: int,
    kaitoriritsu_pct,
    unei_soryo: int = 0,
    unei_furikomi_tesuryo: int = 0,
) -> int:
    """運営者がこの買取で払う合計(円) = 買取額 + 運営者負担の送料 + 運営者負担の振込手数料。"""
    _check(soba, unei_soryo, unei_furikomi_tesuryo)
    return kaitori_gaku(soba, kaitoriritsu_pct) + unei_soryo + unei_furikomi_tesuryo


@dataclass(frozen=True)
class Hikaku:
    """比較結果。金額は円、率は%。"""

    soba: int
    furima_tejori: int          # 売り手: フリマで売った場合の手取り
    kaitori_gaku: int           # 買取額(相場 × 買取率)
    kaitori_tejori: int         # 売り手: 買取に出した場合の手取り
    urite_sagaku: int           # 売り手: 買取 − フリマ(プラスなら買取が多い)
    gyakuten_ritsu: Decimal     # 売り手の手取りが同じになる買取率
    saitei_ritsu: Decimal       # 買取の手取りがフリマ以上になる最小の買取率(0.1%刻み)
    furima_shiire: int          # 運営者: フリマで買う場合の支払い
    kaitori_shiire: int         # 運営者: 買取で仕入れる場合の支払い合計
    unei_sagaku: int            # 運営者: フリマ − 買取(プラスなら買取が安い)


def hikaku(
    soba: int,
    tesuryo_pct,
    furima_soryo: int,
    kaitoriritsu_pct,
    urite_soryo: int = 0,
    urite_furikomi_tesuryo: int = 0,
    unei_soryo: int = 0,
    unei_furikomi_tesuryo: int = 0,
    furima_konyu_soryo: int = 0,
) -> Hikaku:
    """売り手と運営者の両方の視点をまとめて計算する。

    furima_konyu_soryo: 運営者がフリマで買うときに別途払う送料。
        送料込みの出品が多いので初期値は 0。
    """
    _check(soba, furima_konyu_soryo)
    f = furima_tejori(soba, tesuryo_pct, furima_soryo)
    k = kaitori_tejori(soba, kaitoriritsu_pct, urite_soryo, urite_furikomi_tesuryo)
    fs = soba + furima_konyu_soryo
    ks = shiire_cost(soba, kaitoriritsu_pct, unei_soryo, unei_furikomi_tesuryo)
    return Hikaku(
        soba=soba,
        furima_tejori=f,
        kaitori_gaku=kaitori_gaku(soba, kaitoriritsu_pct),
        kaitori_tejori=k,
        urite_sagaku=k - f,
        gyakuten_ritsu=gyakuten_ritsu(
            soba, tesuryo_pct, furima_soryo, urite_soryo, urite_furikomi_tesuryo
        ),
        saitei_ritsu=saitei_ritsu(
            soba, tesuryo_pct, furima_soryo, urite_soryo, urite_furikomi_tesuryo
        ),
        furima_shiire=fs,
        kaitori_shiire=ks,
        unei_sagaku=fs - ks,
    )


def _yen(n: int) -> str:
    return f"{n:,}円"


def _signed(n: int) -> str:
    return f"{n:+,}円"


def format_table(h: Hikaku) -> str:
    """比較結果を Markdown の表にする。"""
    lines = [
        f"相場価格: {_yen(h.soba)}",
        "",
        "| 立場 | フリマ | この買取 | 差額 |",
        "|---|---:|---:|---:|",
        f"| 売り手の手取り | {_yen(h.furima_tejori)} | {_yen(h.kaitori_tejori)} "
        f"| {_signed(h.urite_sagaku)}(買取 − フリマ) |",
        f"| 運営者の支払い | {_yen(h.furima_shiire)} | {_yen(h.kaitori_shiire)} "
        f"| {_signed(h.unei_sagaku)}(フリマ − 買取) |",
        "",
        f"買取額(相場 × 買取率): {_yen(h.kaitori_gaku)}",
        f"売り手の手取りが同じになる買取率: {h.gyakuten_ritsu:.2f}%",
        f"買取の手取りがフリマ以上になる最小の買取率(0.1%刻み): {h.saitei_ritsu:.1f}%",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="フリマで売った場合と郵送買取の手取りを比べます(金額は円、率は%)。"
    )
    p.add_argument("--soba", type=int, required=True, help="相場価格(円)")
    p.add_argument("--tesuryo", type=Decimal, default=Decimal("10"),
                   help="フリマの販売手数料率(%%)。例の初期値 10")
    p.add_argument("--furima-soryo", type=int, default=210,
                   help="フリマで売り手が払う送料(円)。例の初期値 210")
    p.add_argument("--kaitoriritsu", type=Decimal, default=Decimal("93"),
                   help="買取率(%%)。例の初期値 93")
    p.add_argument("--urite-soryo", type=int, default=0,
                   help="買取で売り手が負担する送料(円)。初期値 0")
    p.add_argument("--urite-furikomi", type=int, default=0,
                   help="買取で売り手が負担する振込手数料(円)。初期値 0")
    p.add_argument("--unei-soryo", type=int, default=0,
                   help="買取で運営者が負担する送料(円)。初期値 0")
    p.add_argument("--unei-furikomi", type=int, default=0,
                   help="買取で運営者が負担する振込手数料(円)。初期値 0")
    p.add_argument("--furima-konyu-soryo", type=int, default=0,
                   help="運営者がフリマで買うとき別途払う送料(円)。初期値 0")
    a = p.parse_args(argv)
    try:
        h = hikaku(
            a.soba, a.tesuryo, a.furima_soryo, a.kaitoriritsu,
            a.urite_soryo, a.urite_furikomi, a.unei_soryo, a.unei_furikomi,
            a.furima_konyu_soryo,
        )
    except ValueError as e:
        p.error(str(e))
    print(format_table(h))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
