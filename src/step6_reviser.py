"""ステップ6: 監修フィードバックの自動反映（--revise）。

toto先生が記入した監修Excel（review_checklist.xlsx）を読み取り、
修正指示・監修判定・コメントを集約して、Claudeで各成果物を修正版に作り直します。

反映元として読むシート:
  - Sheet2「主張×出典」     : 監修判定が「要修正/削除」の主張＋コメント
  - Sheet3「必須チェック項目」: コメント記入のある項目
  - Sheet4「成果物別レビュー」: 「修正」マーク行＋コメント
  - Sheet5「修正指示記入欄」  : フリーフォーマット欄＋表形式の指示

修正版は元ファイル名に `_rev<N>` を付けて保存し、スライドと監修パッケージも作り直します。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from openpyxl import load_workbook

from .step4_article_builder import _to_html
from .step4_slide_builder import build_slides
from .step5_review_kit_builder import build_review_kit
from .utils.claude_client import ClaudeClient
from .utils.common import (
    OUTPUT_DIR,
    ensure_dir,
    get_logger,
    reviewer_name,
    slugify,
)

logger = get_logger()


# === 監修Excelの読み取り ====================================================
def _cell(ws, r, c) -> str:
    """セル値を文字列で安全に取得。"""
    v = ws.cell(row=r, column=c).value
    return str(v).strip() if v is not None else ""


def extract_instructions(xlsx_path: Path) -> Dict[str, List[str]]:
    """監修Excelから成果物別の修正指示を抽出する。

    返り値: {"記事": [...], "本編": [...], "Shorts": [...], "共通": [...]}
    """
    wb = load_workbook(str(xlsx_path), data_only=True)
    out: Dict[str, List[str]] = {"記事": [], "本編": [], "Shorts": [], "共通": []}

    def add(target: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        key = "共通"
        if "記事" in target:
            key = "記事"
        elif "本編" in target or "youtube" in target.lower() or "動画" in target:
            key = "本編"
        elif "shorts" in target.lower() or "ショート" in target:
            key = "Shorts"
        out[key].append(text)

    # --- Sheet2: 主張×出典（要修正/削除） ---
    if "主張×出典" in wb.sheetnames:
        ws = wb["主張×出典"]
        for r in range(2, ws.max_row + 1):
            verdict = _cell(ws, r, 7)
            if verdict in ("要修正", "削除"):
                cid, claim, comment = _cell(ws, r, 1), _cell(ws, r, 2), _cell(ws, r, 8)
                instr = f"[{verdict}] 主張{cid}「{claim}」"
                if comment:
                    instr += f" — 指示: {comment}"
                if verdict == "削除":
                    instr += "（この主張は削除すること）"
                out["共通"].append(instr)

    # --- Sheet3: 必須チェック項目（コメント or NG） ---
    if "必須チェック項目" in wb.sheetnames:
        ws = wb["必須チェック項目"]
        for r in range(2, ws.max_row + 1):
            check, comment = _cell(ws, r, 5), _cell(ws, r, 6)
            text = _cell(ws, r, 3)
            # チェック欄がNG系、またはコメントがあれば指示として扱う
            if comment or check in ("NG", "×", "要修正", "✗"):
                out["共通"].append(f"チェック項目「{text}」: {comment or check}")

    # --- Sheet4: 成果物別レビュー（「修正」マーク行） ---
    if "成果物別レビュー" in wb.sheetnames:
        ws = wb["成果物別レビュー"]
        section = "記事"  # 直近のセクション見出しで対象を判定
        for r in range(1, ws.max_row + 1):
            head = _cell(ws, r, 1)
            if head.startswith("■"):
                if "記事" in head:
                    section = "記事"
                elif "本編" in head:
                    section = "本編"
                elif "Shorts" in head:
                    section = "Shorts"
                continue
            # 行内のどこかに「修正」マークがあるか
            row_vals = [_cell(ws, r, c) for c in range(1, 6)]
            if any(v in ("修正", "要修正", "NG") for v in row_vals):
                comment = row_vals[-1]
                add(section, f"「{row_vals[0]}」を修正: {comment or '（コメントなし）'}")

    # --- Sheet5: 修正指示記入欄 ---
    if "修正指示記入欄" in wb.sheetnames:
        ws = wb["修正指示記入欄"]
        # 表形式（ヘッダー行4、データ行5以降）
        for r in range(5, ws.max_row + 1):
            target, place, content, pri = (
                _cell(ws, r, 1), _cell(ws, r, 2), _cell(ws, r, 3), _cell(ws, r, 4)
            )
            if content:
                instr = f"{place + ' / ' if place else ''}{content}"
                if pri:
                    instr += f"（優先度: {pri}）"
                add(target, instr)
        # フリーフォーマット欄（A2付近の長文。説明文プレースホルダは除外）
        free = _cell(ws, 2, 1)
        if free and "次回" not in free and "ここに修正指示" not in free:
            out["共通"].append(f"全体への指示: {free}")

    total = sum(len(v) for v in out.values())
    logger.info("監修Excelから %d 件の修正指示を抽出", total)
    return out


# === 成果物の特定 ===========================================================
def _theme_from_review(xlsx_path: Path) -> str:
    """同じフォルダの review_summary.md からテーマ名を取得する。"""
    summary = xlsx_path.parent / "review_summary.md"
    if summary.exists():
        m = re.search(r"\*\*テーマ\*\*[:：]\s*(.+)", summary.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip()
    # フォールバック: フォルダ名 <slug>_<日付> から推測
    return xlsx_path.parent.name.rsplit("_", 1)[0]


def _latest(folder: str, slug: str, suffix: str) -> str:
    """slug に一致する最新ファイルパスを返す（_rev版を優先的に拾う）。"""
    files = sorted((OUTPUT_DIR / folder).glob(f"{slug}_*{suffix}"))
    return str(files[-1]) if files else ""


def _next_rev_path(original: str) -> Path:
    """元パスから次のリビジョン番号を付けたパスを作る（..._rev1.md など）。"""
    p = Path(original)
    stem = re.sub(r"_rev\d+$", "", p.stem)
    existing = list(p.parent.glob(f"{stem}_rev*{p.suffix}"))
    nums = [int(m.group(1)) for f in existing
            if (m := re.search(r"_rev(\d+)" + re.escape(p.suffix) + "$", f.name))]
    nxt = (max(nums) + 1) if nums else 1
    return p.parent / f"{stem}_rev{nxt}{p.suffix}"


# === Claudeによる修正適用 ===================================================
def _apply_revision(label: str, original_text: str, instructions: List[str],
                    client: ClaudeClient) -> str:
    """元テキストに修正指示を適用した改訂版をClaudeに作らせる。"""
    if not original_text.strip():
        return original_text
    instr_block = "\n".join(f"- {i}" for i in instructions) or "（特になし）"
    prompt = f"""以下は監修者（小児科医）から戻ってきた「{label}」のドラフトと修正指示です。
