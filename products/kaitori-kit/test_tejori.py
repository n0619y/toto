"""tejori.py を手計算の値と突き合わせるテスト。

実行: python3 -m pytest products/kaitori-kit/test_tejori.py
期待値はすべて、コメントに書いた手計算の結果を直接書いている(関数で作り直していない)。
"""

from decimal import Decimal

import pytest

import tejori as t


# --- 基本の例: 相場 10,000円 / 手数料 10% / フリマ送料 210円 / 買取率 93% ---

def test_furima_tejori_kihon():
    # 10,000 − 1,000(10%) − 210 = 8,790
    assert t.furima_tejori(10000, 10, 210) == 8790


def test_kaitori_tejori_kihon():
    # 10,000 × 93% = 9,300。売り手負担なし
    assert t.kaitori_tejori(10000, 93) == 9300


def test_gyakuten_ritsu_kihon():
    # 8,790 ÷ 10,000 = 87.9%
    assert t.gyakuten_ritsu(10000, 10, 210) == Decimal("87.9")


def test_gyakuten_ritsu_de_tejori_ga_itchi():
    # 逆転する買取率で計算した買取の手取りは、フリマの手取りと同じ 8,790円
    assert t.kaitori_tejori(10000, Decimal("87.9")) == 8790


def test_hikaku_kihon():
    h = t.hikaku(10000, 10, 210, 93)
    assert h.furima_tejori == 8790
    assert h.kaitori_gaku == 9300
    assert h.kaitori_tejori == 9300
    assert h.urite_sagaku == 510          # 9,300 − 8,790
    assert h.gyakuten_ritsu == Decimal("87.9")
    assert h.saitei_ritsu == Decimal("87.9")
    assert h.furima_shiire == 10000
    assert h.kaitori_shiire == 9300
    assert h.unei_sagaku == 700           # 10,000 − 9,300


# --- 売り手が送料・振込手数料を負担する場合 ---

def test_urite_futan_ari():
    # 買取額 9,300 − 送料 520 − 振込手数料 150 = 8,630
    assert t.kaitori_tejori(10000, 93, 520, 150) == 8630
    # フリマ 8,790 のほうが 160円多い
    h = t.hikaku(10000, 10, 210, 93, urite_soryo=520, urite_furikomi_tesuryo=150)
    assert h.urite_sagaku == -160
    # (8,790 + 520 + 150) ÷ 10,000 = 94.6%
    assert h.gyakuten_ritsu == Decimal("94.6")


# --- 運営者が送料・振込手数料を負担する場合 ---

def test_unei_futan_ari():
    # 9,300 + 着払い送料 520 + 振込手数料 150 = 9,970 → フリマより 30円安い
    h = t.hikaku(10000, 10, 210, 93, unei_soryo=520, unei_furikomi_tesuryo=150)
    assert h.kaitori_shiire == 9970
    assert h.unei_sagaku == 30
    assert h.kaitori_tejori == 9300       # 売り手の手取りは変わらない


def test_furima_konyu_soryo():
    # フリマで送料別 300円の出品を買う場合: 10,000 + 300 = 10,300
    h = t.hikaku(10000, 10, 210, 93, furima_konyu_soryo=300)
    assert h.furima_shiire == 10300
    assert h.unei_sagaku == 1000


# --- まとめ売り(ロット)の例: 相場合計 60,000円、フリマでは10件に分けて出品 ---

def test_lot():
    # フリマ: 60,000 − 6,000 − 210×10 = 51,900
    assert t.furima_tejori(60000, 10, 2100) == 51900
    # 買取: 60,000 × 93% = 55,800
    h = t.hikaku(60000, 10, 2100, 93, unei_soryo=850, unei_furikomi_tesuryo=150)
    assert h.kaitori_tejori == 55800
    assert h.urite_sagaku == 3900
    # 51,900 ÷ 60,000 = 86.5%
    assert h.gyakuten_ritsu == Decimal("86.5")
    # 運営者: 55,800 + 850 + 150 = 56,800 → 60,000 との差 3,200
    assert h.kaitori_shiire == 56800
    assert h.unei_sagaku == 3200


# --- 端数 ---

def test_hasu_kirisute():
    # 手数料: 3,333 × 10% = 333.3 → 333。手取り 3,333 − 333 − 210 = 2,790
    assert t.furima_tejori(3333, 10, 210) == 2790
    # 買取額: 3,333 × 93% = 3,099.69 → 3,099
    assert t.kaitori_gaku(3333, 93) == 3099
    # 小数の率: 12,345 × 92.5% = 11,419.125 → 11,419
    assert t.kaitori_gaku(12345, 92.5) == 11419


def test_saitei_ritsu_kiriage():
    # 逆転率 = 2,790 ÷ 3,333 = 83.708...% → 0.1%刻みで切り上げて 83.8%
    assert t.saitei_ritsu(3333, 10, 210) == Decimal("83.8")
    # 83.8% なら買取額 2,793(≥ 2,790)、83.7% なら 2,789(< 2,790)
    assert t.kaitori_gaku(3333, Decimal("83.8")) == 2793
    assert t.kaitori_gaku(3333, Decimal("83.7")) == 2789


# --- 入力チェック ---

@pytest.mark.parametrize("args", [
    (0, 10, 210, 93),
    (-1, 10, 210, 93),
    (10000, -1, 210, 93),
    (10000, 101, 210, 93),
    (10000, 10, -1, 93),
    (10000, 10, 210, -5),
])
def test_fusei_na_nyuryoku(args):
    with pytest.raises(ValueError):
        t.hikaku(*args)


# --- コマンドライン ---

def test_cli(capsys):
    assert t.main(["--soba", "10000", "--tesuryo", "10",
                   "--furima-soryo", "210", "--kaitoriritsu", "93"]) == 0
    out = capsys.readouterr().out
    assert "8,790円" in out
    assert "9,300円" in out
    assert "+510円" in out
    assert "87.90%" in out
    assert "+700円" in out
