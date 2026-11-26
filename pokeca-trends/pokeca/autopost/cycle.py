"""1サイクル = 収集 → 分析 → 前回までの投稿の反応を回収 → 学習 → 生成・審査 → 投稿。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import db
from ..analysis import llm
from ..config import get_logger, settings
from . import bandit, composer, feedback, style
from .publisher import PUBLISHERS

log = get_logger()


def post_cycle(date: str, now: datetime | None = None, force_offline: bool = False, simulate=None) -> list[dict]:
    """simulate: デモ用。(platform, text, archetype) -> platform_id を返す関数を渡すと実投稿の代わりに使う。"""
    cfg = settings()["autopost"]
    now = now or datetime.now(timezone.utc)
    use_ai = llm.available() and not force_offline
    live = cfg.get("enabled") or simulate is not None

    with db.connect() as conn:
        topics = db.load_topics(conn, date)
        posts = db.load_posts(conn, date)
        market = db.latest_report(conn, "market")
        playbook = db.latest_report(conn, "playbook")
        recent = db.own_posts(conn, "created_at >= ?", ((now - timedelta(days=30)).isoformat(),), limit=1000)
        evaluated = db.own_posts(conn, "reward IS NOT NULL", limit=1000)
    if not topics:
        log.warning("自動投稿: %s の話題がないためスキップ", date)
        return []

    try:
        guide = style.build(posts) if use_ai else style.offline(posts)
    except Exception as exc:
        log.error("スタイル分析に失敗（既定値で続行）: %s", exc)
        guide = style.default()
    with db.connect() as conn:
        db.save_report(conn, date, "style", guide)

    sources = [p.text for p in posts]
    own_texts = {pf: [p["text"] for p in recent if p["platform"] == pf and p["text"]
                      and p["created_at"] >= (now - timedelta(days=14)).isoformat()] for pf in cfg["platforms"]}
    cooldown = (now - timedelta(hours=cfg["same_topic_cooldown_hours"])).isoformat()
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    results = []
    for pf in cfg["platforms"]:
        pub = PUBLISHERS[pf]()
        posted_today = sum(p["platform"] == pf and p["created_at"] >= today0 and p["status"] == "posted" for p in recent)
        if live and not simulate and not pub.ready():
            log.warning("[%s] 投稿用の認証情報が未設定のためスキップ", pf)
            continue
        used_topics = {p["topic_key"] for p in recent if p["platform"] == pf and p["created_at"] >= cooldown}
        for _ in range(cfg["posts_per_cycle"]):
            if live and posted_today >= cfg["max_posts_per_day"]:
                log.info("[%s] 1日の上限に達したため投稿しません", pf)
                break
            pf_eval = [p for p in evaluated if p["platform"] == pf]
            tried: set[str] = set()
            best = arche = topic = None
            # 審査に通らなければ、別の型・別の話題で最大3回まで作り直す
            for _attempt in range(3):
                pick = None
                while len(tried) < len(cfg["archetypes"]):
                    a = bandit.choose(list(cfg["archetypes"]), pf_eval, cfg.get("exploration", 0.8), tried)
                    tried.add(a)
                    cand_topics = [t for t in topics if t["topic_key"] not in used_topics and composer.fits_archetype(a, t, market)]
                    if cand_topics:
                        pick = (a, cand_topics[0])  # 型に合う話題のうち最上位
                        break
                if not pick:
                    break
                arche, topic = pick
                try:
                    best = composer.compose(pf, topic, arche, guide, playbook, market, sources, own_texts[pf], use_ai)
                except Exception as exc:
                    log.error("[%s] 生成に失敗: %s", pf, exc)
                if best:
                    break
            if not topic:
                log.info("[%s] 投稿できる話題がありません（クールダウン中）", pf)
                break
            rec = {"platform": pf, "archetype": arche, "topic_key": topic["topic_key"], "topic_title": topic["title"],
                   "created_at": now.isoformat(), "cycle": now.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")}
            if not best:
                rec.update(status="rejected", text="", review={"issues": ["全候補が審査で不合格"]})
            else:
                rec.update(text=best["text"], review=best["review"])
                if not live:
                    rec["status"] = "dry_run"
                else:
                    try:
                        rec["platform_id"] = simulate(pf, best["text"], arche) if simulate else pub.post(best["text"])
                        rec["status"] = "posted"
                        posted_today += 1
                    except Exception as exc:
                        log.error("[%s] 投稿に失敗: %s", pf, exc)
                        rec["status"] = "failed"
                        rec["review"] = {**best["review"], "error": str(exc)[:300]}
            with db.connect() as conn:
                db.add_own_post(conn, rec)
            used_topics.add(topic["topic_key"])
            if rec.get("text"):
                own_texts[pf].append(rec["text"])
            log.info("[%s] %s（%s）: %s", pf, rec["status"], arche, (rec.get("text") or "").replace("\n", " ")[:60])
            results.append(rec)
    return results


def run(date: str, force_offline: bool = False) -> None:
    from .. import pipeline
    from ..site import builder
    use_ai = llm.available() and not force_offline
    pipeline.collect(date)
    pipeline.analyze(date, force_offline=force_offline)
    with db.connect() as conn:
        has_market = db.load_report(conn, date, "market")
    if not has_market:  # 相場は1日1回
        pipeline.market(date, force_offline=force_offline)
    feedback.collect(use_ai=use_ai)
    feedback.update_playbook(date, use_ai=use_ai)
    post_cycle(date, force_offline=force_offline)
    builder.build()
