"""投稿前の機械的チェック（文字数・盗用・禁止表現）。Claude の審査とは別に必ず通す。"""
from __future__ import annotations

import re
import unicodedata

# 投資助言・煽り・なりすまし体験談・他者への絡み を機械的に弾く
BANNED = [
    (r"@\w", "他アカウントへのメンションは禁止"),
    (r"絶対(に)?(上が|儲か|値上が|損しな)", "断定的な値上がり予測"),
    (r"(今が|今こそ)?買い時|今すぐ買|爆益|確実に(儲|上)", "投資の勧誘・煽り"),
    (r"(私|僕|俺|自分)が?(当て|引い|開封し|買い取)", "架空の体験談"),
    (r"(当たり|当た)ました|引きました|神引きした", "架空の体験談"),
    (r"拡散希望|RTして|リポストして|フォローして", "拡散・フォローの要求"),
]


def x_length(text: str) -> int:
    """X の重み付き文字数（CJK・全角は2、URLは23）。上限280。"""
    text = re.sub(r"https?://\S+", "x" * 23, text)
    n = 0
    for ch in text:
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") or ord(ch) > 0x2FFF else 1
    return n


def fits(platform: str, text: str) -> bool:
    return x_length(text) <= 280 if platform == "x" else len(text) <= 500


def _grams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s+|#\S+|https?://\S+", "", unicodedata.normalize("NFKC", s))
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def similarity(a: str, b: str) -> float:
    ga, gb = _grams(a), _grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))  # 短い方を基準にした重なり率（部分コピーも検出）


def max_similarity(text: str, others: list[str]) -> float:
    return max((similarity(text, o) for o in others), default=0.0)


def _plain(s: str) -> str:
    return re.sub(r"\s+|#\S+|https?://\S+", "", unicodedata.normalize("NFKC", s))


def longest_copy(text: str, others: list[str]) -> int:
    """他の文章と連続して一致する最長の文字数（丸写しの検出）。"""
    from difflib import SequenceMatcher
    a, best = _plain(text), 0
    for o in others:
        m = SequenceMatcher(None, a, _plain(o), autojunk=False).find_longest_match()
        best = max(best, m.size)
    return best


def check(platform: str, text: str, sources: list[str], own: list[str], cfg: dict, site_url: str = "") -> list[str]:
    issues = []
    if not text.strip():
        return ["空の本文"]
    if not fits(platform, text):
        issues.append(f"文字数超過（{x_length(text) if platform == 'x' else len(text)}）")
    for pat, why in BANNED:
        if re.search(pat, text):
            issues.append(why)
    for url in re.findall(r"https?://\S+", text):
        if not site_url or not url.startswith(site_url):
            issues.append("自サイト以外のURL")
    if len(re.findall(r"#\S+", text)) > cfg.get("max_hashtags", 2):
        issues.append("ハッシュタグが多すぎる")
    s_src = max_similarity(text, sources)
    copied = longest_copy(text, sources)
    if s_src >= cfg.get("max_similarity_to_source", 0.5) or copied >= cfg.get("max_copied_chars", 18):
        issues.append(f"元投稿と似すぎ（重なり{s_src:.2f}・連続一致{copied}字）")
    s_own = max_similarity(text, own)
    if s_own >= cfg.get("max_similarity_to_own", 0.6):
        issues.append(f"自分の過去投稿と似すぎ（{s_own:.2f}）")
    return issues
