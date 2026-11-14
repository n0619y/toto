"""収集データの共通モデル。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Comment:
    id: str
    author: str
    text: str
    likes: int = 0
    created_at: str = ""


@dataclass
class Post:
    id: str                 # "<source>:<元ID>"
    source: str             # x / threads / instagram / reddit
    region: str             # ja（国内） / global（海外）
    author: str
    text: str
    url: str
    created_at: str         # ISO8601
    likes: int = 0
    comments_count: int = 0
    shares: int = 0
    views: int = 0
    lang: str = ""
    comments: list[Comment] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def guess_region(text: str) -> str:
    """ひらがな・カタカナが含まれていれば国内、それ以外は海外とみなす。"""
    for ch in text:
        if "぀" <= ch <= "ヿ":
            return "ja"
    return "global"
