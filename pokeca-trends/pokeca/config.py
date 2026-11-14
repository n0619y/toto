"""設定・パス・ロガーの共通処理。"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def settings() -> dict:
    with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def shops() -> list[dict]:
    path = ROOT / settings()["market"]["shops_file"]
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("shops") or []


def env(name: str) -> str | None:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else None


def get_logger() -> logging.Logger:
    logger = logging.getLogger("pokeca")
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger
