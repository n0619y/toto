"""カレンダー PDF (2枚目形式) から、コマ単位の色とラベルを機械的に取り出す.

出力は ``{(day, member): [SlotInfo, SlotInfo, SlotInfo]}``。
元の PDF と、本ツールが生成した PDF の両方に使い、``compare`` で突き合わせる。

レイアウトの推定方法:

* 最初の「時刻」行にある 8:30 / 12:00 / 17:00 の文字位置から 21 コマの中心 x を決める
* 「時刻」ラベルの y 位置から各週ブロックの行位置を決める
  （時刻行 → 日付行 → メンバー行 ×N の順、行高は等間隔）
* 各コマ中心の塗り色を取り、同色の連続区間をセル候補とする
* セル候補内に複数の文字塊 (x 中心が離れている) があれば、そこで分割する
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

from .model import CODE_COLOR, COLOR_CODE


@dataclass
class SlotInfo:
    color: str  # "Y" / "G" / "P" / "B" / "W"
    lines: tuple[str, ...] = ()
    cross: bool = False

    @property
    def label(self) -> str:
        return "".join(self.lines)

    def key(self) -> tuple:
        # 文字の並びは PDF の span 順に依存する (LibreOffice 出力は折り返し行の順が入れ替わる) ので
        # 文字の多重集合で比較する
        return (self.color, "".join(sorted(_norm(self.label))), self.cross)


@dataclass
class ExtractedCalendar:
    title: str
    members: list[str]
    slots: dict[tuple[int, str], list[SlotInfo]] = field(default_factory=dict)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _color_code(rgb) -> str:  # noqa: ANN001
    r, g, b = (int(round(v * 255)) for v in rgb)
    hexv = f"{r:02X}{g:02X}{b:02X}"
    if hexv in COLOR_CODE:
        return COLOR_CODE[hexv]
    # 近似色 (LibreOffice 変換時の丸めなど)
    best, bestd = "W", 1e9
    for code_hex, code in COLOR_CODE.items():
        cr, cg, cb = int(code_hex[0:2], 16), int(code_hex[2:4], 16), int(code_hex[4:6], 16)
        d = (cr - r) ** 2 + (cg - g) ** 2 + (cb - b) ** 2
        if d < bestd:
            best, bestd = code, d
    return best if bestd < 30**2 else "?"


def _page_with_full_content(doc: pymupdf.Document) -> pymupdf.Page:
    """CropBox が MediaBox より小さい PDF (元ファイルがそう) でも全内容を扱えるようにする."""
    page = doc[0]
    if page.cropbox != page.mediabox:
        page.set_cropbox(page.mediabox)
    return page


def extract_calendar(path: str, members: list[str] | None = None) -> ExtractedCalendar:
    doc = pymupdf.open(path)
    page = _page_with_full_content(doc)
    big = pymupdf.Rect(-10000, -10000, 10000, 10000)

    # ---- 文字 -------------------------------------------------------------------
    spans: list[tuple[pymupdf.Rect, str]] = []
    for block in page.get_textpage(clip=big).extractDICT()["blocks"]:
        for line in block["lines"]:
            for sp in line["spans"]:
                if sp["text"].strip():
                    spans.append((pymupdf.Rect(sp["bbox"]), sp["text"].strip()))

    # ---- 塗り矩形・線 ------------------------------------------------------------
    fills: list[tuple[pymupdf.Rect, str]] = []
    diagonals: list[pymupdf.Rect] = []
    for dr in page.get_drawings():
        fill = dr.get("fill")
        if fill is not None and dr["type"] in ("f", "fs"):
            code = _color_code(fill)
            if code != "?" and [round(v, 2) for v in fill] != [0, 0, 0]:
                for item in dr["items"]:
                    if item[0] == "re":
                        fills.append((item[1], code))
                    elif item[0] == "qu":
                        fills.append((item[1].rect, code))
        for item in dr["items"]:
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) > 3 and abs(p1.y - p2.y) > 3:
                    diagonals.append(pymupdf.Rect(p1, p2).normalize())

    # ---- レイアウト推定 ----------------------------------------------------------
    time_labels = sorted((r for r, t in spans if t == "時刻"), key=lambda r: r.y0)
    if not time_labels:
        raise ValueError("『時刻』行が見つかりません")
    first_time_row = time_labels[0]
    slot_texts = sorted(
        (r for r, t in spans if t in ("8:30", "12:00", "17:00") and abs(r.y0 - first_time_row.y0) < 3),
        key=lambda r: r.x0,
    )
    if len(slot_texts) != 21:
        raise ValueError(f"時刻ラベルが 21 個ではありません: {len(slot_texts)}")
    # 列座標: 時刻ラベルは列中央に無いことがあるので、色付きセルの左右端 (=罫線位置) から求める.
    # 色付きセルはコマ列の範囲にしか無いので、その最小/最大 x を 21 等分すればコマ境界になる.
    colored_edges = [v for r, c in fills if c != "W" for v in (r.x0, r.x1)]
    if colored_edges:
        gx0, gx1 = min(colored_edges), max(colored_edges)
        slot_w = (gx1 - gx0) / 21
        centers = [gx0 + slot_w * (k + 0.5) for k in range(21)]
    else:
        centers = [(r.x0 + r.x1) / 2 for r in slot_texts]
        slot_w = (centers[-1] - centers[0]) / 20
    # 行高: 時刻行同士の間隔 / (1 + 1 + メンバー数)
    if members is None:
        # 日付行の次の行から「時刻」までの左端ラベルをメンバーとみなす
        members = _guess_members(spans, time_labels, first_time_row)
    nrows_per_week = 2 + len(members)
    if len(time_labels) >= 2:
        row_h = (time_labels[1].y0 - time_labels[0].y0) / nrows_per_week
    else:
        row_h = first_time_row.height * 1.05

    title = ""
    for r, t in spans:
        if r.y1 <= first_time_row.y0 - row_h and "Schedule" in t:
            title = t

    def color_at(x: float, y: float) -> str:
        code = "W"
        for r, c in fills:
            if r.x0 - 0.3 <= x <= r.x1 + 0.3 and r.y0 - 0.3 <= y <= r.y1 + 0.3:
                code = c
        return code

    result = ExtractedCalendar(title=title, members=list(members))
    for time_rect in time_labels:
        time_cy = (time_rect.y0 + time_rect.y1) / 2
        day_row_y0 = time_cy + row_h / 2
        # 日付
        day_of_col: list[int | None] = []
        for di in range(7):
            x0 = centers[di * 3] - slot_w / 2
            x1 = centers[di * 3 + 2] + slot_w / 2
            txt = [t for r, t in spans if x0 <= (r.x0 + r.x1) / 2 < x1 and day_row_y0 <= (r.y0 + r.y1) / 2 < day_row_y0 + row_h]
            day_of_col.append(int(txt[0]) if txt and txt[0].isdigit() else None)
        for mi, member in enumerate(members):
            y0 = day_row_y0 + row_h * (mi + 1)
            y1 = y0 + row_h
            ymid = (y0 + y1) / 2
            colors = [color_at(cx, ymid) for cx in centers]
            texts = [(r, t) for r, t in spans if y0 <= (r.y0 + r.y1) / 2 < y1 and centers[0] - slot_w / 2 <= (r.x0 + r.x1) / 2 < centers[-1] + slot_w / 2]
            crosses = [d for d in diagonals if y0 - 1 <= d.y0 and d.y1 <= y1 + 1]
            row_slots = _split_row(colors, centers, slot_w, texts, crosses)
            for di, day in enumerate(day_of_col):
                if day is None:
                    continue
                result.slots[(day, member)] = row_slots[di * 3 : di * 3 + 3]
    return result


def _guess_members(spans, time_labels, first_time_row) -> list[str]:  # noqa: ANN001
    """時刻行の左端ラベル位置と同じ x にある、時刻でも数字でもない文字をメンバー名とみなす."""
    label_x = (first_time_row.x0 + first_time_row.x1) / 2
    rows_y = [r.y0 for r in time_labels]
    if len(rows_y) < 2:
        raise ValueError("メンバー名を推定できません (members を指定してください)")
    names = []
    for r, t in sorted(spans, key=lambda s: s[0].y0):
        if abs((r.x0 + r.x1) / 2 - label_x) < 12 and rows_y[0] < r.y0 < rows_y[1] and t != "時刻" and not t.isdigit():
            names.append(t)
    return names


def _split_row(colors, centers, slot_w, texts, crosses):  # noqa: ANN001
    """1 メンバー行 (21 コマ) を、同色連続区間 + 文字塊で分割してコマごとの情報にする."""
    n = len(colors)
    slots: list[SlotInfo | None] = [None] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and colors[j + 1] == colors[i]:
            j += 1
        x0 = centers[i] - slot_w / 2
        x1 = centers[j] + slot_w / 2
        run_texts = [(r, t) for r, t in texts if x0 <= (r.x0 + r.x1) / 2 < x1]
        # 文字塊 (x 中心が近いもの) にまとめる
        clusters: list[list[tuple[pymupdf.Rect, str]]] = []
        for r, t in sorted(run_texts, key=lambda s: (s[0].x0 + s[0].x1) / 2):
            cx = (r.x0 + r.x1) / 2
            if clusters and abs(cx - _cluster_cx(clusters[-1])) < slot_w * 0.35:
                clusters[-1].append((r, t))
            else:
                clusters.append([(r, t)])
        owner = _assign_clusters(centers[i : j + 1], [_cluster_cx(c) for c in clusters])
        for k in range(i, j + 1):
            lines: tuple[str, ...] = ()
            if clusters:
                cl = clusters[owner[k - i]]
                lines = tuple(t for r, t in sorted(cl, key=lambda s: s[0].y0))
            cross = any(d.x0 - 1 <= centers[k] <= d.x1 + 1 for d in crosses)
            slots[k] = SlotInfo(colors[k], lines, cross)
        i = j + 1
    return slots  # type: ignore[return-value]


def _assign_clusters(slot_centers: list[float], cluster_cx: list[float]) -> list[int]:
    """同色区間内のコマを文字塊に割り当てる.

    文字はセルの中央に描かれるので、「各文字塊が自分の担当区間の中央に来る」ように
    区間の分割位置を総当たりで決める.
    """
    n, k = len(slot_centers), len(cluster_cx)
    if k == 0:
        return [0] * n
    if k == 1:
        return [0] * n
    if k > n:
        # 文字塊がコマ数より多い (折り返しで span が割れた等): 最寄りの塊に割り当てる
        return [min(range(k), key=lambda t: abs(cluster_cx[t] - c)) for c in slot_centers]
    from itertools import combinations

    best, best_cost = None, float("inf")
    for cuts in combinations(range(1, n), k - 1):
        bounds = (0, *cuts, n)
        cost = 0.0
        for t in range(k):
            seg = slot_centers[bounds[t] : bounds[t + 1]]
            cost += abs((seg[0] + seg[-1]) / 2 - cluster_cx[t])
        if cost < best_cost:
            best, best_cost = bounds, cost
    owner = [0] * n
    for t in range(k):
        for idx in range(best[t], best[t + 1]):
            owner[idx] = t
    return owner


def _cluster_cx(cluster) -> float:  # noqa: ANN001
    return sum((r.x0 + r.x1) / 2 for r, _ in cluster) / len(cluster)


def slot_to_spec_text(info: SlotInfo) -> str:
    """抽出結果を roster.yaml のコマ指定文字列に変換する."""
    from .model import ROLES

    label = "".join(info.lines)
    lines = list(info.lines)
    if info.color == "Y" or info.color == "G":
        role = "1st" if info.color == "Y" else "2nd"
        if not lines:
            return role
        others = [ln for ln in lines if ln not in ROLES]
        if not others:
            return role
        if any(ln in ROLES for ln in lines):
            return f"{role}+{''.join(others)}"
        return f"{label}/{role}"
    if info.color == "P":
        return label
    if info.cross:
        return "×"
    return ""


def color_hex(code: str) -> str:
    return CODE_COLOR[code]
