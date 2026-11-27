"""台本の読み込み・検査・秒数計算・文字の割り付け（ブラウザを使わない部分）。

文字の割り付けは IPAGothic が等幅（全角=1em、半角=0.5em）であることを前提に、
Python 側で折り返し位置と文字サイズを決める。こうしておくと `check` でも
「はみ出すかどうか」を動画を作らずに判定でき、同じ台本からは必ず同じ画面になる。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "config" / "settings.yaml"

# ---- 動画の決まりごと -------------------------------------------------------
FPS = 30
WIDTH, HEIGHT = 1080, 1920
MAX_TOTAL_SECONDS = 60.0  # YouTube Shorts の上限（このツールでの上限）

# ---- 秒数の自動計算 ---------------------------------------------------------
# 画面の文字を黙読する速さの目安（1秒あたりの文字数）。仮の値で、根拠となる計測はしていない。
# 速すぎる・遅すぎると感じたらここを変えるか、台本の seconds で個別に指定する。
CHARS_PER_SECOND = 6.0
BASE_SECONDS = 1.0  # 文字が出そろうまでの動きの分
MIN_SCENE_SECONDS = 2.5
MAX_SCENE_SECONDS = 8.0
MIN_EXPLICIT_SECONDS = 1.0  # seconds を手で指定する場合の下限（動きが収まる長さ）

KINDS = ("hook", "point", "warning", "cta", "disclaimer")
DEFAULT_DISCLAIMER = "本コンテンツは一般的情報提供です。診断・治療は必ず医療機関にご相談ください。"
DISCLAIMER_HEADING = "ご注意"
TITLE_MAX_CHARS = 100  # YouTube のタイトル上限

DEFAULT_DESIGN = {
    "primary_color": "#4FB3D9",
    "secondary_color": "#F4F9FC",
    "accent_color": "#FF8A65",
}

# ---- 画面の割り付け（px）。render.py の CSS と同じ値を使う ---------------------
CARD_MAX_HEIGHT = 1270  # カードを置ける縦の範囲（上 230 〜 下 1500。下はアプリの表示と重なるので空ける）
HEAD_WIDTH = 900
HEAD_WIDTH_WARNING = 790  # warning は「！」の印の分だけ狭い
BODY_WIDTH = 860
HEAD_PAD_Y = 44
BODY_PAD_Y = 56
HEAD_LINE_HEIGHT = 1.3
BODY_LINE_HEIGHT = 1.45
BODY_GAP_EM = 0.6  # 台本の行と行のあいだ
HEAD_SIZES = (92, 80, 70, 60)
BODY_SIZES = (66, 60, 54, 48, 42)
DISCLAIMER_BODY_SIZES = (54, 48, 42)
HEAD_MAX_ROWS = 3
SUPERVISOR_WIDTH = 760
SUPERVISOR_SIZES = (38, 32, 28)

_NO_LINE_START = set("、。，．,.！？!?）)」』】〕］}〉》・：；:;ー〜~…‥々ゝゞぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ％%")
_NO_LINE_END = set("（(「『【〔［{〈《")


class ScriptError(ValueError):
    """台本に問題があるときのエラー。メッセージはそのまま利用者に見せる。"""


@dataclass
class Scene:
    index: int  # 1 始まり
    heading: str
    lines: list[str]
    kind: str
    seconds: float
    frames: int
    auto_seconds: bool
    # 割り付けの結果
    head_size: int = 0
    head_rows: list[str] = field(default_factory=list)
    body_size: int = 0
    body_rows: list[list[str]] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return count_chars(self.heading) + sum(count_chars(x) for x in self.lines)


@dataclass
class Script:
    title: str
    supervisor: str
    supervisor_size: int
    scenes: list[Scene]
    disclaimer: str
    hashtags: list[str]
    design: dict[str, str]
    warnings: list[str]

    @property
    def total_frames(self) -> int:
        return sum(s.frames for s in self.scenes)

    @property
    def total_seconds(self) -> float:
        return self.total_frames / FPS


# ---- 小さな道具 -------------------------------------------------------------
def count_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text or ""))


def slugify(text: str, max_len: int = 40) -> str:
    """タイトルをファイル名に使える文字列にする（src/utils/common.py の slugify と同じ方針）。

    日本語は残す。空白と、OS やアップロード先で問題になりやすい記号は `_` にまとめる。
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch.isspace())
    text = re.sub(r"[\\/:*?\"<>|\s#%&'`.,!、。！？「」『』（）()\[\]{}]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    text = text[:max_len].strip("_")
    return text or "shorts"


def auto_seconds(chars: int) -> float:
    """文字数から表示秒数を決める（0.1 秒きざみ、最短 2.5 秒・最長 8 秒）。"""
    sec = BASE_SECONDS + chars / CHARS_PER_SECOND
    return round(min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, sec)), 1)


