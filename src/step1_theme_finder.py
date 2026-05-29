"""ステップ1: テーマ検索。

Googleトレンド（pytrends）のシードキーワードから関連ワードを取得し、
Q&Aサイトのよくある質問タイトルを補助的に収集して、Claudeで「保護者が本当に
知りたい疑問か」「医学的に正確な回答が可能か」「季節性・話題性」を採点します。
スコア上位10テーマを output/themes/YYYYMMDD.json に保存します。

検索やトレンド取得に失敗しても、組み込みのシードテーマでフォールバックします。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from .utils.claude_client import ClaudeClient
from .utils.common import OUTPUT_DIR, ensure_dir, get_logger, today_str

logger = get_logger()

# Googleトレンドに渡すシードキーワード
SEED_KEYWORDS = ["子供", "赤ちゃん", "小児", "発熱", "予防接種"]

# トレンド・検索が全滅したときのフォールバック候補
FALLBACK_THEMES = [
    "子供の発熱対応", "乳児の便秘", "子供の咳が続くとき", "予防接種のスケジュール",
    "子供の脱水症状の見分け方", "とびひ（伝染性膿痂疹）のケア", "子供の鼻水・鼻づまり",
    "熱性けいれんへの対応", "子供の嘔吐・下痢のホームケア", "アトピー性皮膚炎の保湿ケア",
]


def _fetch_trends() -> List[str]:
    """pytrends で関連急上昇ワードを取得する。失敗時は空リスト。"""
    related: List[str] = []
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="ja-JP", tz=540)
        for kw in SEED_KEYWORDS:
            try:
                pytrends.build_payload([kw], geo="JP", timeframe="now 7-d")
                queries = pytrends.related_queries()
                rising = queries.get(kw, {}).get("rising")
                if rising is not None:
                    related.extend(rising["query"].astype(str).tolist()[:5])
                time.sleep(1.0)  # レート制限への配慮
            except Exception as exc:
                logger.debug("トレンド取得失敗 (%s): %s", kw, exc)
        logger.info("Googleトレンドから %d 件の関連ワードを取得", len(related))
    except Exception as exc:
        logger.warning("pytrends 利用不可: %s — シードのみで継続", exc)
    return related


# Q&Aサイトの小児・育児カテゴリーのページ（robots.txt遵守の上で巡回）
QA_CATEGORY_URLS = [
    # Yahoo!知恵袋 「子育ての悩み」「子供の病気」関連カテゴリー
    "https://chiebukuro.yahoo.co.jp/category/2078297745/question/list",
    "https://chiebukuro.yahoo.co.jp/category/2079420109/question/list",
    # 教えて!goo 「子育て・育児・新生児」関連
    "https://oshiete.goo.ne.jp/category/674/",
    "https://oshiete.goo.ne.jp/category/210/",
]


def _scrape_qa_sites() -> List[str]:
    """Q&Aサイトの小児カテゴリーを直接スクレイピングして質問タイトルを収集する。

    robots.txt遵守・UA設定・1秒間隔は SearchTools 側で担保。
    サイト構造変更で取得できない場合は空リストを返し、呼び出し側で検索フォールバックする。
    """
    titles: List[str] = []
    try:
        from bs4 import BeautifulSoup

        from .utils.search_tools import SearchTools

        tools = SearchTools()
        for url in QA_CATEGORY_URLS:
            html_text = tools.fetch_raw_html(url)
            if not html_text:
                continue
            soup = BeautifulSoup(html_text, "html.parser")
            # 質問タイトルらしきリンクを広めに拾う（サイト構造差異に頑健に）
            for a in soup.find_all("a"):
                text = a.get_text(strip=True)
                href = a.get("href", "")
                if text and 8 <= len(text) <= 60 and (
                    "question" in href or "/qa/" in href or text.endswith(("？", "?"))
                ):
                    titles.append(text)
        logger.info("Q&Aサイト直接スクレイピングで %d 件のタイトルを取得", len(titles))
    except Exception as exc:
        logger.debug("Q&A直接スクレイピング失敗: %s", exc)
    return titles


def _search_faq_titles() -> List[str]:
    """検索経由でQ&Aのよくある質問タイトルを収集するフォールバック。"""
    titles: List[str] = []
    try:
        from .utils.search_tools import SearchTools

        tools = SearchTools()
        for q in ["子供 発熱 知恵袋 質問", "赤ちゃん 病気 教えて goo 相談", "小児 受診 目安 質問"]:
            for r in tools.search(q, max_results=5):
                if r.title:
                    titles.append(r.title)
    except Exception as exc:
        logger.debug("FAQ検索フォールバック失敗: %s", exc)
    return titles


def _fetch_faq_titles() -> List[str]:
    """Q&Aサイトのよくある質問タイトルを収集する。

    まず直接スクレイピングを試み、取得できなければ検索フォールバックに切り替える。
    """
    titles = _scrape_qa_sites()
    if len(titles) < 5:  # 直接取得が不十分なら検索で補う
        logger.info("直接スクレイピングが不十分のため検索フォールバックを併用")
        titles.extend(_search_faq_titles())
    return titles


def _score_with_claude(candidates: List[str]) -> List[dict]:
    """Claudeで候補テーマを採点し、JSON配列(辞書リスト)で返す。"""
    client = ClaudeClient()
    bullet = "\n".join(f"- {c}" for c in candidates)
    prompt = f"""以下は小児科コンテンツのテーマ候補です。各候補を評価し、上位10件を選んでください。

