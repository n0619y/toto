"""共通ユーティリティ。

設定ファイルの読み込み、ロガーの初期化、出力ディレクトリの解決、
日本語テーマ名のスラッグ化など、各ステップから共通で使う関数をまとめています。
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

# プロジェクトルート（このファイルから2階層上 = リポジトリ直下）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"


@lru_cache(maxsize=None)
def load_settings() -> Dict[str, Any]:
    """config/settings.yaml を読み込んで辞書で返す（結果はキャッシュ）。"""
    path = CONFIG_DIR / "settings.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"設定ファイルが見つかりません: {path}\n"
            "config/settings.yaml が存在するか確認してください。"
        )
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=None)
def load_review_checklist() -> Dict[str, Any]:
    """config/review_checklist.yaml を読み込んで辞書で返す。"""
    path = CONFIG_DIR / "review_checklist.yaml"
    if not path.exists():
        raise FileNotFoundError(f"チェックリスト設定が見つかりません: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def reviewer_display() -> str:
    """監修者表記文字列（例: 「監修: toto先生（小児科医）」）を返す。"""
    return load_settings()["reviewer"]["display"]


def reviewer_name() -> str:
    """監修者名（例: toto先生）を返す。"""
    return load_settings()["reviewer"]["name"]


def reviewer_title() -> str:
    """監修者の肩書き（例: 小児科医）を返す。"""
    return load_settings()["reviewer"]["title"]


# 全成果物末尾に挿入する免責文（YMYL配慮）
DISCLAIMER_TEXT = (
    "本コンテンツは一般的情報提供です。診断・治療は必ず医療機関にご相談ください。"
)


def get_logger(name: str = "pediatric") -> logging.Logger:
    """logs/YYYYMMDD.log とコンソールの両方に出力するロガーを返す。"""
    logger = logging.getLogger(name)
    if logger.handlers:  # 既に初期化済みなら使い回す
        return logger

    logger.setLevel(logging.INFO)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"{datetime.now():%Y%m%d}.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stream_handler)

    return logger


def slugify(text: str, max_len: int = 40) -> str:
    """テーマ名をファイル名に使える安全な文字列へ変換する。

    日本語はそのまま残し（ファイル名に使える）、空白・記号をアンダースコアに置換。
    OSによって扱えない文字だけを除去する。
    """
    text = unicodedata.normalize("NFKC", text).strip()
    # ファイル名に使えない文字を除去
    text = re.sub(r'[\\/:*?"<>|\s]+', "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_len] if text else "untitled"


def today_str() -> str:
    """YYYYMMDD 形式の今日の日付文字列。"""
    return f"{datetime.now():%Y%m%d}"


def today_iso() -> str:
    """YYYY-MM-DD 形式の今日の日付文字列（アクセス日などに使用）。"""
    return f"{datetime.now():%Y-%m-%d}"


def ensure_dir(path: Path) -> Path:
    """ディレクトリが無ければ作成し、そのパスを返す。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def count_chars(text: str) -> int:
    """日本語文字数カウント（空白・改行を除いた文字数）。"""
    return len(re.sub(r"\s", "", text or ""))