修正指示を反映した改訂版を作成してください。

【厳守】
- 指示された箇所のみ修正し、それ以外の構成・表現・引用元ID([ref:Cxx])はできるだけ維持する。
- 「削除」指示のある主張は本文から取り除く。
- 監修者表記「{reviewer_name()}」と免責文は必ず残す。
- 出力は改訂後の本文【のみ】。前後の説明・コメントは書かない。

# 修正指示
{instr_block}

# 元のドラフト
{original_text}"""
    return client.complete(prompt, max_tokens=8000, temperature=0.4)


# === メイン ================================================================
def revise(xlsx_path: str) -> Dict:
    """監修Excelの指示を反映して成果物を作り直す。"""
    xp = Path(xlsx_path)
    if not xp.exists():
        raise FileNotFoundError(f"監修Excelが見つかりません: {xp}")

    theme = _theme_from_review(xp)
    slug = slugify(theme)
    logger.info("=== ステップ6: 監修フィードバック反映開始（テーマ: %s）===", theme)

    instructions = extract_instructions(xp)
    if sum(len(v) for v in instructions.values()) == 0:
        logger.warning("修正指示が見つかりませんでした。Excelの記入欄をご確認ください。")
        print("⚠️ 修正指示が空でした。監修Excelに記入してから再実行してください。")
        return {"theme": theme, "applied": 0}

    client = ClaudeClient()

    # 元成果物の特定
    article_md_path = _latest("articles", slug, ".md")
    youtube_path = _latest("scripts", slug, "_youtube.md")
    shorts_path = _latest("scripts", slug, "_shorts.md")

    artifacts: Dict = {"citations_path": _latest("research", slug, "_citations.json")}

    # --- 記事の改訂 ---
    if article_md_path:
        original = Path(article_md_path).read_text(encoding="utf-8")
        revised = _apply_revision(
            "記事", original, instructions["記事"] + instructions["共通"], client
        )
        new_md = _next_rev_path(article_md_path)
        new_md.write_text(revised, encoding="utf-8")
        # HTMLも作り直す
        title_m = re.search(r"^#\s+(.+)$", revised, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else theme
        new_html = new_md.with_suffix(".html")
        new_html.write_text(_to_html(revised, title), encoding="utf-8")
        artifacts["article_md"] = str(new_md)
        logger.info("記事を改訂: %s", new_md)

    # --- 台本（本編・Shorts）の改訂 ---
    if youtube_path:
        original = Path(youtube_path).read_text(encoding="utf-8")
        revised = _apply_revision(
            "YouTube本編台本", original, instructions["本編"] + instructions["共通"], client
        )
        new_yt = _next_rev_path(youtube_path)
        new_yt.write_text(revised, encoding="utf-8")
        artifacts["youtube_script"] = str(new_yt)
        logger.info("本編台本を改訂: %s", new_yt)

    if shorts_path:
        original = Path(shorts_path).read_text(encoding="utf-8")
        revised = _apply_revision(
            "YouTube Shorts台本", original, instructions["Shorts"] + instructions["共通"], client
        )
        new_sh = _next_rev_path(shorts_path)
        new_sh.write_text(revised, encoding="utf-8")
        artifacts["shorts_script"] = str(new_sh)
        logger.info("Shorts台本を改訂: %s", new_sh)

    # --- スライドの作り直し ---
    if artifacts.get("youtube_script") and artifacts.get("shorts_script"):
        slides = build_slides(
            theme + "（改訂版）",
            artifacts["youtube_script"],
            artifacts["shorts_script"],
        )
        artifacts.update(slides)

    # --- 監修パッケージの作り直し ---
    review = build_review_kit(theme + "（改訂版）", artifacts)

    applied = sum(len(v) for v in instructions.values())
    print("\n========================================")
    print(f"✅ 監修フィードバックを反映しました（指示 {applied} 件）")
    print(f"記事(改訂):   {artifacts.get('article_md', '-')}")
    print(f"本編スライド: {artifacts.get('slides_main', '-')}")
    print(f"Shorts:      {artifacts.get('slides_shorts', '-')}")
    print(f"📋 再監修パッケージ: {review.get('review_xlsx', '-')}")
    print("========================================\n")

    return {"theme": theme, "applied": applied, "artifacts": artifacts, "review": review}


if __name__ == "__main__":
    import sys

    revise(sys.argv[1])