def char_width(ch: str) -> float:
    """IPAGothic での文字幅（em）。全角 1、半角 0.5。"""
    return 1.0 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 0.5


def text_width(text: str) -> float:
    return sum(char_width(c) for c in text)


def _tokens(text: str) -> list[str]:
    """折り返してよい単位に分ける。英数字のかたまりは割らず、行頭・行末の禁則を守る。"""
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9.,%+\-/]*|\s+|.", text)
    out: list[str] = []
    glue_next = False
    for tok in raw:
        if out and (glue_next or tok[0] in _NO_LINE_START):
            out[-1] += tok
        else:
            out.append(tok)
        glue_next = tok[-1] in _NO_LINE_END
    return out


def _char_class(ch: str) -> str:
    if "\u3041" <= ch <= "\u3096":
        return "hira"
    if "\u30a1" <= ch <= "\u30fa" or ch == "ー":
        return "kata"
    if "\u4e00" <= ch <= "\u9fff" or ch == "々":
        return "kanji"
    if ch.isascii() and ch.isalnum():
        return "ascii"
    return "other"


def _break_penalty(a: str, b: str) -> float:
    """a と b のあいだで折り返すときの「読みにくさ」。語の途中らしい場所ほど大きい。

    辞書は使わず、文字の種類の並びだけで見る目安（例: カタカナ語や熟語の途中は避ける）。
    """
    ca, cb = _char_class(a), _char_class(b)
    if ca == "other" or cb == "other":
        return 0.0
    if ca == cb:
        return {"kata": 0.6, "kanji": 0.35, "hira": 0.08}.get(ca, 0.6)
    if ca == "kanji" and cb == "hira":
        return 0.25  # 送りがなの手前
    if a in "おご" and cb == "kanji":
        return 0.3  # 「ご相談」「お子さん」など
    return 0.0 if ca == "hira" else 0.03


def wrap(text: str, max_em: float) -> list[str]:
    """幅 max_em（em 単位）に収まるよう折り返す。

    行数は最少にし、その中で「各行の長さがそろい、語の途中で切れにくい」切り方を選ぶ。
    """
    tokens: list[str] = []
    for tok in _tokens(text.strip()):
        while text_width(tok) > max_em:  # 1 単位が 1 行より長いときは文字で割る
            cut, w = 0, 0.0
            for ch in tok:
                if w + char_width(ch) > max_em:
                    break
                w += char_width(ch)
                cut += 1
            cut = max(cut, 1)
            tokens.append(tok[:cut])
            tok = tok[cut:]
        if tok:
            tokens.append(tok)
    n = len(tokens)
    if n == 0:
        return [""]
    # best[i] = (行数, 読みにくさ, 直前の切れ目) … 先頭から i 個の単位を並べ終えたとき
    best: list[tuple[int, float, int] | None] = [(0, 0.0, -1)] + [None] * n
    for i in range(1, n + 1):
        for j in range(i - 1, -1, -1):
            row = "".join(tokens[j:i]).strip()
            w = text_width(row)
            if w > max_em:
                break
            if best[j] is None:
                continue
            cost = best[j][1] + ((max_em - w) / max_em) ** 2
            if j > 0:
                cost += _break_penalty(tokens[j - 1][-1], tokens[j][0])
                if len(tokens[j]) > 1 and tokens[j][-1] in _NO_LINE_START and _char_class(tokens[j][0]) == "hira":
                    cost += 0.3  # 「…で/す。」のように、句読点の直前の1文字だけを次の行へ送らない
            if i < n:
                cost += 0.001 * w  # 同点なら、前の行が短いほうを選ぶ
            cand = (best[j][0] + 1, cost, j)
            if best[i] is None or cand[:2] < best[i][:2]:
                best[i] = cand
    rows, i = [], n
    while i > 0:
        j = best[i][2]
        rows.append("".join(tokens[j:i]).strip())
        i = j
    return [r for r in reversed(rows) if r] or [""]


def card_height(head_size: int, head_rows: int, body_size: int, body_rows: list[int]) -> float:
    h = head_rows * head_size * HEAD_LINE_HEIGHT + 2 * HEAD_PAD_Y
    if body_rows:
        h += 2 * BODY_PAD_Y + sum(body_rows) * body_size * BODY_LINE_HEIGHT
        h += (len(body_rows) - 1) * body_size * BODY_GAP_EM
    return h


def fit_scene(scene: Scene) -> None:
    """見出しと本文の文字サイズ・折り返しを決める。収まらなければ ScriptError。"""
    head_width = HEAD_WIDTH_WARNING if scene.kind == "warning" else HEAD_WIDTH
    head = None
    for size in HEAD_SIZES:
        rows = wrap(scene.heading, head_width / size)
        if len(rows) <= 2 or (size == HEAD_SIZES[-1] and len(rows) <= HEAD_MAX_ROWS):
            head = (size, rows)
            break
    label = f"シーン{scene.index}（{scene.heading[:12]}）"
    if head is None:
        raise ScriptError(
            f"{label}: 見出しが長すぎます（{count_chars(scene.heading)}文字）。"
            f"最小の文字サイズでも{HEAD_MAX_ROWS}行に収まりません。短くしてください。"
        )
    sizes = DISCLAIMER_BODY_SIZES if scene.kind == "disclaimer" else BODY_SIZES
    for size in sizes:
        body = [wrap(line, BODY_WIDTH / size) for line in scene.lines]
        if card_height(head[0], len(head[1]), size, [len(r) for r in body]) <= CARD_MAX_HEIGHT:
            scene.head_size, scene.head_rows = head
            scene.body_size, scene.body_rows = size, body
            return
    raise ScriptError(
        f"{label}: 本文が長すぎて画面に収まりません（{len(scene.lines)}行・{scene.chars}文字）。"
        "行を減らすか、シーンを分けてください。"
    )


# ---- 読み込み ---------------------------------------------------------------
def load_settings(path: Path | None = None) -> dict:
    path = path or SETTINGS_PATH
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def design_from_settings(settings: dict) -> dict[str, str]:
    design = dict(DEFAULT_DESIGN)
    src = settings.get("design") if isinstance(settings.get("design"), dict) else {}
    for key in design:
        value = src.get(key)
        if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value.strip()):
            design[key] = value.strip().upper()
    return design


def read_script_file(path: str | Path) -> dict:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ScriptError(f"台本を読めません: {path}（{e.strerror or e}）") from e
    try:
        data = yaml.safe_load(text) if path.suffix.lower() in (".yaml", ".yml") else json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise ScriptError(f"台本の書式が正しくありません: {path}（{e}）") from e
    if not isinstance(data, dict):
        raise ScriptError("台本は {\"title\": ..., \"scenes\": [...]} の形で書いてください。")
    return data


def _text(value, where: str, required: bool = True) -> str:
    if value is None or value == "":
        if required:
            raise ScriptError(f"{where} がありません。")
        return ""
    if not isinstance(value, str):
        raise ScriptError(f"{where} は文字列で書いてください。")
    value = re.sub(r"\s+", " ", value).strip()
    if required and not value:
        raise ScriptError(f"{where} が空です。")
    return value