# 候補
{bullet}

# 評価観点（各5点満点）
1. parent_need: 保護者が本当に知りたい疑問か
2. medical_accuracy: 医学的に正確な回答が出典付きで可能か
3. timeliness: 季節性・話題性

# 出力形式（厳密にこのJSONのみ。前後に説明文を付けない）
[
  {{
    "theme": "テーマ名（保護者目線の自然な日本語に整える）",
    "parent_need": 5,
    "medical_accuracy": 5,
    "timeliness": 4,
    "total": 14,
    "reason": "選定理由を1文で",
    "season_or_topic": "季節性や話題性のメモ"
  }}
]
total は3観点の合計。total降順で最大10件。"""
    raw = client.complete(prompt, max_tokens=4000, temperature=0.3)
    return _parse_json_array(raw)


def _parse_json_array(raw: str) -> List[dict]:
    """Claude応答からJSON配列を抽出してパースする。"""
    raw = raw.strip()
    # コードフェンス除去
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        raw = raw[raw.find("[") :] if "[" in raw else raw
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as exc:
        logger.warning("テーマ採点JSONのパース失敗: %s", exc)
        return []


def find_themes(auto: bool = True, interactive: bool = False) -> dict:
    """テーマ検索の本体。選定結果dictを返す。

    返り値: {"path": <保存先json>, "themes": [...], "selected": <選択テーマ or None>}
    """
    logger.info("=== ステップ1: テーマ検索を開始 ===")

    candidates: List[str] = []
    candidates.extend(_fetch_trends())
    candidates.extend(_fetch_faq_titles())
    # 重複除去しつつシードも足す
    candidates.extend(FALLBACK_THEMES)
    seen = set()
    uniq = []
    for c in candidates:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    candidates = uniq[:40]
    logger.info("テーマ候補 %d 件を採点します", len(candidates))

    try:
        scored = _score_with_claude(candidates)
    except Exception as exc:
        logger.warning("Claude採点に失敗: %s — フォールバックテーマを使用", exc)
        scored = [
            {"theme": t, "parent_need": 4, "medical_accuracy": 4, "timeliness": 3,
             "total": 11, "reason": "フォールバック候補", "season_or_topic": "-"}
            for t in FALLBACK_THEMES
        ]

    scored = sorted(scored, key=lambda x: x.get("total", 0), reverse=True)[:10]

    # 保存
    out_path = ensure_dir(OUTPUT_DIR / "themes") / f"{today_str()}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)
    logger.info("テーマ候補を保存: %s", out_path)

    selected: Optional[str] = None
    if interactive and not auto:
        selected = _interactive_select(scored)
    elif scored:
        selected = scored[0]["theme"]
        logger.info("自動選択テーマ: %s", selected)

    return {"path": str(out_path), "themes": scored, "selected": selected}


def _interactive_select(themes: List[dict]) -> Optional[str]:
    """対話モードでテーマを選ばせる。"""
    print("\n=== テーマ候補 ===")
    for i, t in enumerate(themes, 1):
        print(f"  {i:2d}. {t['theme']}  (score={t.get('total','?')})  {t.get('reason','')}")
    print("   0. 手動入力")
    while True:
        choice = input("テーマ番号を選んでください > ").strip()
        if choice == "0":
            return input("テーマ名を入力 > ").strip() or None
        if choice.isdigit() and 1 <= int(choice) <= len(themes):
            return themes[int(choice) - 1]["theme"]
        print("正しい番号を入力してください。")


if __name__ == "__main__":
    result = find_themes(auto=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
