"""main.py の Shorts 台本（Markdown）→ shorts/ の台本（JSON）の変換のテスト。"""

import json
import os
from pathlib import Path

import pytest

from shorts import from_pipeline as F
from shorts import script as S
from shorts.__main__ import main

# テストは config/settings.yaml の中身に依存させない
SETTINGS = {"reviewer": {"display": "監修: toto先生（小児科医）"}}
HEADER = "| 枚数 | 表示秒数 | タイトル | 本文 | ナレーション | 引用元ID |\n|---|---|---|---|---|---|\n"

# python main.py --demo が output/scripts/乳児の便秘_<日付>_shorts.md に書く内容と同じ形
DEMO = """# 乳児の便秘 Shorts台本

フック（1秒）：「うんち数日出てない赤ちゃん、大丈夫?」

| 枚数 | 表示秒数 | タイトル | 本文 | ナレーション | 引用元ID |
|---|---|---|---|---|---|
| 1 | 3秒 | 数日出ない？ | 元気ならOKなことも | 数日出なくても元気なら大丈夫なことも | C01 |
| 2 | 5秒 | でも注意 | 血便・嘔吐・ぐったりは受診 | こんなサインはすぐ受診 | C03 |
| 3 | 5秒 | おうちケア | 水分・マッサージ | お腹を「の」の字マッサージ | C04 |
| 4 | 4秒 | まとめ | 迷ったら小児科へ | 監修: toto先生（小児科医） | - |

最終スライド：一般的情報提供です。診断・治療は医療機関へ。
"""
DEMO_TEXTS = [
    "うんち数日出てない赤ちゃん、大丈夫?",
    "数日出ない？", "元気ならOKなことも", "数日出なくても元気なら大丈夫なことも",
    "でも注意", "血便・嘔吐・ぐったりは受診", "こんなサインはすぐ受診",
    "おうちケア", "水分・マッサージ", "お腹を「の」の字マッサージ",
    "まとめ", "迷ったら小児科へ", "監修: toto先生（小児科医）",
    "一般的情報提供です。", "診断・治療は医療機関へ。",
]


def table(*rows):
    return "# テスト Shorts台本\n\n" + HEADER + "".join(
        f"| {i} | 5秒 | {t} | {b} | {n} | - |\n" for i, (t, b, n) in enumerate(rows, 1))


def all_text(data):
    out = data["supervisor"] + data["disclaimer"]
    for sc in data["scenes"]:
        out += sc["heading"] + "".join(sc["lines"]) + sc.get("narration", "")
    return F.norm(out)


def test_demo_fixture_matches_what_main_py_writes():
    demo_content = pytest.importorskip("src.demo_content")
    assert DEMO == demo_content.DEMO_SHORTS_SCRIPT