def build_script(data: dict, settings: dict | None = None) -> Script:
    """台本（dict）を検査し、秒数と割り付けを決めた Script を返す。問題があれば ScriptError。"""
    settings = load_settings() if settings is None else settings
    warnings: list[str] = []

    title = _text(data.get("title"), "title（タイトル）")
    if len(title) > TITLE_MAX_CHARS:
        raise ScriptError(f"title が長すぎます（{len(title)}文字。YouTube の上限は{TITLE_MAX_CHARS}文字）。")

    supervisor = _text(data.get("supervisor"), "supervisor", required=False)
    if not supervisor:
        reviewer = settings.get("reviewer") if isinstance(settings.get("reviewer"), dict) else {}
        supervisor = _text(reviewer.get("display"), "supervisor", required=False)
    if not supervisor:
        raise ScriptError(
            "supervisor（監修表記）がありません。台本に書くか、config/settings.yaml の reviewer.display を設定してください。"
        )
    supervisor_size = next(
        (s for s in SUPERVISOR_SIZES if text_width(supervisor) * s <= SUPERVISOR_WIDTH), None
    )
    if supervisor_size is None:
        raise ScriptError(f"supervisor（監修表記）が長すぎます（{len(supervisor)}文字）。")

    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ScriptError("scenes（シーンの一覧）がありません。1つ以上書いてください。")

    disclaimer = _text(data.get("disclaimer"), "disclaimer", required=False) or DEFAULT_DISCLAIMER
    raw_scenes = list(raw_scenes)
    last = raw_scenes[-1]
    if not (isinstance(last, dict) and last.get("kind") == "disclaimer"):
        # 免責文のシーンは必ず最後に入れる
        raw_scenes.append({"heading": DISCLAIMER_HEADING, "lines": [disclaimer], "kind": "disclaimer"})

    scenes: list[Scene] = []
    for i, raw in enumerate(raw_scenes, 1):
        where = f"シーン{i}"
        if not isinstance(raw, dict):
            raise ScriptError(f"{where} は {{\"heading\": ..., \"lines\": [...]}} の形で書いてください。")
        heading = _text(raw.get("heading"), f"{where} の heading（見出し）")
        lines_raw = raw.get("lines", [])
        if isinstance(lines_raw, str):
            lines_raw = [lines_raw]
        if not isinstance(lines_raw, list):
            raise ScriptError(f"{where} の lines は文字列の一覧で書いてください。")
        lines = [_text(x, f"{where} の lines の{j}行目") for j, x in enumerate(lines_raw, 1)]
        kind = raw.get("kind", "point")
        if kind not in KINDS:
            raise ScriptError(f"{where} の kind が正しくありません: {kind!r}（{' / '.join(KINDS)} のどれか）。")
        chars = count_chars(heading) + sum(count_chars(x) for x in lines)
        sec_raw = raw.get("seconds")
        if sec_raw is None:
            seconds, is_auto = auto_seconds(chars), True
            if BASE_SECONDS + chars / CHARS_PER_SECOND > MAX_SCENE_SECONDS + 0.05:
                warnings.append(
                    f"{where}: {chars}文字あり、上限の{MAX_SCENE_SECONDS:g}秒では読み切れないおそれがあります。"
                    "シーンを分けることを検討してください。"
                )
        else:
            if isinstance(sec_raw, bool) or not isinstance(sec_raw, (int, float)):
                raise ScriptError(f"{where} の seconds は数値で書いてください。")
            seconds, is_auto = float(sec_raw), False
            if not (MIN_EXPLICIT_SECONDS <= seconds <= MAX_TOTAL_SECONDS):
                raise ScriptError(
                    f"{where} の seconds は {MIN_EXPLICIT_SECONDS:g}〜{MAX_TOTAL_SECONDS:g} の範囲で書いてください（{seconds:g}）。"
                )
            if chars / seconds > CHARS_PER_SECOND * 1.5:
                warnings.append(
                    f"{where}: {seconds:g}秒に{chars}文字は多めです（目安は1秒あたり{CHARS_PER_SECOND:g}文字）。"
                )
        frames = round(seconds * FPS)
        scene = Scene(i, heading, lines, kind, frames / FPS, frames, is_auto)
        for text in [heading, *lines]:
            bad = sorted({c for c in text if ord(c) > 0xFFFF})
            if bad:
                raise ScriptError(
                    f"{where}: フォントに無い文字（絵文字など）が含まれています: {' '.join(bad)}。取り除いてください。"
                )
        fit_scene(scene)
        scenes.append(scene)

    total = sum(s.frames for s in scenes) / FPS
    if total > MAX_TOTAL_SECONDS + 1e-9:
        detail = "、".join(f"{s.index}:{s.seconds:g}秒" for s in scenes)
        raise ScriptError(
            f"合計 {total:.1f} 秒で、上限の {MAX_TOTAL_SECONDS:g} 秒を超えています"
            f"（免責文のシーンを含む。{detail}）。シーンを減らすか seconds を短くしてください。"
        )

    tags_raw = data.get("hashtags", [])
    if isinstance(tags_raw, str):
        tags_raw = tags_raw.split()
    if not isinstance(tags_raw, list):
        raise ScriptError("hashtags は文字列の一覧で書いてください。")
    hashtags: list[str] = []
    for tag in ["Shorts", *tags_raw]:
        tag = "#" + re.sub(r"[\s#＃]+", "", str(tag))
        if len(tag) > 1 and tag.lower() not in [t.lower() for t in hashtags]:
            hashtags.append(tag)

    limits = settings.get("output") if isinstance(settings.get("output"), dict) else {}
    max_chars = limits.get("shorts_max_chars")
    all_chars = sum(s.chars for s in scenes if s.kind != "disclaimer")
    if isinstance(max_chars, int) and all_chars > max_chars:
        warnings.append(f"本文の合計が{all_chars}文字で、設定の目安（{max_chars}文字）を超えています。")

    return Script(title, supervisor, supervisor_size, scenes, disclaimer, hashtags,
                  design_from_settings(settings), warnings)


def load_script(path: str | Path, settings: dict | None = None) -> Script:
    return build_script(read_script_file(path), settings)


def summary(script: Script) -> str:
    rows = [f"タイトル: {script.title}", f"監修表記: {script.supervisor}"]
    for s in script.scenes:
        auto = "自動" if s.auto_seconds else "指定"
        rows.append(
            f"  {s.index:>2}. [{s.kind:<10}] {s.seconds:>4.1f}秒({auto}) {s.chars:>3}文字 "
            f"見出し{s.head_size}px 本文{s.body_size}px  {s.heading}"
        )
    rows.append(f"合計: {script.total_seconds:.1f}秒 / 上限 {MAX_TOTAL_SECONDS:g}秒（{len(script.scenes)}シーン）")
    rows += [f"注意: {w}" for w in script.warnings]
    return "\n".join(rows)
