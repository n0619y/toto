"""ステップ4a: 記事生成。

記事用台本(A)からMarkdownとHTMLを生成します:
  - HTMLの<head>に <meta name="author" content="監修: toto先生（小児科医）"> を挿入
  - 記事末尾に監修者表記ブロックと免責文を自動追加
  - アイキャッチ画像生成プロンプトを別ファイルに出力
  - 末尾に関連テーマ提案を追加
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown as md_lib

from .utils.claude_client import ClaudeClient
from .utils.common import (
    DISCLAIMER_TEXT,
    OUTPUT_DIR,
    ensure_dir,
    get_logger,
    load_settings,
    reviewer_display,
    reviewer_name,
    reviewer_title,
    slugify,
    today_str,
)

logger = get_logger()


def _reviewer_block_md() -> str:
    """記事末尾に付ける監修者ブロック（Markdown）。"""
    return (
        f"\n\n---\n\n**{reviewer_display()}**\n\n"
        f"> {DISCLAIMER_TEXT}\n"
    )


def _suggest_related_themes(theme: str, client: ClaudeClient) -> str:
    """関連テーマ提案を生成する。失敗時は簡易フォールバック。"""
    try:
        prompt = (
            f"小児科テーマ「{theme}」の記事の最後に載せる「関連テーマ提案」を5つ、"
            "保護者が次に読みたくなる切り口で、Markdownの箇条書きで出してください。説明文は不要。"
        )
        return client.complete(prompt, max_tokens=600, temperature=0.6)
    except Exception as exc:
        logger.warning("関連テーマ生成失敗: %s", exc)
        return "- 関連テーマの自動生成に失敗しました。"


def _eyecatch_prompt(theme: str, client: ClaudeClient) -> str:
    """アイキャッチ画像生成用プロンプトを生成する。"""
    design = load_settings()["design"]
    try:
        prompt = (
            f"小児科記事「{theme}」のアイキャッチ画像を作るための画像生成プロンプトを、"
            f"英語と日本語の両方で1案ずつ作ってください。配色は primary={design['primary_color']}, "
            f"accent={design['accent_color']} を基調に、やさしく安心感のあるフラットイラスト。"
            "医療広告ガイドラインに配慮し、特定の薬や患部の生々しい描写は避けること。"
        )
        return client.complete(prompt, max_tokens=600, temperature=0.7)
    except Exception as exc:
        logger.warning("アイキャッチプロンプト生成失敗: %s", exc)
        return f"A gentle flat illustration about '{theme}' for parents, soft pastel colors."


def _to_html(markdown_text: str, title: str) -> str:
    """MarkdownをHTMLに変換し、監修者metaタグ等を含む完全なHTMLを返す。"""
    design = load_settings()["design"]
    body_html = md_lib.markdown(
        markdown_text, extensions=["extra", "toc", "sane_lists", "tables"]
    )
    # metaディスクリプションを台本から拾う（あれば）
    desc_match = re.search(r"メタディスクリプション[：: ]*(.+)", markdown_text)
    description = desc_match.group(1).strip()[:120] if desc_match else title

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="author" content="{reviewer_display()}">
<meta name="description" content="{description}">
<title>{title}</title>
<style>
  body {{ font-family: "{design['font_main']}", sans-serif; line-height: 1.9;
          max-width: 760px; margin: 0 auto; padding: 24px; color: #333;
          background: {design['secondary_color']}; }}
  h1 {{ color: {design['primary_color']}; border-bottom: 4px solid {design['primary_color']}; padding-bottom: 8px; }}
  h2 {{ color: {design['primary_color']}; border-left: 6px solid {design['accent_color']}; padding-left: 10px; margin-top: 2em; }}
  h3 {{ color: {design['accent_color']}; }}
  .reviewer-badge {{ background: #fff; border: 2px solid {design['primary_color']};
                     border-radius: 12px; padding: 12px 16px; margin: 24px 0; font-weight: bold; }}
  .disclaimer {{ font-size: 0.9em; color: #666; background: #fff;
                 border-radius: 8px; padding: 12px; margin-top: 16px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #cdd; padding: 6px 10px; }}
</style>
</head>
<body>
<div class="reviewer-badge">{reviewer_display()}</div>
{body_html}
<div class="disclaimer">{DISCLAIMER_TEXT}</div>
</body>
</html>
"""


def build_article(theme: str, article_script_path: str, offline: bool = False) -> dict:
    """記事のMarkdown/HTML/アイキャッチプロンプトを生成・保存する。

    offline=True のときは関連テーマ・アイキャッチのClaude呼び出しを行わず、
    静的なフォールバック内容を使う（APIキー不要のデモ・検証用）。
    """
    logger.info("=== ステップ4a: 記事生成開始（テーマ: %s）===", theme)
    client = ClaudeClient()

    script = Path(article_script_path).read_text(encoding="utf-8")

    # タイトル抽出（最初のH1、無ければテーマ名）
    title_match = re.search(r"^#\s+(.+)$", script, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else theme

    # 監修者ブロックと関連テーマ提案を末尾に付与
    if offline:
        related = (f"- {theme}に関するよくある質問\n- 子供の体調変化のホームケア\n"
                   "- 受診の目安まとめ\n- 予防接種のスケジュール\n- 季節ごとの感染症対策")
        eyecatch = (f"A gentle flat illustration about '{theme}' for parents, "
                    "soft pastel colors, reassuring mood. ／ "
                    f"「{theme}」の保護者向けアイキャッチ。やさしいパステル調のフラットイラスト。")
    else:
        related = _suggest_related_themes(theme, client)
        eyecatch = _eyecatch_prompt(theme, client)

    full_md = script
    if reviewer_name() not in full_md:
        full_md += _reviewer_block_md()
    full_md += f"\n\n## 関連テーマ\n{related}\n"

    html = _to_html(full_md, title)

    slug = slugify(theme)
    base = ensure_dir(OUTPUT_DIR / "articles")
    md_path = base / f"{slug}_{today_str()}.md"
    html_path = base / f"{slug}_{today_str()}.html"
    eye_path = base / f"{slug}_{today_str()}_eyecatch_prompt.txt"

    md_path.write_text(full_md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    eye_path.write_text(eyecatch, encoding="utf-8")

    logger.info("記事Markdown: %s", md_path)
    logger.info("記事HTML: %s", html_path)
    logger.info("アイキャッチプロンプト: %s", eye_path)

    return {
        "article_md": str(md_path),
        "article_html": str(html_path),
        "eyecatch_prompt": str(eye_path),
        "title": title,
    }


if __name__ == "__main__":
    import sys

    print(build_article(sys.argv[1], sys.argv[2]))
