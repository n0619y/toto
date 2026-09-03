"""Roster → PDF 直接描画 (PyMuPDF). LibreOffice や Excel が無くても 2枚目 PDF と同じ表を出力する.

寸法は元 PDF から実測した値 (行高 13.25pt, コマ幅 23.35pt, 本文 6.2pt) を「設計単位」とし、
用紙幅に合わせて拡大縮小する。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pymupdf

from .model import (
    COLOR_FREE,
    COLOR_HOLIDAY,
    SLOT_TIMES,
    WEEKDAY_JA,
    Cell,
    Roster,
    build_cells,
)

# 日本語フォントの候補 (上から順に探す)
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]


@dataclass
class PdfStyle:
    page_width: float = 841.89  # A4 横
    page_height: float = 595.28
    margin: float = 28.0
    row_h: float = 13.25
    slot_w: float = 23.35
    label_w: float = 26.6
    font_size: float = 6.2
    wrap_font_size: float = 5.3
    note_font_size: float = 4.4
    title_font_size: float = 8.7
    thin: float = 0.3
    thick: float = 1.0
    font_file: str | None = None


def _load_font(style: PdfStyle) -> pymupdf.Font:
    candidates = ([style.font_file] if style.font_file else []) + [os.environ.get("DUTY_ROSTER_FONT", "")] + FONT_CANDIDATES
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return pymupdf.Font(fontfile=path)
            except Exception:  # noqa: BLE001
                continue
    return pymupdf.Font("japan")  # MuPDF 内蔵 CJK フォント


def _hex_to_rgb(hexv: str) -> tuple[float, float, float]:
    return tuple(int(hexv[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


class _Layout:
    def __init__(self, roster: Roster, style: PdfStyle):
        self.roster = roster
        self.st = style
        self.weeks = roster.weeks()
        nmem = len(roster.members)
        self.table_w = style.label_w + style.slot_w * 21
        # 行の並び: title, weekday, time, (day, members..., time)...
        self.rows: list[tuple[str, int | None, str | None]] = [("title", None, None), ("weekday", None, None), ("time", None, None)]
        for wi in range(len(self.weeks)):
            if wi > 0:
                self.rows.append(("time", None, None))
            self.rows.append(("day", wi, None))
            for m in roster.members:
                self.rows.append(("member", wi, m))
        self.table_h = style.row_h * len(self.rows)
        self.nmem = nmem
        avail_w = style.page_width - 2 * style.margin
        avail_h = style.page_height - 2 * style.margin
        self.scale = min(avail_w / self.table_w, avail_h / self.table_h)
        self.ox = (style.page_width - self.table_w * self.scale) / 2
        self.oy = (style.page_height - self.table_h * self.scale) / 2

    # 設計単位 → ページ座標
    def x(self, col: int) -> float:
        """col=0 はラベル列の左端, col=1.. はコマ列の左端 (col=22 が右端)."""
        w = 0.0 if col == 0 else self.st.label_w + self.st.slot_w * (col - 1)
        return self.ox + w * self.scale

    def y(self, row: int) -> float:
        return self.oy + self.st.row_h * row * self.scale

    def rect(self, row: int, col0: int, col1: int) -> pymupdf.Rect:
        return pymupdf.Rect(self.x(col0), self.y(row), self.x(col1 + 1), self.y(row + 1))

    def member_row(self, wi: int, member: str) -> int:
        return self.rows.index(("member", wi, member))


def render_pdf(roster: Roster, path: str, style: PdfStyle | None = None) -> str:
    st = style or PdfStyle()
    lay = _Layout(roster, st)
    font = _load_font(st)
    doc = pymupdf.open()
    page = doc.new_page(width=st.page_width, height=st.page_height)
    shape = page.new_shape()
    writer = pymupdf.TextWriter(page.rect)

    def fs(size: float) -> float:
        return size * lay.scale

    def fill_rect(r: pymupdf.Rect, hexv: str) -> None:
        if hexv.upper() == COLOR_FREE:
            return
        shape.draw_rect(r)
        shape.finish(color=None, fill=_hex_to_rgb(hexv))

    def text_in(r: pymupdf.Rect, lines: tuple[str, ...], size: float, sizes: tuple[float, ...] | None = None) -> None:
        """矩形の中央に (複数行の) 文字を描く. 収まらなければ 2 行に折り返し, さらに縮小する."""
        if not lines:
            return
        lines = tuple(ln for ln in lines if ln)
        line_sizes = list(sizes) if sizes else [size] * len(lines)
        inner = r.width - 2 * lay.scale
        # 1 行目が収まらないときは折り返す (元表の "Web/会議", "市立/秋田" の挙動)
        if len(lines) == 1 and font.text_length(lines[0], fontsize=fs(size)) > inner:
            s = st.wrap_font_size
            txt = lines[0]
            split = _wrap_point(txt, lambda t: font.text_length(t, fontsize=fs(s)), inner)
            if split:
                lines, line_sizes = (txt[:split], txt[split:]), [s, s]
            else:
                lines, line_sizes = (txt,), [s]
        # まだ収まらなければ縮小
        while max(font.text_length(ln, fontsize=fs(sz)) for ln, sz in zip(lines, line_sizes)) > inner and min(line_sizes) > 2.5:
            line_sizes = [sz * 0.92 for sz in line_sizes]
        heights = [fs(sz) * 1.15 for sz in line_sizes]
        total = sum(heights)
        y = r.y0 + (r.height - total) / 2
        for ln, sz, h in zip(lines, line_sizes, heights):
            w = font.text_length(ln, fontsize=fs(sz))
            baseline = y + h - fs(sz) * 0.25
            writer.append(pymupdf.Point(r.x0 + (r.width - w) / 2, baseline), ln, font=font, fontsize=fs(sz))
            y += h

    # ---- 背景・文字 ----------------------------------------------------------------------
    borders: list[tuple[pymupdf.Rect, bool]] = []  # (矩形, 太線か)
    for ri, (kind, wi, member) in enumerate(lay.rows):
        if kind == "title":
            text_in(lay.rect(ri, 1, 21), (roster.title or roster.default_title(),), st.title_font_size)
            continue
        if kind == "weekday":
            for di in range(7):
                text_in(lay.rect(ri, 1 + di * 3, 3 + di * 3), (WEEKDAY_JA[di],), st.font_size)
            continue
        if kind == "time":
            text_in(lay.rect(ri, 0, 0), ("時刻",), st.font_size)
            for k in range(21):
                text_in(lay.rect(ri, 1 + k, 1 + k), (SLOT_TIMES[k % 3],), st.font_size)
            continue
        if kind == "day":
            week = lay.weeks[wi]  # type: ignore[index]
            for di, day in enumerate(week):
                r = lay.rect(ri, 1 + di * 3, 3 + di * 3)
                holiday = (day is not None and roster.is_holiday(day)) or (day is None and di >= 5)
                fill_rect(r, COLOR_HOLIDAY if holiday else COLOR_FREE)
                if day is not None:
                    text_in(r, (str(day),), st.font_size)
            continue
        if kind == "member":
            text_in(lay.rect(ri, 0, 0), (member,), st.font_size)  # type: ignore[arg-type]

    cells: list[Cell] = build_cells(roster)
    for cell in cells:
        ri = lay.member_row(cell.week_index, cell.member)
        r = lay.rect(ri, 1 + cell.start, 1 + cell.end)
        fill_rect(r, cell.color)
        if cell.lines:
            sizes = (st.font_size,) + (st.note_font_size,) * (len(cell.lines) - 1)
            text_in(r, cell.lines, st.font_size, sizes)
        if cell.cross:
            shape.draw_line(pymupdf.Point(r.x0, r.y0), pymupdf.Point(r.x1, r.y1))
            shape.draw_line(pymupdf.Point(r.x0, r.y1), pymupdf.Point(r.x1, r.y0))
            shape.finish(color=(0, 0, 0), width=st.thick * lay.scale)

    # ---- 罫線 ----------------------------------------------------------------------------
    thin_w = st.thin * lay.scale
    thick_w = st.thick * lay.scale
    first_row = 1  # 曜日行から
    last_row = len(lay.rows) - 1
    # 細線: 全コマ (結合セル内は省く)
    merged: dict[int, list[tuple[int, int]]] = {}
    for cell in cells:
        ri = lay.member_row(cell.week_index, cell.member)
        merged.setdefault(ri, []).append((1 + cell.start, 1 + cell.end))
    for ri, (kind, wi, member) in enumerate(lay.rows):
        if kind == "title":
            continue
        # 横線 (行の下辺)
        shape.draw_line(pymupdf.Point(lay.x(0), lay.y(ri + 1)), pymupdf.Point(lay.x(22), lay.y(ri + 1)))
        # 縦線
        spans = merged.get(ri)
        if kind in ("weekday", "day"):
            cols = [0] + [1 + di * 3 for di in range(7)]
            if kind == "day":
                cols = list(range(0, 22))
                # 日付行はコマごとに細線あり (元表と同じ)
        elif spans:
            cols = [0, 1] + [c1 + 1 for _, c1 in spans]
        else:
            cols = list(range(0, 22))
        for c in cols:
            if c <= 21:
                shape.draw_line(pymupdf.Point(lay.x(c), lay.y(ri)), pymupdf.Point(lay.x(c), lay.y(ri + 1)))
    shape.finish(color=(0, 0, 0), width=thin_w)

    # 太線: 外枠, ラベル列右, 日付境界, 時刻行の上下
    thick_lines: list[tuple[pymupdf.Point, pymupdf.Point]] = []
    y_top, y_bot = lay.y(first_row), lay.y(last_row + 1)
    for c in [0, 1] + [1 + di * 3 for di in range(1, 7)] + [22]:
        thick_lines.append((pymupdf.Point(lay.x(c), y_top), pymupdf.Point(lay.x(c), y_bot)))
    for ri, (kind, _, _) in enumerate(lay.rows):
        if kind == "time":
            thick_lines.append((pymupdf.Point(lay.x(0), lay.y(ri)), pymupdf.Point(lay.x(22), lay.y(ri))))
            thick_lines.append((pymupdf.Point(lay.x(0), lay.y(ri + 1)), pymupdf.Point(lay.x(22), lay.y(ri + 1))))
    thick_lines.append((pymupdf.Point(lay.x(0), y_top), pymupdf.Point(lay.x(22), y_top)))
    thick_lines.append((pymupdf.Point(lay.x(0), y_bot), pymupdf.Point(lay.x(22), y_bot)))
    for p1, p2 in thick_lines:
        shape.draw_line(p1, p2)
    shape.finish(color=(0, 0, 0), width=thick_w)

    shape.commit()
    writer.write_text(page)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def _char_class(ch: str) -> str:
    if ch.isascii():
        return "ascii"
    if ch in "（）()～〜、,":
        return "punct"
    return "cjk"


def _wrap_point(text: str, width_of, inner: float) -> int | None:  # noqa: ANN001
    """2 行に折り返す位置を返す. 空白 → 文字種の境界 (Web|会議) → 中央 の順で優先する."""
    fits = [n for n in range(1, len(text)) if width_of(text[:n]) <= inner and width_of(text[n:]) <= inner]
    if not fits:
        return None
    mid = len(text) / 2
    spaces = [n for n in fits if text[n - 1] == " " or text[n] == " "]
    if spaces:
        return min(spaces, key=lambda n: abs(n - mid))
    bounds = [n for n in fits if _char_class(text[n - 1]) != _char_class(text[n])]
    if bounds:
        return min(bounds, key=lambda n: abs(n - mid))
    return min(fits, key=lambda n: abs(n - mid))
