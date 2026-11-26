"""APIキーが無いときの簡易分析（キーワード集約 + 辞書ベース感情分析）。

精度は Claude による分析に劣るが、APIキー無しでもサイト全体を動かして確認できる。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from ..models import Post
from .sentiment import reaction_items, summarize_labels

STOP = {"ポケカ", "ポケモン", "ポケモンカード", "カード", "パック", "ボックス", "ツイート", "コメント",
        "pokemon", "tcg", "ptcg", "card", "cards", "the", "and", "this", "that", "with", "for", "just",
        "pack", "packs", "box", "pokemontcg", "psa", "sir", "what", "from", "have", "got", "today", "your", "are", "was", "pull"}
TERM_RE = re.compile(r"[ァ-ヴー]{3,}(?:ex|EX|V|VSTAR|VMAX)?|[A-Z][a-zA-Z]+(?: ex)?|[一-龥]{2,}[ァ-ヴー]*")

POS = ["最高", "神", "嬉しい", "うれしい", "当たった", "欲しい", "かっこいい", "可愛い", "かわいい", "楽しみ", "おめでとう",
       "すごい", "ありがたい", "助かる", "良い", "いい", "好き", "感動", "love", "amazing", "awesome", "great",
       "beautiful", "congrats", "hyped", "excited", "insane pull", "nice", "gorgeous", "finally", "best"]
NEG = ["転売", "高すぎ", "買えない", "最悪", "ひどい", "酷い", "残念", "微妙", "偽物", "詐欺", "怒", "不満", "落選",
       "売り切れ", "やめて", "おかしい", "ふざけ", "scalper", "scalpers", "overpriced", "fake", "scam", "worst",
       "disappointed", "ridiculous", "sold out", "terrible", "awful", "greedy", "hate", "sucks"]


def terms(text: str) -> list[str]:
    out = []
    for m in TERM_RE.findall(text):
        t = m.strip()
        if t.lower() not in STOP and t not in STOP and len(t) >= 2:
            out.append(t)
    return out


def extract_topics(posts: list[Post], previous: list[dict]) -> list[dict]:
    df = Counter()
    post_terms = {}
    for p in posts:
        ts = set(terms(p.text))
        post_terms[p.id] = ts
        df.update(ts)
    groups: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        cands = [t for t in post_terms[p.id] if df[t] >= 2]
        if cands:
            groups[max(cands, key=lambda t: (df[t], len(t)))].append(p)
    prev_by_title = {t.get("_term"): t["topic_key"] for t in previous}
    topics = []
    for term, members in groups.items():
        members.sort(key=lambda p: p.likes + p.comments_count * 2, reverse=True)
        lead = " ".join(members[0].text.split())
        topics.append({
            "topic_key": prev_by_title.get(term) or "kw-" + re.sub(r"\W+", "-", term.lower()),
            "_term": term,
            "title": f"「{term}」が話題",
            "summary": f"{len(members)}件の投稿で言及。代表的な投稿: {lead[:120]}",
            "key_points": list(dict.fromkeys(" ".join(m.text.split())[:60] for m in members))[:3],
            "category": "その他",
            "cards": [term],
            "post_ids": [m.id for m in members],
        })
    return topics


def classify(text: str) -> str:
    t = text.lower()
    p = sum(w in t for w in POS)
    n = sum(w in t for w in NEG)
    return "positive" if p > n else "negative" if n > p else "neutral"


def analyze_sentiment(topic: dict, topic_posts: list[Post]) -> dict:
    items = reaction_items(topic_posts, 200)
    labels = {i[0]: classify(i[1]) for i in items}
    likes = {i[0]: i[2] for i in items}
    pos = list(dict.fromkeys(i[1][:60] for i in items if labels[i[0]] == "positive"))[:3]
    neg = list(dict.fromkeys(i[1][:60] for i in items if labels[i[0]] == "negative"))[:3]
    return summarize_labels(labels, likes, "（簡易分析）辞書ベースで判定しています。APIキー設定でAI要約になります。", pos, neg)
