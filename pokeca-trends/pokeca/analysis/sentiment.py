"""コメント欄（返信・コメント）の反応を 好意的/否定的/中立 に分類する。"""
from __future__ import annotations

from ..config import get_logger, settings
from ..models import Post
from . import llm
from .schemas import SentimentResult

log = get_logger()

SYSTEM = """あなたはポケカ（ポケモンカード）コミュニティの反応を分析するアナリストです。
ある話題について寄せられたコメント・投稿を1件ずつ読み、話題に対する書き手の感情を判定します。

判定基準:
- positive（好意的）: 喜び・期待・称賛・賛成・「欲しい」「最高」「当たった」など前向きな反応
- negative（否定的）: 不満・怒り・失望・批判・不安・「転売」「高すぎ」「買えない」など後ろ向きな反応
- neutral（中立）: 質問・事実の共有・感情が読み取れないもの
- 皮肉（「さすが転売ヤーの皆さん」等）は文字どおりではなく意図で判定する
- 多言語に対応し、要約は日本語で書く
- 意見の代表例は個人が特定できないよう言い換えて要約する"""


def reaction_items(topic_posts: list[Post], limit: int) -> list[tuple[str, str, int]]:
    """(id, text, likes)。コメントを優先し、足りなければ投稿本文も反応として使う。"""
    items = []
    for p in topic_posts:
        for c in p.comments:
            items.append((c.id, c.text, c.likes))
    items.sort(key=lambda x: x[2], reverse=True)
    if len(items) < 15:  # Instagram などコメント本文が取れない媒体は投稿自体を反応として扱う
        items += [(p.id, p.text, p.likes) for p in topic_posts]
    return items[:limit]


def analyze(topic: dict, topic_posts: list[Post]) -> dict:
    cfg = settings()["claude"]
    items = reaction_items(topic_posts, cfg["max_comments_per_topic"])
    if not items:
        return empty()
    short = {f"c{i+1}": it for i, it in enumerate(items)}
    body = "\n".join(f"[{k}] (いいね{v[2]}) {' '.join(v[1].split())[:300]}" for k, v in short.items())
    prompt = f"## 話題\n{topic['title']}\n{topic['summary']}\n\n## コメント（{len(short)}件）\n{body}"
    r = llm.parse(SentimentResult, system=SYSTEM, content=prompt,
                  model=cfg["light_model"], effort=cfg["sentiment_effort"])
    labels = {x.id: x.label for x in r.labels if x.id in short}
    return summarize_labels(labels, {k: v[2] for k, v in short.items()},
                            r.reaction_summary, r.positive_points, r.negative_points)


def summarize_labels(labels: dict[str, str], likes: dict[str, int], summary: str,
                     pos_points: list[str], neg_points: list[str]) -> dict:
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    weighted = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    for k, lab in labels.items():
        counts[lab] += 1
        weighted[lab] += 1 + likes.get(k, 0) ** 0.5  # いいねの多いコメントほど重く（平方根で緩和）
    total = sum(counts.values()) or 1
    wtotal = sum(weighted.values()) or 1
    ratio = {k: round(v / total * 100) for k, v in counts.items()}
    pos, neg = weighted["positive"] / wtotal, weighted["negative"] / wtotal
    score = round((pos - neg) * 100)  # -100（否定的）〜 +100（好意的）
    if score >= 25:
        overall = "好意的"
    elif score <= -25:
        overall = "否定的"
    elif pos + neg > 0.5:
        overall = "賛否両論"
    else:
        overall = "中立"
    return {"counts": counts, "ratio": ratio, "score": score, "overall": overall, "analyzed": sum(counts.values()),
            "reaction_summary": summary, "positive_points": pos_points, "negative_points": neg_points}


def empty() -> dict:
    return summarize_labels({}, {}, "コメントが取得できませんでした。", [], [])
