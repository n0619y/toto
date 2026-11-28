import json
import shutil
import subprocess
from pathlib import Path

import pytest

from shorts import render
from shorts import script as S
from shorts.__main__ import main
from shorts.script import ScriptError, build_script

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "shorts" / "sample" / "channel_intro.json"
# テストは config/settings.yaml の中身に依存させない
SETTINGS = {"reviewer": {"display": "監修: テスト"}, "design": {"primary_color": "#112233", "accent_color": "赤"}}


def base(**over):
    data = {
        "title": "テストの台本",
        "supervisor": "監修: テスト",
        "scenes": [{"heading": "見出し", "lines": ["本文の1行目", "本文の2行目"], "kind": "hook"}],
    }
    data.update(over)
    return data


def test_sample_script_is_valid():
    sc = S.load_script(SAMPLE)
    assert sc.total_seconds <= S.MAX_TOTAL_SECONDS
    assert sc.scenes[-1].kind == "disclaimer"
    assert not sc.warnings


def test_required_fields():
    for key in ("title", "scenes"):
        data = base()
        del data[key]
        with pytest.raises(ScriptError):
            build_script(data, SETTINGS)
    with pytest.raises(ScriptError, match="シーン1 の heading"):
        build_script(base(scenes=[{"lines": ["本文"]}]), SETTINGS)
    with pytest.raises(ScriptError, match="kind"):
        build_script(base(scenes=[{"heading": "見出し", "kind": "intro"}]), SETTINGS)
    with pytest.raises(ScriptError, match="supervisor"):
        build_script(base(supervisor=""), {})


def test_supervisor_and_design_fall_back_to_settings():
    data = base()
    del data["supervisor"]
    sc = build_script(data, SETTINGS)
    assert sc.supervisor == "監修: テスト"
    assert sc.design["primary_color"] == "#112233"
    assert sc.design["accent_color"] == S.DEFAULT_DESIGN["accent_color"]  # 色として読めない値は既定値


def test_auto_seconds_from_char_count():
    assert S.auto_seconds(0) == S.MIN_SCENE_SECONDS
    assert S.auto_seconds(1000) == S.MAX_SCENE_SECONDS
    assert S.auto_seconds(24) == pytest.approx(S.BASE_SECONDS + 24 / S.CHARS_PER_SECOND)
    sc = build_script(base(), SETTINGS)
    first = sc.scenes[0]
    assert first.auto_seconds and first.seconds == S.auto_seconds(first.chars)
    assert first.frames == round(first.seconds * S.FPS)


def test_explicit_seconds_are_used():
    sc = build_script(base(scenes=[{"heading": "見出し", "lines": ["本文"], "seconds": 4}]), SETTINGS)
    assert sc.scenes[0].seconds == 4 and not sc.scenes[0].auto_seconds
    with pytest.raises(ScriptError, match="seconds"):
        build_script(base(scenes=[{"heading": "見出し", "seconds": 0.2}]), SETTINGS)
    with pytest.raises(ScriptError, match="seconds"):
        build_script(base(scenes=[{"heading": "見出し", "seconds": "5"}]), SETTINGS)


def test_disclaimer_scene_is_always_last():
    sc = build_script(base(), SETTINGS)
    assert [s.kind for s in sc.scenes] == ["hook", "disclaimer"]
    assert sc.scenes[-1].lines == [S.DEFAULT_DISCLAIMER]
    sc = build_script(base(disclaimer="これは確認用の文です。"), SETTINGS)
    assert sc.scenes[-1].lines == ["これは確認用の文です。"]
    own = base()
    own["scenes"].append({"heading": "ご注意", "lines": ["自分で書いた免責文"], "kind": "disclaimer"})
    assert len(build_script(own, SETTINGS).scenes) == 2  # 二重には入れない


def test_over_60_seconds_is_an_error():
    scenes = [{"heading": f"見出し{i}", "lines": ["本文"], "seconds": 8} for i in range(7)]
    ok = build_script(base(scenes=scenes + [{"heading": "注意", "kind": "disclaimer", "seconds": 4}]), SETTINGS)
    assert ok.total_seconds == 60
    with pytest.raises(ScriptError, match="上限の 60 秒を超えています"):
        build_script(base(scenes=scenes), SETTINGS)  # 56 秒 + 自動で入る免責文のシーン


