#!/usr/bin/env python3
"""小児科コンテンツ自動生成システム — エントリーポイント。

非エンジニアの方でも `python main.py` 一発で動くように作られています。
詳しい使い方・初期セットアップは README.md をご覧ください。

使い方:
  python main.py                          # フル自動（テーマ選定〜監修パッケージまで）
  python main.py --interactive            # 各ステップで確認しながら進める
  python main.py --theme "子供の発熱対応"   # テーマを指定して実行
  python main.py --step 2 --input <file>  # 特定ステップだけ実行
  python main.py --review-only "乳児の便秘" # 監修パッケージのみ再生成
  python main.py --revise <review.xlsx>    # 監修Excelの修正指示を成果物へ自動反映
  python main.py --auto                    # テーマ自動選択（デフォルト挙動）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# src パッケージを import できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.common import get_logger, reviewer_display  # noqa: E402

logger = get_logger()


def _print_summary(theme, artifacts, review):
    """完了サマリーをコンソールに表示する（依頼仕様の体裁）。"""
    print("\n========================================")
    print("✅ 全工程完了")
    print(f"記事:        {artifacts.get('article_md', '-')}")
    print(f"本編スライド: {artifacts.get('slides_main', '-')}")
    print(f"Shorts:      {artifacts.get('slides_shorts', '-')}")
    print(f"📋 監修パッケージ: {review.get('review_xlsx', '-')}")
    print(f"   → {reviewer_display().replace('監修: ', '')}、このファイルを開いて監修をお願いします")
    print("========================================\n")


def run_full_pipeline(theme: str | None, interactive: bool, auto: bool) -> None:
    """ステップ1〜5を通しで実行する。"""
    from src import (
        step1_theme_finder,
        step2_researcher,
        step3_script_writer,
        step4_article_builder,
        step4_slide_builder,
        step5_review_kit_builder,
    )

    artifacts: dict = {}

    # --- ステップ1: テーマ ---
    if not theme:
        result = step1_theme_finder.find_themes(auto=not interactive, interactive=interactive)
        theme = result["selected"]
        if not theme:
            logger.error("テーマが選択されませんでした。終了します。")
            return
    logger.info("確定テーマ: %s", theme)
    if interactive and input(f"このテーマで進めますか？ [{theme}] (Y/n) > ").strip().lower() == "n":
        theme = input("テーマを入力 > ").strip() or theme

    # --- ステップ2: リサーチ ---
    research = step2_researcher.research(theme)
    artifacts.update(research)

    # --- ステップ3: 台本 ---
    scripts = step3_script_writer.write_scripts(
        theme, research["markdown_path"], research["citations_path"]
    )
    artifacts.update(scripts)

    # --- ステップ4a: 記事 ---
    article = step4_article_builder.build_article(theme, scripts["article_script"])
    artifacts.update(article)

    # --- ステップ4b: スライド ---
    slides = step4_slide_builder.build_slides(
        theme, scripts["youtube_script"], scripts["shorts_script"]
    )
    artifacts.update(slides)

    # --- ステップ5: 監修パッケージ ---
    review = step5_review_kit_builder.build_review_kit(theme, artifacts)

    _print_summary(theme, artifacts, review)


def run_single_step(step: int, theme: str | None, input_path: str | None) -> None:
    """特定ステップだけを実行する。"""
    from src import (
        step1_theme_finder,
        step2_researcher,
        step3_script_writer,
        step4_article_builder,
        step4_slide_builder,
    )

    if step == 1:
        print(step1_theme_finder.find_themes(auto=True))
    elif step == 2:
        if not theme:
            logger.error("--step 2 には --theme が必要です。")
            return
        print(step2_researcher.research(theme))
    elif step == 3:
        # input は research markdown を想定。citations は同名 _citations.json を探す
        if not (theme and input_path):
            logger.error("--step 3 には --theme と --input(research.md) が必要です。")
            return
        cit = str(Path(input_path).with_name(Path(input_path).stem + "_citations.json"))
        print(step3_script_writer.write_scripts(theme, input_path, cit))
    elif step == 4:
        if not (theme and input_path):
            logger.error("--step 4 には --theme と --input(article台本) が必要です。")
            return
        print(step4_article_builder.build_article(theme, input_path))
    else:
        logger.error("ステップ %s は単独実行に対応していません（1〜4）。", step)


def run_review_only(theme: str) -> None:
    """既存成果物から監修パッケージのみ再生成する。

    output/ 内の最新ファイルをテーマ名から推測して収集する。
    """
    from src import step5_review_kit_builder
    from src.utils.common import OUTPUT_DIR, slugify

    slug = slugify(theme)

    def _latest(folder: str, pattern: str) -> str:
        files = sorted((OUTPUT_DIR / folder).glob(f"{slug}_*{pattern}"))
        return str(files[-1]) if files else ""

    artifacts = {
        "article_md": _latest("articles", ".md"),
        "youtube_script": _latest("scripts", "_youtube.md"),
        "shorts_script": _latest("scripts", "_shorts.md"),
        "citations_path": _latest("research", "_citations.json"),
    }
    logger.info("--review-only: 収集した成果物 %s", artifacts)
    review = step5_review_kit_builder.build_review_kit(theme, artifacts)
    print("\n📋 監修パッケージを再生成しました:")
    print(f"   {review['review_xlsx']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="小児科コンテンツ自動生成システム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--theme", type=str, help="テーマを指定")
    parser.add_argument("--interactive", action="store_true", help="各ステップで確認")
    parser.add_argument("--auto", action="store_true", help="テーマ自動選択（デフォルト）")
    parser.add_argument("--step", type=int, help="特定ステップだけ実行（1〜4）")
    parser.add_argument("--input", type=str, help="ステップ単独実行時の入力ファイル")
    parser.add_argument("--review-only", type=str, metavar="THEME",
                        help="既存成果物から監修パッケージのみ再生成")
    parser.add_argument("--revise", type=str, metavar="REVIEW_XLSX",
                        help="監修Excelの修正指示を成果物へ自動反映")
    args = parser.parse_args()

    try:
        if args.revise:
            from src import step6_reviser
            step6_reviser.revise(args.revise)
        elif args.review_only:
            run_review_only(args.review_only)
        elif args.step:
            run_single_step(args.step, args.theme, args.input)
        else:
            run_full_pipeline(args.theme, args.interactive, args.auto)
    except KeyboardInterrupt:
        print("\n中断しました。")
    except Exception as exc:
        logger.exception("処理中にエラーが発生しました: %s", exc)
        print(f"\n❌ エラー: {exc}\n  詳細は logs/ のログを確認してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
