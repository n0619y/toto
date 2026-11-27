"""共通データモデル。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# 法務部の判定
AUTO = "AUTO"    # 規約上、自動実行してよい（サイト側が明示的に許可している場合のみ）
HUMAN = "HUMAN"  # 本人が行う（システムは最短ルートを用意するだけ）
HOLD = "HOLD"    # お金・契約が絡むため、日次ルートには入れず本人判断に回す

TASK_TYPES = (
    "login", "click", "read", "video", "survey", "quiz",
    "entry", "signup", "purchase", "unknown",
)


@dataclass
class Opportunity:
    """ポイント獲得機会 1 件。"""

    site: str
    title: str
    url: str = ""
    task_type: str = "unknown"
    points: float = 0.0       # サイト内ポイント（不明なら 0）
    minutes: float = 0.0      # 所要時間の見積り（0 なら分析部が補完）
    deadline: str = ""        # YYYY-MM-DD（不明なら空）
    source: str = ""          # routine / mail / feed / demo
    day: str = ""             # ルーティンは日付ごとに別案件として扱う
    # 以降は各部署が書き込む
    verdict: str = ""
    reason: str = ""
    value_yen: float = 0.0
    score: float = 0.0
    selected: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        key = f"{self.site}|{self.title}|{self.url}|{self.day}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