def test_too_long_text_is_an_error_naming_the_scene():
    scenes = [
        {"heading": "短い見出し", "lines": ["短い本文"]},
        {"heading": "長いシーン", "lines": ["とても長い本文です。" * 12] * 4},
    ]
    with pytest.raises(ScriptError, match="シーン2（長いシーン）.*本文が長すぎ"):
        build_script(base(scenes=scenes), SETTINGS)
    with pytest.raises(ScriptError, match="シーン1.*見出しが長すぎ"):
        build_script(base(scenes=[{"heading": "長い見出し" * 12, "lines": []}]), SETTINGS)
    with pytest.raises(ScriptError, match="絵文字"):
        build_script(base(scenes=[{"heading": "見出し😀", "lines": []}]), SETTINGS)


def test_long_lines_wrap_and_shrink_within_the_card():
    line = "長めの行は自動で折り返し、収まらなければ文字を小さくします。"
    sc = build_script(base(scenes=[{"heading": "見出し", "lines": [line] * 6}]), SETTINGS)
    s = sc.scenes[0]
    assert s.body_size < S.BODY_SIZES[0]
    for rows, src in zip(s.body_rows, s.lines):
        assert "".join(rows) == src
        assert all(S.text_width(r) * s.body_size <= S.BODY_WIDTH for r in rows)
    assert S.card_height(s.head_size, len(s.head_rows), s.body_size,
                         [len(r) for r in s.body_rows]) <= S.CARD_MAX_HEIGHT


def test_wrap_rules():
    assert S.wrap("短い", 10) == ["短い"]
    assert S.wrap("このチャンネルは何を届ける？", 9.5) == ["このチャンネルは", "何を届ける？"]
    for row in S.wrap("読点、句点。は行の先頭に置かない、という決まりです。", 6):
        assert row[0] not in "、。" and S.text_width(row) <= 6
    assert "100%" in S.wrap("割合はおよそ100%と書く", 8)[-1]  # 数字と単位は割らない
    assert S.text_width("abcあい") == 3.5


def test_slugify():
    assert S.slugify("このチャンネルで扱うこと") == "このチャンネルで扱うこと"
    assert S.slugify("  発熱 / 受診の目安?  ") == "発熱_受診の目安"
    assert S.slugify("ＡＢＣ　Shorts #1") == "abc_shorts_1"
    assert S.slugify("あ" * 80) == "あ" * 40
    assert S.slugify("???") == "shorts"


def test_hashtags_and_post_text_use_only_script_words():
    sc = build_script(base(hashtags=["子育て", "#shorts", "子育て"]), SETTINGS)
    assert sc.hashtags == ["#Shorts", "#子育て"]
    text = render.post_text(sc)
    assert "テストの台本" in text and "・見出し" in text
    assert "監修: テスト" in text and S.DEFAULT_DISCLAIMER in text and "#Shorts #子育て" in text


def test_still_frames_are_reused():
    sc = build_script(base(), SETTINGS)
    tl = render.timeline(sc)
    plan = render.frame_plan(tl, sc.total_frames)
    assert len(plan) == sc.total_frames and plan[0] == 0
    assert all(src <= f for f, src in enumerate(plan))
    assert len(set(plan)) < sc.total_frames / 2
    assert plan[-1] == plan[-2]  # 最後は動きが終わって止まっている


def test_check_command(tmp_path, capsys):
    assert main(["check", str(SAMPLE)]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(base(scenes=[])), encoding="utf-8")
    assert main(["check", str(bad)]) == 1
    assert "scenes" in capsys.readouterr().err


@pytest.mark.skipif(not (shutil.which("node") and shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="node / ffmpeg が必要")
def test_make_writes_a_vertical_mp4(tmp_path):
    src = tmp_path / "short.yaml"
    src.write_text(
        "title: 動作確認\nsupervisor: '監修: テスト'\nscenes:\n"
        "  - {heading: 確認用の動画, lines: [1行目, 2行目], seconds: 1.5, kind: warning}\n"
        "  - {heading: ご注意, lines: [これは確認用の文です。], seconds: 1, kind: disclaimer}\n",
        encoding="utf-8",
    )
    assert main(["make", str(src), "--out", str(tmp_path / "out"), "--date", "20260101"]) == 0
    mp4 = tmp_path / "out" / "20260101_動作確認.mp4"
    assert mp4.with_suffix(".png").stat().st_size > 0 and "動作確認" in mp4.with_suffix(".txt").read_text("utf-8")
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mp4)],
        capture_output=True, text=True, check=True).stdout)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (video["codec_name"], video["width"], video["height"]) == ("h264", 1080, 1920)
    assert video["pix_fmt"] == "yuv420p" and video["r_frame_rate"] == "30/1"
    assert audio["codec_name"] == "aac"
    assert float(probe["format"]["duration"]) == pytest.approx(2.5, abs=0.1)
