"""ステップ3: 台本作成。

リサーチ結果(research.md)から3種類の台本を生成します:
  (A) 記事用台本     2500〜4000字 / SEO配慮 / FAQ必須 / [ref:Cxx]埋め込み
  (B) YouTube本編用  1500〜2500字 / スライド表形式 / 口語ナレーション
  (C) Shorts用       200〜350字 / 強いフック / スライド3〜5枚

それぞれ output/scripts/ に保存します。
"""

from __future__ import annotations

import json
from pathlib import Path

from .utils.citation_tracker import CitationTracker
from .utils.claude_client import ClaudeClient
from .utils.common import (
    OUTPUT_DIR,
    DISCLAIMER_TEXT,
    ensure_dir,
    get_logger,
    load_settings,
    reviewer_display,
    slugify,
    today_str,
)

logger = get_logger()


def _citations_context(citations_path: str) -> str:
    """出典JSONを読み込み、Claudeに渡す参照ID一覧テキストを作る。"""
    tracker = CitationTracker.load(Path(citations_path))
    if not tracker:
        return "（出典データなし。リサーチ本文中の[Sxx]を参照すること）"
    return "\n".join(
        f"{c.claim_id}: {c.claim[:80]} / {c.org} / 信頼度{c.confidence} / {c.url}"
        for c in tracker.items
    )


def _write_article_script(theme, research_md, cit_ctx, client) -> str:
    cfg = load_settings()["output"]
    prompt = f"""テーマ「{theme}」の保護者向け【記事用台本】を作成してください。

# リサーチ本文
{research_md}

# 利用可能な引用元ID（各段落末尾に [ref:Cxx] 形式で必ず付与）
{cit_ctx}

# 要件
- 文字数: {cfg['article_min_chars']}〜{cfg['article_max_chars']}字
- 冒頭にSEO用の「タイトル」「メタディスクリプション（120字以内）」を明記
- H2/H3の見出し構造（Markdown）
- 保護者目線。専門用語には必ず（注: ...）で注釈
- 緊急症状があれば冒頭に救急受診の警告
- 「よくある質問（FAQ）」セクションを必須で設ける（Q&A形式3問以上）
- 各段落の末尾に引用元ID [ref:Cxx] を埋め込む
- 末尾に「{reviewer_display()}」を必ず明記
- 末尾に免責文「{DISCLAIMER_TEXT}」
- 診断・処方の断定はしない。商品名は使わず一般名のみ。"""
    return client.complete(prompt, max_tokens=8000, temperature=0.5)


def _write_youtube_script(theme, research_md, cit_ctx, client) -> str:
    cfg = load_settings()["output"]
    prompt = f"""テーマ「{theme}」の【YouTube本編用台本】（6〜10分・{cfg['youtube_min_chars']}〜{cfg['youtube_max_chars']}字）を作成。

# リサーチ本文
{research_md}

# 利用可能な引用元ID
{cit_ctx}

# 要件
- 構成: 冒頭フック（15秒以内）→ 本編 → まとめ → CTA（チャンネル登録等）
- スライドごとに必ず次のMarkdown表で書く:
  | 枚数 | タイトル | 本文 | ナレーション | 引用元ID |
- 本文は1スライド3行以内。ナレーションは別撮り想定の自然な口語。
- 1枚目（表紙）と最終スライド（エンドカード）に「{reviewer_display()}」を入れる。
- 緊急症状は早い段階で警告。商品名禁止・一般名のみ。診断/処方の断定なし。
- 最終スライドに免責文「{DISCLAIMER_TEXT}」。"""
    return client.complete(prompt, max_tokens=8000, temperature=0.5)


def _write_shorts_script(theme, research_md, cit_ctx, client) -> str:
    cfg = load_settings()["output"]
    prompt = f"""テーマ「{theme}」の【YouTube Shorts用台本】（45〜60秒・{cfg['shorts_min_chars']}〜{cfg['shorts_max_chars']}字）を作成。

# リサーチ本文（要点のみ使う）
{research_md}

# 利用可能な引用元ID
{cit_ctx}

# 要件
- 1秒以内の強いフックから始める
- メッセージは1つに絞る
- スライド3〜5枚。各スライドに「表示秒数」を明記
- 次のMarkdown表で書く:
  | 枚数 | 表示秒数 | タイトル | 本文 | ナレーション | 引用元ID |
- 表紙/最終スライドに「{reviewer_display()}」
- 最終スライドに短い免責文。商品名禁止・一般名のみ・断定なし。"""
    return client.complete(prompt, max_tokens=4000, temperature=0.5)


def write_scripts(theme: str, research_md_path: str, citations_path: str) -> dict:
    """3種類の台本を生成・保存し、パスを返す。"""
    logger.info("=== ステップ3: 台本作成開始（テーマ: %s）===", theme)
    client = ClaudeClient()

    research_md = Path(research_md_path).read_text(encoding="utf-8")
    cit_ctx = _citations_context(citations_path)

    article = _write_article_script(theme, research_md, cit_ctx, client)
    youtube = _write_youtube_script(theme, research_md, cit_ctx, client)
    shorts = _write_shorts_script(theme, research_md, cit_ctx, client)

    slug = slugify(theme)
    base = ensure_dir(OUTPUT_DIR / "scripts")
    paths = {
        "article_script": base / f"{slug}_{today_str()}_article.md",
        "youtube_script": base / f"{slug}_{today_str()}_youtube.md",
        "shorts_script": base / f"{slug}_{today_str()}_shorts.md",
    }
    paths["article_script"].write_text(article, encoding="utf-8")
    paths["youtube_script"].write_text(youtube, encoding="utf-8")
    paths["shorts_script"].write_text(shorts, encoding="utf-8")

    for name, p in paths.items():
        logger.info("%s を保存: %s", name, p)

    return {k: str(v) for k, v in paths.items()}


if __name__ == "__main__":
    import sys

    print(write_scripts(sys.argv[1], sys.argv[2], sys.argv[3]))
