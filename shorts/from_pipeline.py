"""main.py が作る Shorts 台本（Markdown）を、shorts/ の台本（JSON）に変換する。

main.py の流れ（src/step3_script_writer.py、--demo では src/demo_content.py）は、
Shorts の台本を `output/scripts/<テーマ>_<日付>_shorts.md` に次の形で出す:

    # 乳児の便秘 Shorts台本
    フック（1秒）：「うんち数日出てない赤ちゃん、大丈夫?」
    | 枚数 | 表示秒数 | タイトル | 本文 | ナレーション | 引用元ID |
    |---|---|---|---|---|---|
    | 1 | 3秒 | 数日出ない？ | 元気ならOKなことも | 数日出なくても元気なら大丈夫なことも | C01 |
    最終スライド：一般的情報提供です。診断・治療は医療機関へ。

変換の決まり:

- 文言は変えない・足さない・削らない。行う操作は「句読点の位置で分ける」「シーンを分ける」だけ。
  変換のあと、元の台本の文がすべて出力にあることを確かめ、欠けていればエラーにする。
- フックの行は先頭のシーン、表の1行は1シーン（タイトル → 見出し、本文 → 本文の行）。
- 動画は無音なので、ナレーションも画面の行として出す（`narration="show"`）。
  `narration="notes"` にすると画面には出さず、JSON の `narration` に残すだけにする。
- 表示秒数は台本の値を使わず、文字数から決める（台本の秒数は音声で読む前提の値で、
  ナレーションも画面に出すと読み切れないため）。元の値は JSON の `source` に残す。
- 60 秒を超えるときは削らずにエラーにして、どこが長いかを示す（監修者が台本を直す）。
- 監修表記は config/settings.yaml の reviewer.display（無ければ台本の「監修: …」）。
  免責文は台本の最終スライドの文（無ければ既定の文）。

このモジュールの関数は、ファイルの読み書きをする `convert_file` / `find_latest` 以外は純粋関数。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import script as S
from .script import ScriptError

# ---- シーンの種類を決める語 -------------------------------------------------
# warning: 緊急・すぐ受診を表す語。見出し・本文・ナレーションのどこかにあれば warning にする。
WARNING_WORDS = (
    "緊急", "救急", "119", "至急",
    "すぐ受診", "すぐに受診", "すぐ病院", "すぐに病院", "すぐに医療機関", "すぐ医療機関",
    "ただちに", "直ちに", "速やかに受診", "速やかに医療機関", "夜間でも受診",
    "要受診", "受診の目安", "受診のサイン", "受診が必要", "危険なサイン", "危険サイン",
)
# warning: 緊急の症状を表す語（画面の色が変わるだけなので、広めに拾う）。
EMERGENCY_SYMPTOM_WORDS = (
    "けいれん", "痙攣", "ひきつけ", "意識がない", "意識がおかしい", "呼吸が苦しい", "息が苦しい",
    "呼吸困難", "顔色が悪い", "唇が紫", "ぐったり", "血便",
)
# cta: 見出しにあれば cta にする語
CTA_HEADING_WORDS = ("まとめ", "おわりに", "最後に")
# cta: どこかにあれば cta にする語
CTA_WORDS = ("チャンネル登録", "フォロー", "高評価", "次の動画")
# 表の外の「ラベル：文」の行のラベル
HOOK_LABELS = ("フック", "冒頭", "つかみ", "オープニング")
CTA_LABELS = ("CTA", "cta", "締め", "エンディング")
END_LABELS = ("最終スライド", "エンドカード", "免責", "注意書き")
SUPERVISOR_LABELS = ("監修",)
# 免責文らしさを見る語
DISCLAIMER_WORDS = ("情報提供", "免責", "診断・治療")

# ---- 行を分ける目安 ---------------------------------------------------------
LINE_MAX_EM = 30.0  # 1行がこれ（全角30文字ぶん）より長ければ、読点の位置で分ける
NARRATION_MODES = ("show", "notes")

_COLUMNS = {
    "number": ("枚数", "No", "番号"),
    "seconds": ("表示秒数", "秒数"),
    "title": ("タイトル", "見出し"),
    "body": ("本文", "テロップ"),
    "narration": ("ナレーション",),
    "ref": ("引用元",),
}
_DEFAULT_ORDER = ("number", "seconds", "title", "body", "narration", "ref")
_OPEN, _CLOSE = "「『（(【〔［", "」』）)】〕］"


class ConvertError(ScriptError):
    """台本を変換できないときのエラー。メッセージはそのまま利用者に見せる。"""


@dataclass
class Unit:
    """元の台本の1まとまり（フックの行、表の1行、CTA の行など）。"""

    where: str  # 「フック」「表の2枚目」など。エラーの説明に使う
    heading: str
    body: list[str] = field(default_factory=list)
    narration: list[str] = field(default_factory=list)
    hint: str | None = None  # ラベルから決まる種類
    seconds: str = ""
    ref: str = ""


@dataclass
class Parsed:
    title: str
    units: list[Unit]
    disclaimer: str
    supervisor: str  # 台本に書かれていた監修表記（無ければ空）
    skipped: list[str]  # 画面に出さなかった行（メモ書きなど）
    texts: list[str]  # 取り込んだ元の文言（文が落ちていないことの確認に使う）


# ---- 文字列の道具 -----------------------------------------------------------
def norm(text: str) -> str:
    return re.sub(r"\s", "", text or "")


def _clean(cell: str) -> str:
    """表のセルや行から、書式の記号だけを取り除く（文言は変えない）。"""
    cell = re.sub(r"\[(?:ref:)?[CS]\d+\]", "", cell)  # 引用元IDの印
    cell = cell.replace("**", "").replace("__", "")
    return cell.strip()


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in "「『" and text[-1] in "」』" and not re.search(r"[」』].*[「『]", text[1:-1]):
        return text[1:-1].strip()
    return text


def _split_at(text: str, marks: str) -> list[str]:
    """かっこの外にある marks の直後で分ける。分けた結果をつなぐと元の文字列に戻る。"""
    out, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth = max(0, depth - 1)
        elif ch in marks and depth == 0:
            j = i + 1
            while j < len(text) and text[j] in marks + _CLOSE:
                j += 1
            out.append(text[start:j])
            start, i = j, j
            continue
        i += 1
    out.append(text[start:])
    return [p.strip() for p in out if p.strip()]


def split_sentences(text: str) -> list[str]:
    """改行・<br>・文末（。！？）で分ける。"""
    out: list[str] = []
    for part in re.split(r"<br\s*/?>|\n", text or ""):
        out += _split_at(_clean(part), "。！？!?")
    return out


def split_long_line(line: str, max_em: float = LINE_MAX_EM) -> list[str]:
    """max_em より長い行を、まん中に近い読点（、）の直後で分ける。読点が無ければそのまま。"""
    if S.text_width(line) <= max_em:
        return [line]
    parts = _split_at(line, "、，")
    if len(parts) < 2:
        return [line]
    half, best, acc = S.text_width(line) / 2, 1, 0.0
    best_gap = float("inf")
    for k in range(1, len(parts)):
        acc += S.text_width(parts[k - 1])
        if abs(acc - half) < best_gap:
            best, best_gap = k, abs(acc - half)
    left, right = "".join(parts[:best]), "".join(parts[best:])
    return split_long_line(left, max_em) + split_long_line(right, max_em)


def is_disclaimer_text(text: str) -> bool:
    return any(w in text for w in DISCLAIMER_WORDS)


# ---- 元の台本（Markdown）を読む ----------------------------------------------
def _is_supervisor(piece: str, displays: list[str]) -> bool:
    n = norm(piece).rstrip("。")
    return bool(n) and (n in [norm(d) for d in displays if d] or re.match(r"^監修[:：]", n) is not None)


def parse_markdown(text: str, supervisor_display: str = "", fallback_title: str = "") -> Parsed:
    """Shorts 台本の Markdown を、まとまり（Unit）の一覧にする。"""
    title, units, tail_units = "", [], []
    disclaimer, script_supervisor = "", ""
    skipped: list[str] = []
    texts: list[str] = []
    order: tuple[str, ...] | None = None
    seen_table = False

    def pieces(raw: str) -> list[str]:
        """文に分け、監修表記だけの文は取り除く（監修表記は画面の左上に常に出る）。"""
        nonlocal script_supervisor
        out = []
        for p in split_sentences(raw):
            if _is_supervisor(p, [supervisor_display]):
                script_supervisor = script_supervisor or p.rstrip("。")
            else:
                out.append(p)
        return out

    for raw in text.splitlines():
        line = raw.strip()
        if not line or re.fullmatch(r"[-=*_]{3,}", line):
            continue
        if line.startswith("#"):
            head = line.lstrip("#").strip()
            if not title:
                title = re.sub(r"\s*(YouTube\s*)?(Shorts|ショート)\s*(用)?\s*台本.*$", "", head, flags=re.I).strip() or head
            else:
                skipped.append(line)
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not re.search(r"\d", cells[0]) and any(n in "".join(cells) for names in _COLUMNS.values() for n in names):
                found = []
                for c in cells:  # 見出しの行から列の並びを読む
                    found.append(next((k for k, names in _COLUMNS.items() if any(n in c for n in names)), ""))
                order = tuple(found)
                continue
            cols = order
            if cols is None:  # 見出しの行が無いときは、src/step4_slide_builder.py と同じ並びとみなす
                cols = _DEFAULT_ORDER if len(cells) >= 6 else ("number", "title", "body", "narration", "ref")
            row = {k: c for k, c in zip(cols, cells) if k}
            number = re.sub(r"\D", "", row.get("number", "")) or str(len(units) + 1)
            where = f"表の{number}枚目"
            heading_parts = pieces(row.get("title", ""))
            body = pieces(row.get("body", ""))
            narration = pieces(row.get("narration", ""))
            texts += heading_parts + body + narration
            if not heading_parts and not body and not narration:
                continue
            seen_table = True
            unit = Unit(where, "", body, narration, None, row.get("seconds", ""), _clean(row.get("ref", "")))
            unit.heading = _clean(row.get("title", "")) if heading_parts else ""
            units.append(unit)
            continue

        plain = re.sub(r"^[>\-*・\s]+", "", line)
        m = re.match(r"^([^：:「|]{1,20}?)\s*(?:[（(][^）)]*[）)])?\s*[：:]\s*(.+)$", plain)
        label, content = (m.group(1).strip(), _unquote(m.group(2))) if m else ("", plain)
        if label.startswith(SUPERVISOR_LABELS):
            script_supervisor = script_supervisor or _clean(plain)
            texts.append(_clean(plain))
            continue
        ps = pieces(content)
        if label.startswith(HOOK_LABELS) or label.startswith(CTA_LABELS):
            texts += ps
            if ps:
                kind = "hook" if label.startswith(HOOK_LABELS) else "cta"
                unit = Unit(label, ps[0], ps[1:], [], kind)
                (units if kind == "hook" and not seen_table else tail_units).append(unit)
        elif label.startswith(END_LABELS) or (not label and is_disclaimer_text(content)):
            texts += ps
            if any(is_disclaimer_text(p) for p in ps):
                disclaimer += "".join(ps)  # 文言はそのまま（文の間に空白も足さない）
            elif ps:
                tail_units.append(Unit(label or "表のあとの行", ps[0], ps[1:], [], "cta"))
        else:
            skipped.append(line)

    return Parsed(title or fallback_title, units + tail_units, disclaimer, script_supervisor, skipped, texts)


# ---- シーンの種類 -----------------------------------------------------------
def classify(heading: str, texts: list[str], position: int, total: int, hint: str | None = None) -> str:
    """シーンの種類を決める。緊急・すぐ受診の語があれば、位置やラベルより優先して warning。"""
    everything = norm(heading + "".join(texts))
    if any(norm(w) in everything for w in WARNING_WORDS + EMERGENCY_SYMPTOM_WORDS):
        return "warning"
    if hint:
        return hint
    if any(w in heading for w in CTA_HEADING_WORDS) or any(w in everything for w in CTA_WORDS):
        return "cta"
    if position == 0:
        return "hook"
    if position == total - 1 and total > 1:
        return "cta"
    return "point"


# ---- シーンに収める ---------------------------------------------------------
def _fits(heading: str, lines: list[str], kind: str) -> bool:
    try:
        S.fit_scene(S.Scene(1, heading, lines, kind, 0, 0, True))
    except ScriptError:
        return False
    return True


def _need_seconds(heading: str, lines: list[str]) -> float:
    return S.BASE_SECONDS + (S.count_chars(heading) + sum(S.count_chars(x) for x in lines)) / S.CHARS_PER_SECOND


def _in_time(heading: str, lines: list[str]) -> bool:
    return _need_seconds(heading, lines) <= S.MAX_SCENE_SECONDS + 0.05


def _heading_fits(heading: str, kind: str) -> bool:
    width = S.HEAD_WIDTH_WARNING if kind == "warning" else S.HEAD_WIDTH
    return len(S.wrap(heading, width / S.HEAD_SIZES[-1])) <= S.HEAD_MAX_ROWS


def pack_unit(unit: Unit, kind: str, narration: str = "show") -> list[dict]:
    """1つのまとまりを、画面に収まり 8 秒以内で読める 1 つ以上のシーンにする。文は落とさない。"""
    heading, lines = unit.heading, list(unit.body)
    if not heading:  # タイトルの列が空の行は、本文の先頭を見出しにする
        if not lines and narration == "show":
            lines = list(unit.narration)
        if not lines:
            return []
        heading, lines = lines[0], lines[1:]
    if not _heading_fits(heading, kind):
        parts = [q for p in split_sentences(heading) for q in _split_at(p, "、，")]
        if len(parts) < 2 or not _heading_fits(parts[0], kind):
            raise ConvertError(
                f"{unit.where}: 見出しが長すぎます（{S.count_chars(heading)}文字: 「{heading[:20]}…」）。"
                "句読点で分けても画面に収まりません。台本のタイトルを短くしてください。"
            )
        heading, lines = parts[0], ["".join(parts[1:])] + lines
    if narration == "show" and unit.heading:
        shown = norm(heading + "".join(lines))
        lines += [p for p in unit.narration if norm(p) not in shown]  # 同じ文を二度は出さない

    atoms: list[str] = []
    for line in lines:
        for piece in split_long_line(line):
            if not (_fits(heading, [piece], kind) and _in_time(heading, [piece])):
                piece_parts = split_long_line(piece, 0.0)  # 読点のあるところすべてで分ける
            else:
                piece_parts = [piece]
            atoms += piece_parts

    groups: list[list[str]] = []
    for atom in atoms:
        if not _fits(heading, [atom], kind):
            raise ConvertError(
                f"{unit.where}（{heading[:12]}）: 1つの文が長すぎて画面に収まりません"
                f"（{S.count_chars(atom)}文字: 「{atom[:20]}…」）。句読点で分けられないため、台本の文を短くしてください。"
            )
        if groups and _fits(heading, groups[-1] + [atom], kind) and _in_time(heading, groups[-1] + [atom]):
            groups[-1].append(atom)
        else:
            groups.append([atom])
    groups = groups or [[]]

    scenes = []
    for n, group in enumerate(groups):
        k = kind
        if len(groups) > 1 and kind == "hook" and n > 0:
            k = "point"
        if len(groups) > 1 and kind == "cta" and n < len(groups) - 1:
            k = "point"
        scene: dict = {"kind": k, "heading": heading, "lines": group}
        if not _in_time(heading, group):  # 分けられない長い文は、読み切れる秒数を指定する
            scene["seconds"] = math.ceil(_need_seconds(heading, group) * 10) / 10
        source = {"where": unit.where}
        if unit.seconds:
            source["seconds"] = unit.seconds
        if unit.ref and unit.ref != "-":
            source["ref"] = unit.ref
        scene["source"] = source
        if narration == "notes" and unit.narration and n == 0:
            scene["narration"] = " ".join(unit.narration)
        scenes.append(scene)
    return scenes


def _scene_seconds(scene: dict) -> float:
    if "seconds" in scene:
        return float(scene["seconds"])
    return S.auto_seconds(S.count_chars(scene["heading"]) + sum(S.count_chars(x) for x in scene["lines"]))


def missing_sentences(texts: list[str], data: dict) -> list[str]:
    """元の文言のうち、出力（見出し・本文・ナレーション・監修表記・免責文）のどこにも無いもの。"""
    scenes = data.get("scenes", [])
    haystacks = [
        norm(data.get("supervisor", "")),
        norm(data.get("disclaimer", "")),
        "".join(norm(sc.get("heading", "") + "".join(sc.get("lines", []))) for sc in scenes),
        # 1つの文が複数のシーンにまたがるとき、あいだに見出しが入るので、本文だけをつないだものも見る
        "".join(norm("".join(sc.get("lines", []))) for sc in scenes),
        "".join(norm(sc.get("narration", "")) for sc in scenes),
    ]

    def found(t: str) -> bool:
        return any(t in h or t.rstrip("。") in h for h in haystacks)

    return [t for t in texts if norm(t) and not found(norm(t))]


# ---- 変換 -------------------------------------------------------------------
def convert(markdown_text: str, settings: dict | None = None, narration: str = "show",
            source_name: str = "") -> dict:
    """Shorts 台本の Markdown を shorts/ の台本（dict）にする。問題があれば ConvertError。"""
    if narration not in NARRATION_MODES:
        raise ConvertError(f"narration は {' / '.join(NARRATION_MODES)} のどちらかです: {narration!r}")
    settings = S.load_settings() if settings is None else settings
    reviewer = settings.get("reviewer") if isinstance(settings.get("reviewer"), dict) else {}
    display = reviewer.get("display") if isinstance(reviewer.get("display"), str) else ""

    stem = re.sub(r"_\d{8}_shorts(_rev\d+)?$", "", Path(source_name).stem) if source_name else ""
    parsed = parse_markdown(markdown_text, display, fallback_title=stem)
    if not parsed.units:
        raise ConvertError(
            "Shorts の台本として読めるシーンがありません。"
            "「| 枚数 | 表示秒数 | タイトル | 本文 | ナレーション | 引用元ID |」の表があるか確かめてください。"
        )
    if not parsed.title:
        raise ConvertError("台本にタイトル（先頭の「# …」の行）がありません。")

    notes: list[str] = []
    supervisor = display or parsed.supervisor
    if display and parsed.supervisor and norm(parsed.supervisor) != norm(display):
        notes.append(f"台本の監修表記（{parsed.supervisor}）が設定（{display}）と違います。設定のほうを使いました。")

    scenes: list[dict] = []
    per_unit: list[tuple[Unit, list[dict]]] = []
    for i, unit in enumerate(parsed.units):
        kind = classify(unit.heading, unit.body + unit.narration, i, len(parsed.units), unit.hint)
        made = pack_unit(unit, kind, narration)
        if len(made) > 1:
            notes.append(f"{unit.where}（{unit.heading[:12]}）は長いので {len(made)} シーンに分けました。")
        per_unit.append((unit, made))
        scenes += made

    data: dict = {"title": parsed.title, "supervisor": supervisor, "hashtags": [], "scenes": scenes}
    disclaimer = parsed.disclaimer or S.DEFAULT_DISCLAIMER
    data["disclaimer"] = disclaimer
    if not parsed.disclaimer:
        notes.append("台本に免責文が無いので、既定の免責文を使いました。")

    # 60 秒に収まるか。収まらなければ、どこが長いかを示して止める（文は削らない）
    disc_sec = _scene_seconds({"heading": S.DISCLAIMER_HEADING, "lines": [disclaimer]})
    total = sum(round(_scene_seconds(s) * S.FPS) for s in scenes) / S.FPS + disc_sec
    if total > S.MAX_TOTAL_SECONDS + 1e-9:
        rows = []
        for unit, made in per_unit:
            sec = sum(_scene_seconds(s) for s in made)
            n_head = S.count_chars(unit.heading)
            n_body = sum(S.count_chars(x) for x in unit.body)
            n_narr = sum(S.count_chars(x) for x in unit.narration)
            rows.append((sec, f"  {unit.where}「{unit.heading[:14]}」: {sec:.1f}秒"
                              f"（見出し{n_head}文字・本文{n_body}文字・ナレーション{n_narr}文字、{len(made)}シーン）"))
        rows.sort(key=lambda r: -r[0])
        hint = ""
        if narration == "show" and any(u.narration for u, _ in per_unit):
            hint = "\nナレーションを画面に出さない場合は --narration notes を付けてください（JSON には残ります）。"
        raise ConvertError(
            f"合計 {total:.1f} 秒で、上限の {S.MAX_TOTAL_SECONDS:g} 秒を {total - S.MAX_TOTAL_SECONDS:.1f} 秒超えています"
            f"（免責文 {disc_sec:.1f} 秒を含む）。文は削っていません。台本を短くしてください。\n長い順:\n"
            + "\n".join(r[1] for r in rows) + hint
        )

    lost = missing_sentences(parsed.texts, data)
    if lost:  # ここに来たらこの変換の不具合。黙って動画にしない
        raise ConvertError("変換で落ちた文があります（変換を中止しました）: " + " / ".join(lost))

    script = S.build_script(data, settings)  # shorts check と同じ検査
    notes += script.warnings
    if parsed.skipped:
        notes.append("画面に出していない行（メモ書きとみなしました）: " + " / ".join(parsed.skipped))
    data["source"] = {"file": Path(source_name).name if source_name else "", "narration": narration}
    data["notes"] = notes
    return data


# ---- ファイルの読み書き -----------------------------------------------------
def convert_file(path: str | Path, out: str | Path | None = None, settings: dict | None = None,
                 narration: str = "show") -> dict:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ConvertError(f"台本を読めません: {path}（{e.strerror or e}）") from e
    data = convert(text, settings, narration, source_name=path.name)
    if out is not None:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def find_latest(scripts_dir: str | Path) -> Path | None:
    """scripts_dir にある Shorts 台本（*_shorts.md と改訂版 *_shorts_revN.md）のうち、いちばん新しいもの。"""
    d = Path(scripts_dir)
    files = [p for p in d.glob("*_shorts*.md") if re.search(r"_shorts(_rev\d+)?\.md$", p.name)] if d.is_dir() else []
    return max(files, key=lambda p: (p.stat().st_mtime, p.name)) if files else None
