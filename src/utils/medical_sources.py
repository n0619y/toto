"""信頼できる医学情報源のホワイトリストと信頼度判定。

リサーチ時に、ここに定義したドメインを優先的に採用します。
各ドメインには機関名と信頼度ランク（A〜C）を割り当てています。
  A: 国内の学会・公的機関、主要国際機関のガイドライン
  B: それに準じる公的・専門機関
  C: 一般的な情報源（ホワイトリスト外）
"""

from __future__ import annotations

from typing import Dict, Tuple
from urllib.parse import urlparse

# ドメイン -> (機関名, 信頼度ランク)
WHITELIST: Dict[str, Tuple[str, str]] = {
    # --- 国内：学会・医会 ---
    "jpeds.or.jp": ("日本小児科学会", "A"),
    "jpa-web.org": ("日本小児科医会", "A"),
    # --- 国内：公的機関 ---
    "mhlw.go.jp": ("厚生労働省", "A"),
    "ncchd.go.jp": ("国立成育医療研究センター", "A"),
    "niid.go.jp": ("国立感染症研究所", "A"),
    "mext.go.jp": ("文部科学省", "B"),
    "cao.go.jp": ("内閣府", "B"),
    # --- 海外：主要機関・ガイドライン ---
    "aap.org": ("American Academy of Pediatrics (AAP)", "A"),
    "healthychildren.org": ("AAP (HealthyChildren)", "A"),
    "who.int": ("World Health Organization (WHO)", "A"),
    "cdc.gov": ("Centers for Disease Control (CDC)", "A"),
    "nih.gov": ("National Institutes of Health (NIH)", "A"),
    "ncbi.nlm.nih.gov": ("PubMed / NCBI", "A"),
    "uptodate.com": ("UpToDate", "B"),
    "nice.org.uk": ("NICE (UK)", "A"),
}

# 検索の優先ドメイン（site: 絞り込みなどに利用）
PRIORITY_DOMAINS = list(WHITELIST.keys())


def classify_source(url: str) -> Tuple[str, str]:
    """URLから (機関名, 信頼度ランク) を返す。

    ホワイトリストに一致しない場合は ("その他", "C") を返す。
    サブドメインにも対応する（例: www.mhlw.go.jp -> mhlw.go.jp）。
    """
    if not url:
        return ("その他", "C")
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ("その他", "C")
    host = host.split(":")[0]  # ポート除去

    for domain, (org, rank) in WHITELIST.items():
        if host == domain or host.endswith("." + domain):
            return (org, rank)
    return ("その他", "C")


def source_category(rank_or_org: str) -> str:
    """信頼度や機関名から、サマリー集計用のカテゴリーを返す。"""
    org = rank_or_org
    if org in ("日本小児科学会", "日本小児科医会"):
        return "学会"
    if org in ("厚生労働省", "国立成育医療研究センター", "国立感染症研究所",
               "文部科学省", "内閣府"):
        return "公的機関"
    if org in ("American Academy of Pediatrics (AAP)", "AAP (HealthyChildren)",
               "World Health Organization (WHO)", "Centers for Disease Control (CDC)",
               "National Institutes of Health (NIH)", "PubMed / NCBI", "UpToDate",
               "NICE (UK)"):
        return "海外ガイドライン"
    return "その他"
