"""ステップ2: ディープリサーチ（最重要・医学的根拠ベース）。

処理フロー:
  1. テーマに対するリサーチクエリをClaudeで5〜8個生成
  2. 各クエリでWeb検索し、ホワイトリストドメインを優先して収集
  3. citation_tracker に全主張＋出典を構造化保持
  4. Claudeに規定フォーマットのMarkdownを生成させる（出典のない記述は禁止）
  5. research.md と citations.json を output/research/ に保存
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from .utils.citation_tracker import CitationTracker
from .utils.claude_client import ClaudeClient
from .utils.common import (
    OUTPUT_DIR,
    ensure_dir,
    get_logger,
    slugify,
    today_iso,
    today_str,
)
from .utils.medical_sources import PRIORITY_DOMAINS, classify_source
from .utils.search_tools import SearchResult, SearchTools

logger = get_logger()


def _generate_queries(theme: str, client: ClaudeClient) -> List[str]:
    """テーマからリサーチクエリを5〜8個生成する。"""
    prompt = f"""小児科テーマ「{theme}」について、信頼できる医学情報を集めるための
検索クエリを5〜8個作ってください。日本小児科学会・厚生労働省・国立成育医療研究センター・
AAP・WHO・CDC などの一次情報に当たれるよう、具体的な日本語クエリにしてください。

出力は1行1クエリのプレーンテキストのみ。番号や記号は付けないでください。"""
    raw = client.complete(prompt, max_tokens=1000, temperature=0.4)
    queries = [ln.strip(" -・*0123456789.") for ln in raw.splitlines() if ln.strip()]
    queries = [q for q in queries if q][:8]
    if not queries:
        queries = [f"{theme} 小児科 ガイドライン", f"{theme} 厚生労働省", f"{theme} 受診 目安"]
    logger.info("リサーチクエリ %d 件を生成", len(queries))
    return queries


def _collect_sources(queries: List[str]) -> List[SearchResult]:
    """各クエリで検索し、ホワイトリスト優先で結果を収集・並べ替える。"""
    tools = SearchTools()
    collected: List[SearchResult] = []
    seen_urls = set()

    for q in queries:
        # ホワイトリスト絞り込みを併用（Tavily/フォールバック双方で有効）
        for r in tools.search(q):
            if r.url and r.url not in seen_urls:
                seen_urls.add(r.url)
                collected.append(r)

    # 信頼度A→B→Cの順、かつA/Bを優先採用
    def rank_key(res: SearchResult) -> Tuple[int, int]:
        _, rank = classify_source(res.url)
        order = {"A": 0, "B": 1, "C": 2}.get(rank, 3)
        return (order, 0)

    collected.sort(key=rank_key)
    logger.info("出典候補 %d 件を収集（ホワイトリスト優先で並べ替え済み）", len(collected))
    return collected[:20]


def _build_citation_tracker(sources: List[SearchResult]) -> CitationTracker:
    """収集ソースから CitationTracker を作る（各ソースに C01, C02... を割り当て）。

    ここで割り当てた C-ID を Claude に渡し、リサーチ本文・台本・監修Excel まで
    一貫した出典IDとして使い回す。
    """
    tracker = CitationTracker()
    for s in sources:
        org, rank = classify_source(s.url)
        claim = (s.snippet or s.title or "").strip()[:200]
        if claim:
            tracker.add(claim=claim, url=s.url, org=org, confidence=rank)
    return tracker


def _build_source_digest(tracker: CitationTracker, sources: List[SearchResult]) -> str:
    """Claudeに渡す出典ダイジェスト文字列を作る（C-ID付き）。"""
    # claim_id -> SearchResult の対応（URLで突き合わせ）
    url_to_source = {s.url: s for s in sources}
    lines = []
    for c in tracker.items:
        src = url_to_source.get(c.url)
        body = (src.content or src.snippet or c.claim if src else c.claim)[:1200]
        title = src.title if src else c.claim[:60]
        lines.append(
            f"[{c.claim_id}] 機関={c.org} 信頼度={c.confidence}\n"
            f"URL: {c.url}\nタイトル: {title}\n抜粋: {body}\n"
        )
    return "\n".join(lines)


def _generate_research_markdown(
    theme: str, tracker: CitationTracker, sources: List[SearchResult],
    client: ClaudeClient,
) -> str:
    """規定フォーマットのリサーチMarkdownを生成する。

    本文中の出典参照は [C01] のように citations.json と同一のIDを用いる。
    これにより step3 の台本 [ref:C01] や step5 のExcel Sheet2 と対応が取れる。
    """
    digest = _build_source_digest(tracker, sources)
    accessed = today_iso()
    prompt = f"""テーマ「{theme}」について、以下の出典資料【のみ】を根拠に、保護者向けの
医学リサーチをMarkdownで作成してください。出典のない記述は絶対に書かないでください。
各主張には、対応する出典のID（例: [C01]）を本文中に必ず添えてください。
ID は下記資料の角括弧内のもの（C01, C02...）をそのまま使ってください。新しい番号を作らないこと。

# 出典資料
{digest}

# 出力フォーマット（この見出し構成を厳守）
# {theme}
## 医学的概要
## 原因・機序
## 保護者がよく誤解している点
## 受診の目安（救急/当日/翌日以降）
## 家庭でのケア
## ガイドライン参照状況（最新版年度を明記。年度が不明なものは「年度不明」と書く）
## 出典一覧
（各出典を「- [C01] 機関名 / URL / 信頼度A-C / アクセス日 {accessed}」の形式で列挙）

# 注意
- 緊急症状に該当しうる内容は「受診の目安」より前に警告を置く。
- 商品名は使わず一般名のみ。診断・処方の断定をしない。
- 最後に免責文「本コンテンツは一般的情報提供です。診断・治療は必ず医療機関にご相談ください」を付ける。"""
    return client.complete(prompt, max_tokens=8000, temperature=0.4)


def research(theme: str) -> dict:
    """リサーチ本体。research.md と citations.json を保存し、パスを返す。

    返り値: {"theme", "markdown_path", "citations_path", "markdown"}
    """
    logger.info("=== ステップ2: ディープリサーチ開始（テーマ: %s）===", theme)
    client = ClaudeClient()

    queries = _generate_queries(theme, client)
    sources = _collect_sources(queries)

    if not sources:
        logger.warning("検索結果がゼロ件でした。Claudeの一般知識ベースで概要を作成します（出典は限定的）。")

    tracker = _build_citation_tracker(sources)
    markdown = _generate_research_markdown(theme, tracker, sources, client)

    slug = slugify(theme)
    base = ensure_dir(OUTPUT_DIR / "research")
    md_path = base / f"{slug}_{today_str()}.md"
    cit_path = base / f"{slug}_{today_str()}_citations.json"

    md_path.write_text(markdown, encoding="utf-8")
    tracker.save(cit_path)

    logger.info("リサーチMarkdown保存: %s", md_path)
    logger.info("出典JSON保存: %s（出典 %d 件）", cit_path, len(tracker))

    return {
        "theme": theme,
        "markdown_path": str(md_path),
        "citations_path": str(cit_path),
        "markdown": markdown,
    }


if __name__ == "__main__":
    import sys

    t = sys.argv[1] if len(sys.argv) > 1 else "乳児の便秘"
    print(json.dumps(research(t), ensure_ascii=False, indent=2))
