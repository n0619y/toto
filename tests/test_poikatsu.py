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