def test_demo_converts_and_passes_check(tmp_path, capsys):
    data = F.convert(DEMO, SETTINGS)
    sc = S.build_script(data, SETTINGS)  # shorts check と同じ検査
    assert not sc.warnings and data["notes"] == []
    assert sc.total_seconds <= S.MAX_TOTAL_SECONDS
    assert [s["kind"] for s in data["scenes"]] == ["hook", "point", "warning", "point", "cta"]
    assert [s.kind for s in sc.scenes][-1] == "disclaimer"
    assert data["title"] == "乳児の便秘"
    assert data["supervisor"] == "監修: toto先生（小児科医）"
    assert data["disclaimer"] == "一般的情報提供です。診断・治療は医療機関へ。"
    assert "seconds" not in data["scenes"][1]  # 秒数は文字数から決める
    assert data["scenes"][2]["source"] == {"where": "表の2枚目", "seconds": "5秒", "ref": "C03"}

    # コマンド: from-pipeline → check
    src = tmp_path / "乳児の便秘_20260101_shorts.md"
    src.write_text(DEMO, encoding="utf-8")
    out = tmp_path / "x" / "台本.json"
    assert main(["from-pipeline", str(src), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["scenes"][0]["heading"] == "うんち数日出てない赤ちゃん、大丈夫?"
    assert main(["check", str(out)]) == 0
    assert "OK" in capsys.readouterr().out


def test_no_sentence_is_dropped_or_reworded():
    data = F.convert(DEMO, SETTINGS)
    text = all_text(data)
    for sentence in DEMO_TEXTS:
        assert F.norm(sentence) in text, sentence
    # 足してもいない: 画面に出る文字は、元の台本にある文字だけ
    source = F.norm(DEMO)
    for sc in data["scenes"]:
        for piece in [sc["heading"], *sc["lines"]]:
            assert F.norm(piece) in source, piece
    # ナレーションを画面に出さない場合も、JSON には残る
    notes = F.convert(DEMO, SETTINGS, narration="notes")
    assert notes["scenes"][2]["lines"] == ["血便・嘔吐・ぐったりは受診"]
    assert notes["scenes"][2]["narration"] == "こんなサインはすぐ受診"
    assert notes["scenes"][2]["kind"] == "warning"  # 種類の判定にはナレーションも使う
    assert not F.missing_sentences(DEMO_TEXTS, notes)
    assert F.missing_sentences(["台本に無い文"], notes) == ["台本に無い文"]


def test_long_lines_split_at_punctuation_and_scenes_split_without_loss():
    long_body = ("赤ちゃんの排便の回数には大きな個人差があり、数日に1回でも、機嫌がよくて哺乳の量や体重の増え方が順調であれば、"
                 "心配のないことが多いとされています。回数だけでなく、便のかたさや赤ちゃんの様子を合わせてみることが大切です。")
    md = table(("はじめに", "短い本文", ""), ("便秘とは", long_body, ""), ("おわり", "相談を", ""))
    data = F.convert(md, SETTINGS)
    sc = S.build_script(data, SETTINGS)
    assert not sc.warnings  # どのシーンも 8 秒以内で読める量
    parts = [s for s in data["scenes"] if s["heading"] == "便秘とは"]
    assert len(parts) > 1 and all(s["kind"] == "point" for s in parts)
    lines = [x for s in parts for x in s["lines"]]
    assert "".join(lines) == long_body  # 分けただけで、つなぐと元の文に戻る
    assert all(x[-1] in "、。" for x in lines)  # 切れ目は句読点
    assert all(S.text_width(x) <= F.LINE_MAX_EM for x in lines)
    assert any("シーンに分けました" in n for n in data["notes"])


def test_split_helpers():
    assert F.split_sentences("水分をとる。お腹をさする！<br>様子を見る") == ["水分をとる。", "お腹をさする！", "様子を見る"]
    assert F.split_sentences("食事の変化（注: 水分量が変わること。）がきっかけ") == ["食事の変化（注: 水分量が変わること。）がきっかけ"]
    assert F.split_long_line("短い行、そのまま") == ["短い行、そのまま"]
    line = "あ" * 20 + "、" + "い" * 20
    assert F.split_long_line(line) == ["あ" * 20 + "、", "い" * 20]
    assert F.split_long_line("あ" * 50) == ["あ" * 50]  # 読点が無ければ分けない


def test_kind_detection():
    assert "すぐ受診" in F.WARNING_WORDS and "緊急" in F.WARNING_WORDS and "受診の目安" in F.WARNING_WORDS
    for word in F.WARNING_WORDS + F.EMERGENCY_SYMPTOM_WORDS:
        assert F.classify("見出し", [f"これは{word}です"], 1, 4) == "warning", word
    # warning は位置やラベルより優先
    assert F.classify("すぐ受診を", [], 0, 4) == "warning"
    assert F.classify("まとめ", ["けいれんは救急車"], 3, 4, hint="cta") == "warning"
    # 手がかりが無ければ位置で決める
    assert [F.classify("見出し", ["本文"], i, 4) for i in range(4)] == ["hook", "point", "point", "cta"]
    assert F.classify("見出し", ["本文"], 0, 1) == "hook"
    # まとめ・チャンネル登録は cta
    assert F.classify("まとめ", ["本文"], 1, 4) == "cta"
    assert F.classify("見出し", ["チャンネル登録をお願いします"], 1, 4) == "cta"
    assert F.classify("見出し", ["まとめて飲ませない"], 1, 4) == "point"

    md = table(("熱が出たら", "まず様子を見る", ""), ("受診の目安", "生後3か月未満の発熱", ""),
               ("家でのケア", "水分をこまめに", "けいれんしたら救急車"), ("さいごに", "迷ったら相談", ""))
    assert [s["kind"] for s in F.convert(md, SETTINGS)["scenes"]] == ["hook", "warning", "warning", "cta"]


def test_too_long_script_is_an_error_that_says_where():
    filler = "これは長さを確かめるためだけの本文で、医学的な内容はありません。"
    md = table(*[(f"見出し{i}", filler * 2, "ここだけナレーションもある行です。" if i == 3 else "") for i in range(1, 8)])
    with pytest.raises(F.ConvertError) as e:
        F.convert(md, SETTINGS)
    msg = str(e.value)
    assert "60 秒" in msg and "超えています" in msg and "文は削っていません" in msg
    assert "表の3枚目「見出し3」" in msg and "--narration notes" in msg
    assert msg.index("表の3枚目") < msg.index("表の1枚目")  # 長い順に並ぶ
    assert isinstance(e.value, S.ScriptError)  # コマンドでは「エラー: …」として表示される


def test_unsplittable_or_unreadable_input_is_an_error():
    with pytest.raises(F.ConvertError, match="表の1枚目.*見出しが長すぎます"):
        F.convert(table(("あ" * 60, "本文", "")), SETTINGS)
    with pytest.raises(F.ConvertError, match="表の1枚目.*画面に収まりません"):
        F.convert(table(("見出し", "あ" * 700, "")), SETTINGS)
    with pytest.raises(F.ConvertError, match="読めるシーンがありません"):
        F.convert("# テスト Shorts台本\n\n本文だけで表が無い\n", SETTINGS)


def test_long_sentence_without_punctuation_gets_enough_seconds():
    data = F.convert(table(("見出し", "あ" * 50, "")), SETTINGS)
    scene = data["scenes"][0]
    assert scene["lines"] == ["あ" * 50]
    assert scene["seconds"] >= S.BASE_SECONDS + 53 / S.CHARS_PER_SECOND
    assert not S.build_script(data, SETTINGS).warnings


def test_supervisor_and_disclaimer_are_inherited():
    md = table(("見出し", "本文", "監修: 別の先生"))
    data = F.convert(md, SETTINGS)
    assert data["supervisor"] == "監修: toto先生（小児科医）"  # 設定が優先
    assert any("監修表記" in n for n in data["notes"])
    assert data["disclaimer"] == S.DEFAULT_DISCLAIMER  # 台本に無ければ既定の文
    assert F.convert(md, {})["supervisor"] == "監修: 別の先生"  # 設定に無ければ台本から
    # 監修表記の文は画面の行にしない（左上に常に出るため）
    assert all("監修" not in x for s in data["scenes"] for x in s["lines"])
    # メモ書きの行は画面に出さず、notes に残す
    data = F.convert(md + "\n想定尺：50秒\n\nCTA：「次の動画もどうぞ」\n", SETTINGS)
    assert any("想定尺：50秒" in n for n in data["notes"])
    assert data["scenes"][-1] == {"kind": "cta", "heading": "次の動画もどうぞ", "lines": [], "source": {"where": "CTA"}}


def test_table_parsing_agrees_with_slide_builder():
    builder = pytest.importorskip("src.step4_slide_builder")
    slides = builder.parse_script_tables(DEMO, is_shorts=True)
    units = [u for u in F.parse_markdown(DEMO, SETTINGS["reviewer"]["display"]).units if u.where.startswith("表")]
    assert [u.heading for u in units] == [s.title for s in slides]
    assert [u.body for u in units] == [[s.body] for s in slides]
    assert [u.seconds for u in units] == [s.seconds for s in slides]


def test_find_latest_and_make_latest(tmp_path, capsys):
    scripts = tmp_path / "scripts"
    assert F.find_latest(scripts) is None
    assert main(["make-latest", "--scripts-dir", str(scripts), "--out", str(tmp_path / "out")]) == 1
    assert "Shorts の台本" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()

    scripts.mkdir()
    for i, name in enumerate(["a_20260101_shorts.md", "a_20260101_shorts_rev1.md", "a_20260101_youtube.md",
                              "b_20260102_shorts.md"]):
        p = scripts / name
        p.write_text(DEMO, encoding="utf-8")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
    assert F.find_latest(scripts).name == "b_20260102_shorts.md"
    os.utime(scripts / "a_20260101_shorts_rev1.md", (2_000_000, 2_000_000))
    assert F.find_latest(scripts).name == "a_20260101_shorts_rev1.md"
