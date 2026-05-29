"""出典（引用）を構造化して保持・保存するモジュール。

すべての医学的主張に対し、以下の情報を1レコードとして管理します:
  - claim_id:   主張ID（例: C01, C02 ...）
  - claim:      主張文
  - url:        出典URL
  - org:        機関名
  - confidence: 信頼度 A/B/C
  - guideline_year: ガイドライン年度（分かる場合）
  - accessed:   アクセス日（YYYY-MM-DD）

step2 で生成し JSON に保存、step3〜step5 で読み込んで利用します。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from .common import today_iso
from .medical_sources import classify_source


@dataclass
class Citation:
    """1件の主張と、その出典をまとめたデータ構造。"""

    claim_id: str
    claim: str
    url: str = ""
    org: str = ""
    confidence: str = "C"
    guideline_year: str = ""
    accessed: str = field(default_factory=today_iso)

    def __post_init__(self) -> None:
        # 機関名・信頼度が未設定ならURLから自動判定
        if self.url and (not self.org or not self.confidence):
            org, rank = classify_source(self.url)
            self.org = self.org or org
            self.confidence = self.confidence or rank


class CitationTracker:
    """Citation のコレクションを管理し、JSONとして読み書きする。"""

    def __init__(self) -> None:
        self._items: List[Citation] = []
        self._counter = 0

    def add(
        self,
        claim: str,
        url: str = "",
        org: str = "",
        confidence: str = "",
        guideline_year: str = "",
        claim_id: Optional[str] = None,
    ) -> Citation:
        """主張を1件追加し、Citation を返す。claim_id 未指定なら自動採番(C01...)。"""
        if claim_id is None:
            self._counter += 1
            claim_id = f"C{self._counter:02d}"
        else:
            # 既存IDの最大値にカウンタを合わせる
            num = "".join(ch for ch in claim_id if ch.isdigit())
            if num.isdigit():
                self._counter = max(self._counter, int(num))

        # URLから機関・信頼度を補完
        auto_org, auto_rank = classify_source(url) if url else ("その他", "C")
        cit = Citation(
            claim_id=claim_id,
            claim=claim,
            url=url,
            org=org or auto_org,
            confidence=confidence or auto_rank,
            guideline_year=guideline_year,
        )
        self._items.append(cit)
        return cit

    @property
    def items(self) -> List[Citation]:
        return self._items

    def __len__(self) -> int:
        return len(self._items)

    def to_dict_list(self) -> List[dict]:
        return [asdict(c) for c in self._items]

    def save(self, path: Path) -> Path:
        """JSONファイルとして保存する。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict_list(), f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path: Path) -> "CitationTracker":
        """JSONファイルから読み込む。"""
        tracker = cls()
        if not Path(path).exists():
            return tracker
        with Path(path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        for rec in data:
            tracker._items.append(Citation(**rec))
        tracker._counter = len(tracker._items)
        return tracker

    def confidence_breakdown(self) -> dict:
        """信頼度ランクごとの件数を返す（例: {"A": 5, "B": 2, "C": 1}）。"""
        out = {"A": 0, "B": 0, "C": 0}
        for c in self._items:
            out[c.confidence] = out.get(c.confidence, 0) + 1
        return out

    def org_category_breakdown(self) -> dict:
        """出典機関のカテゴリー別件数（学会／公的機関／海外ガイドライン／その他）。"""
        from .medical_sources import source_category

        out = {"学会": 0, "公的機関": 0, "海外ガイドライン": 0, "その他": 0}
        for c in self._items:
            cat = source_category(c.org)
            out[cat] = out.get(cat, 0) + 1
        return out
