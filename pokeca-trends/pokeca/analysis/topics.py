"""投稿群を話題（トピック）にまとめ、要約する。"""
from __future__ import annotations

import math

from ..config import get_logger, settings
from ..models import Post
from . import llm
from .schemas import TopicList

log = get_logger()

SYSTEM = """あなたはポケモンカードゲーム（ポケカ）専門のSNSトレンド編集者です。
国内（日本語）と海外（英語など）のSNS投稿を読み、その日の「話題」ごとにまとめます。

ルール:
- 同じ出来事・同じカード・同じ商品についての投稿は1つの話題にまとめる。国内と海外で同じ話題なら1つに統合する
- 個人の雑談・宣伝・ポケカと無関係な投稿はどの話題にも入れなくてよい
- 投稿が1件しかなくても、反応が大きければ独立した話題にしてよい
- 見出し・要約は日本語。海外の固有名詞は日本語の正式名称がわかればそれを使う
- 推測で事実を足さない。投稿に書かれている範囲で要約する
- 個人を特定・中傷する内容は書かない
- 前日の話題IDの一覧が与えられたら、同じ話題には同じ topic_key を使う"""


def engagement(p: Post) -> float:
    w = settings()["ranking"]
    return (w["weight_likes"] * math.log1p(p.likes) + w["weight_comments"] * math.log1p(p.comments_count)
            + w["weight_shares"] * math.log1p(p.shares))


def extract_topics(posts: list[Post], previous_keys: list[dict]) -> list[dict]:
    """戻り値: [{topic_key,title,summary,key_points,category,cards,post_ids(実ID)}]"""
    cfg = settings()["claude"]
    picked = sorted(posts, key=engagement, reverse=True)[: cfg["max_posts_for_topics"]]
    idmap = {f"p{i+1}": p for i, p in enumerate(picked)}

    lines = []
    for sid, p in idmap.items():
        text = " ".join(p.text.split())[:400]
        lines.append(f"[{sid}] ({p.source}/{'国内' if p.region == 'ja' else '海外'} "
                     f"いいね{p.likes} 返信{p.comments_count} 拡散{p.shares}) {text}")
    prev = "\n".join(f"- {t['topic_key']}: {t['title']}" for t in previous_keys) or "（なし）"
    prompt = (f"## 前日の話題ID\n{prev}\n\n## 今日の投稿（{len(lines)}件）\n" + "\n".join(lines)
              + "\n\n上の投稿を話題ごとにまとめてください。反応の大きい話題から順に、最大40件まで。")

    result = llm.parse(TopicList, system=SYSTEM, content=prompt, effort=cfg["topic_effort"])
    topics = []
    for t in result.topics:
        members = [idmap[i].id for i in t.post_ids if i in idmap]
        if not members:
            continue
        d = t.model_dump()
        d["post_ids"] = members
        topics.append(d)
    log.info("トピック抽出: %d 件の投稿 → %d 話題", len(picked), len(topics))
    return topics
