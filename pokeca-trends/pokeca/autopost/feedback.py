"""投稿の反応を取得し、成績（reward）を計算して、次の投稿に効く「プレイブック」を更新する。

reward の考え方:
- 反応スコア = いいね + 2×返信 + 3×リポスト + 3×引用 + ブックマーク
- 表示回数が取れる場合は「反応率（反応スコア÷表示回数）」で評価（フォロワー増減の影響を減らす）
- 評価時点を24時間にそろえる（未満なら経過時間で補正）
- 返信が否定的なほど減点（炎上で伸びた投稿を「成功」と学習しないため）
- 最後に同じ媒体の自分の投稿の中での順位（0〜1）に変換して型どうしを比較
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .. import db
from ..analysis import llm, sentiment
from ..config import get_logger, settings
from ..models import Post
from .bandit import stats
from .publisher import PUBLISHERS
from .schemas import Playbook

log = get_logger()


def raw_score(m: dict, age_h: float, eval_h: float) -> float:
    s = m.get("likes", 0) + 2 * m.get("replies", 0) + 3 * m.get("reposts", 0) + 3 * m.get("quotes", 0) + m.get("bookmarks", 0)
    if m.get("views"):
        s = s / m["views"] * 1000  # 1000表示あたりの反応
    elif age_h < eval_h:
        s *= math.sqrt(eval_h / max(age_h, 1))
    return s


def age_hours(created_at: str, now: datetime) -> float:
    return (now - datetime.fromisoformat(created_at)).total_seconds() / 3600


def collect(now: datetime | None = None, use_ai: bool = True) -> int:
    """投稿済みの自分の投稿の数値・返信を取得し、reward を更新する。"""
    now = now or datetime.now(timezone.utc)
    fcfg = settings()["autopost"]["feedback"]
    updated = 0
    with db.connect() as conn:
        posts = db.own_posts(conn, "status='posted'")
    for name, cls in PUBLISHERS.items():
        pub = cls()
        targets = [p for p in posts if p["platform"] == name
                   and fcfg["min_age_hours"] <= age_hours(p["created_at"], now) <= fcfg["max_age_days"] * 24
                   # 評価時点(24h)を過ぎて一度測ったものは確定扱いで取り直さない
                   and not (p["metrics_at"] and age_hours(p["created_at"], datetime.fromisoformat(p["metrics_at"])) >= fcfg["eval_age_hours"])]
        if not targets or not pub.ready():
            continue
        try:
            metrics = pub.metrics([p["platform_id"] for p in targets])
        except Exception as exc:
            log.error("[%s] 反応の取得に失敗: %s", name, exc)
            continue
        with db.connect() as conn:
            for p in targets:
                m = metrics.get(p["platform_id"])
                if m is None:
                    continue
                senti = p.get("reply_sentiment")
                if m.get("replies"):
                    try:
                        cmts = pub.replies(p["platform_id"])
                        fake = Post(id=p["platform_id"], source=name, region="ja", author="", text=p["text"], url="", created_at="", comments=cmts)
                        topic = {"title": p["topic_title"] or "", "summary": p["text"]}
                        from ..analysis import offline
                        senti = sentiment.analyze(topic, [fake]) if use_ai else offline.analyze_sentiment(topic, [fake])
                    except Exception as exc:
                        log.warning("[%s] 返信の分析に失敗: %s", name, exc)
                db.update_own_post(conn, p["id"], metrics=m, metrics_at=now.isoformat(), reply_sentiment=senti)
                updated += 1
    rescore()
    log.info("フィードバック: %d 件の反応を更新", updated)
    return updated


def rescore() -> None:
    """媒体ごとに順位(0〜1)へ変換して reward を付け直す。"""
    eval_h = settings()["autopost"]["feedback"]["eval_age_hours"]
    with db.connect() as conn:
        posts = [p for p in db.own_posts(conn, "status='posted' AND metrics IS NOT NULL", limit=2000)]
        by_pf: dict[str, list[tuple[dict, float]]] = {}
        for p in posts:
            age = age_hours(p["created_at"], datetime.fromisoformat(p["metrics_at"]))
            s = raw_score(p["metrics"], age, eval_h)
            senti = (p.get("reply_sentiment") or {}).get("score")
            if senti is not None and (p.get("reply_sentiment") or {}).get("analyzed", 0) >= 3:
                s *= 1 + min(0, senti) / 200  # 否定的な返信が多いほど最大50%減点
            by_pf.setdefault(p["platform"], []).append((p, s))
        for items in by_pf.values():
            ordered = sorted(s for _, s in items)
            n = len(ordered)
            for p, s in items:
                rank = sum(x < s for x in ordered) + 0.5 * (sum(x == s for x in ordered) - 1)
                db.update_own_post(conn, p["id"], reward=round(rank / (n - 1), 3) if n > 1 else 0.5)


RETRO = """あなたはSNS運用の改善担当です。ポケカ情報アカウントの過去の投稿と成績を見て、次の投稿で何を変えるべきかをまとめます。
- 成績は同じ媒体内の相対評価（reward 0〜1）。件数が少ない型の結論は「仮説」と明記する
- 否定的な返信が多かった投稿の特徴は dont に入れる
- 事実の捏造・煽り・体験談の偽装で伸ばす提案はしない"""


def update_playbook(date: str, use_ai: bool = True) -> dict | None:
    with db.connect() as conn:
        ev = db.own_posts(conn, "reward IS NOT NULL", limit=300)
        prev = db.latest_report(conn, "playbook")
    if len(ev) < 3:
        return prev
    st = stats(ev)
    ranked = sorted(ev, key=lambda p: p["reward"], reverse=True)
    fmt = lambda p: (f"- [{p['platform']}/{p['archetype']}] reward={p['reward']} 数値={p['metrics']} "
                     f"返信の反応={(p.get('reply_sentiment') or {}).get('overall', '-')} 本文: {' '.join(p['text'].split())[:140]}")
    if use_ai:
        prompt = ("## 型ごとの成績\n" + "\n".join(f"- {k}: 平均{v['mean']:.2f}（{v['n']}件）" for k, v in st.items()) +
                  "\n\n## 成績上位\n" + "\n".join(map(fmt, ranked[:8])) + "\n\n## 成績下位\n" + "\n".join(map(fmt, ranked[-8:])) +
                  f"\n\n## 前回のプレイブック\n{prev}")
        pb = llm.parse(Playbook, system=RETRO, content=prompt, effort="medium").model_dump()
    else:
        best = max(st.items(), key=lambda kv: kv[1]["mean"])
        worst = min(st.items(), key=lambda kv: kv[1]["mean"])
        pb = {"insights": [f"{k}: 平均{v['mean']:.2f}（{v['n']}件）" for k, v in st.items()],
              "do": [f"{best[0]} 型を増やす"], "dont": [f"{worst[0]} 型は書き方を見直す"]}
    pb["archetype_stats"] = st
    pb["evaluated"] = len(ev)
    with db.connect() as conn:
        db.save_report(conn, date, "playbook", pb)
    return pb
