from datetime import date

from poikatsu.agents import CEO, Compliance, DayContext
from poikatsu.llm import LLM
from poikatsu.models import AUTO, HOLD, HUMAN, Opportunity
from poikatsu.store import Store

ALLOWED = {"automation": "allowed", "tos_checked": "確認済み"}


def judge(task_type, site):
    return Compliance.judge(Opportunity("s", "t", task_type=task_type), site)[0]


def test_medical_portal_is_never_automated():
    site = {"category": "medical_portal", **ALLOWED}
    for t in ("login", "click", "survey", "read", "video"):
        assert judge(t, site) == HUMAN


def test_attention_tasks_are_never_automated():
    for t in ("survey", "quiz", "read", "video", "unknown"):
        assert judge(t, ALLOWED) == HUMAN


def test_auto_requires_both_flags():
    assert judge("login", ALLOWED) == AUTO
    assert judge("login", {"automation": "allowed"}) == HUMAN
    assert judge("login", {}) == HUMAN


def test_money_goes_to_hold():
    assert judge("signup", ALLOWED) == HOLD
    assert judge("purchase", {}) == HOLD


def make_ctx(budget=5):
    cfg = {"daily_budget_minutes": budget, "sites": {}}
    return DayContext(date(2026, 11, 27), cfg, Store(":memory:"), LLM(enabled=False), demo=True)


def test_demo_day_respects_budget_and_gates():
    ctx = make_ctx(budget=5)
    opps, summary = CEO().run_day(ctx)
    route = [o for o in opps if o.selected and o.verdict == HUMAN]
    assert route and sum(o.minutes for o in route) <= 5
    assert summary["hold"] == 1                       # クレジットカード発行
    assert not ctx.executed                           # 実行手段も許可設定も無い
    assert all(o.verdict in (HUMAN, HOLD) for o in opps)


def test_done_items_are_not_offered_again():
    ctx = make_ctx()
    opps, _ = CEO().run_day(ctx)
    target = next(o for o in opps if o.selected)
    assert ctx.store.mark_done([target.id], "2026-11-27") == 1
    again, _ = CEO().run_day(ctx)
    assert target.id not in {o.id for o in again}
    assert ctx.store.month_total("2026-11")[0] == 1


def test_grant_mail_closes_matching_offer_once():
    ctx = make_ctx(budget=30)
    opps, _ = CEO().run_day(ctx)
    survey = next(o for o in opps if o.task_type == "survey")
    assert ctx.store.record_grant("2026-11-28", survey.site, "300ポイント付与のお知らせ", 300)
    assert survey.id in ctx.store.done_ids()
    assert not ctx.store.record_grant("2026-11-28", survey.site, "300ポイント付与のお知らせ", 300)
    assert ctx.store.month_grants("2026-11") == (1, 300)


def test_low_yield_items_are_cut():
    ctx = make_ctx(budget=30)
    ctx.cfg["min_yen_per_minute"] = 3
    opps, _ = CEO().run_day(ctx)
    click = next(o for o in opps if o.task_type == "click")   # 1円/0.5分 = 2円/分
    assert not click.selected


def test_grant_subject_detection():
    from poikatsu.sources import GRANT_RE
    assert GRANT_RE.search("【m3.com】ポイント付与のお知らせ")
    assert GRANT_RE.search("300ポイントを進呈しました")
    assert not GRANT_RE.search("アンケートご協力のお願い（謝礼300ポイント）")
