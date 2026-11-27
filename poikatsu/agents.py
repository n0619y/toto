"""ポイ活カンパニーの各部署（エージェント）。

  社長 CEO ─┬─ リサーチ部 Scout      案件を集める
            ├─ 分析部   Analyst     種類・所要時間・価値を見積もる（AI）
            ├─ 法務部   Compliance  自動化してよいかを判定（コード固定・AIは覆せない）
            ├─ 経営企画 Strategist  時間予算の中で「今日やる案件」を決める
            ├─ 実行部   Operator    AUTO は実行、HUMAN は本人用の最短ルートに並べる
            └─ 経理部   Auditor     実績を記録し、翌日の経営企画にフィードバック
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from . import sources
from .llm import LLM
from .models import AUTO, HOLD, HUMAN, TASK_TYPES, Opportunity
from .store import Store

log = logging.getLogger("poikatsu")


@dataclass
class DayContext:
    today: date
    cfg: dict
    store: Store
    llm: LLM
    demo: bool = False
    warnings: list[str] = field(default_factory=list)
    executed: list[str] = field(default_factory=list)
    briefing: str = ""


# --------------------------------------------------------------------------- #
class Scout:
    """リサーチ部: 情報源から案件を集め、重複と完了済みを除く。"""

    def run(self, ctx: DayContext) -> list[Opportunity]:
        if ctx.demo:
            found = sources.demo(ctx.today)
        else:
            found = []
            for name, fn in (("routines", sources.from_routines),
                             ("feeds", sources.from_feeds),
                             ("mail", sources.from_mail)):
                try:
                    found += fn(ctx.cfg, ctx.today)
                except Exception as exc:  # 1つの情報源の不調で全体を止めない
                    ctx.warnings.append(f"リサーチ部: 情報源 {name} の取得に失敗 ({exc})")
        done = ctx.store.done_ids()
        today = ctx.today.isoformat()
        seen, out = set(), []
        for o in found:
            if o.id in seen or o.id in done:
                continue
            if o.deadline and o.deadline < today:
                continue
            seen.add(o.id)
            out.append(o)
        return out


# --------------------------------------------------------------------------- #
KEYWORDS = [  # 上から順に判定
    ("signup", ("カード発行", "口座開設", "申込", "申し込み", "契約", "入会", "無料登録")),
    ("purchase", ("購入", "お買い物", "ご利用で", "決済")),
    ("survey", ("アンケート", "調査", "意識調査")),
    ("quiz", ("クイズ", "問題に答え")),
    ("video", ("動画", "講演", "ウェビナー", "セミナー", "視聴")),
    ("read", ("MR君", "メッセージ", "記事", "ニュース", "読んで")),
    ("entry", ("応募", "懸賞", "プレゼント", "抽選")),
    ("click", ("クリック", "ガチャ", "くじ", "スタンプ", "ゲーム")),
    ("login", ("ログイン",)),
]
DEFAULT_MINUTES = {"login": 0.5, "click": 0.5, "read": 2, "video": 15, "survey": 5,
                   "quiz": 1, "entry": 2, "signup": 20, "purchase": 10, "unknown": 3}


class Analyst:
    """分析部: 案件の種類と所要時間を見積もる。AIが使えればAI、無ければキーワード。"""

    SYSTEM = (
        "あなたはポイ活案件の分析担当です。各案件のタイトルから種類と所要時間を見積もります。"
        f"task_type は {list(TASK_TYPES)} のいずれか。"
        'JSON配列のみを返してください: [{"i": 番号, "task_type": "...", "minutes": 数値}]'
    )

    def run(self, ctx: DayContext, opps: list[Opportunity]) -> None:
        for o in opps:
            if o.task_type not in TASK_TYPES or o.task_type == "unknown":
                o.task_type = next(
                    (t for t, words in KEYWORDS if any(w in o.title for w in words)), "unknown")
        unknown = [o for o in opps if o.task_type == "unknown" or not o.minutes]
        if unknown:
            listing = "\n".join(f"{i}. [{o.site}] {o.title}" for i, o in enumerate(unknown))
            for row in ctx.llm.ask_json(self.SYSTEM, listing) or []:
                try:
                    o = unknown[int(row["i"])]
                    if o.task_type == "unknown" and row.get("task_type") in TASK_TYPES:
                        o.task_type = row["task_type"]
                    if not o.minutes and float(row.get("minutes", 0)) > 0:
                        o.minutes = float(row["minutes"])
                except (KeyError, IndexError, ValueError, TypeError):
                    continue
        for o in opps:
            if not o.minutes:
                o.minutes = DEFAULT_MINUTES[o.task_type]
            site = ctx.cfg.get("sites", {}).get(o.site, {})
            if o.points:
                o.value_yen = o.points * float(site.get("yen_per_point", 1))
            elif o.task_type == "entry":  # 懸賞は当選確率が不明なので控えめな期待値を置く
                o.value_yen = float(ctx.cfg.get("default_entry_ev_yen", 5))


# --------------------------------------------------------------------------- #
# 本人の閲覧・回答・判断そのものが対価の前提になっている種類。
# サイト設定がどうであれ、ここは自動化しない。
PERSON_REQUIRED = {"survey", "quiz", "read", "video", "unknown"}
MONEY_INVOLVED = {"signup", "purchase"}
# 医師資格に紐づくサイト。製薬企業等が「医師本人の閲覧・意見」に対価を払う仕組みのため常に本人。
ALWAYS_HUMAN_CATEGORIES = {"medical_portal"}


class Compliance:
    """法務部: 自動化の可否を判定する。

    ルールはコードに固定してあり、AIの出力や案件の文面では変わらない。
    AUTO になるのは「サイトが規約で自動操作を明示的に許可している」と
    設定ファイルで本人が確認済み（automation: allowed + tos_checked）の場合だけ。
    """

    def run(self, ctx: DayContext, opps: list[Opportunity]) -> None:
        for o in opps:
            o.verdict, o.reason = self.judge(o, ctx.cfg.get("sites", {}).get(o.site, {}))

    @staticmethod
    def judge(o: Opportunity, site: dict) -> tuple[str, str]:
        if o.task_type in MONEY_INVOLVED:
            return HOLD, "お金・契約・個人情報の提供が絡むため本人判断"
        if site.get("category") in ALWAYS_HUMAN_CATEGORIES:
            return HUMAN, "医師本人の閲覧・回答が対価の前提（代行は規約違反・不正受給になりうる）"
        if o.task_type in PERSON_REQUIRED:
            return HUMAN, "本人が読む・答えることが対価の前提"
        if site.get("automation") == "allowed" and site.get("tos_checked"):
            return AUTO, f"規約で自動操作が許可されていることを確認済み ({site['tos_checked']})"
        return HUMAN, "規約で自動操作の許可を確認できていない"


# --------------------------------------------------------------------------- #
class Strategist:
    """経営企画部: 1日の時間予算の中で、時間あたり価値の高い順に案件を選ぶ。"""

    def run(self, ctx: DayContext, opps: list[Opportunity], site_stats: dict) -> None:
        soon = (ctx.today + timedelta(days=1)).isoformat()
        for o in opps:
            o.score = o.value_yen / max(o.minutes, 0.1)
            if o.deadline and o.deadline <= soon:
                o.score *= 1.5
                o.notes.append("締切間近")
            st = site_stats.get(o.site)
            if st and (st["offered"] or 0) >= 5:  # 経理部からのフィードバック
                rate = (st["done"] or 0) / st["offered"]
                o.score *= 0.5 + 0.5 * rate
                if rate < 0.3:
                    o.notes.append("最近あまり消化されていないサイト")
        budget = float(ctx.cfg.get("daily_budget_minutes", 15))
        for o in sorted(opps, key=lambda x: -x.score):
            if o.verdict == AUTO:
                o.selected = True
            elif o.verdict == HUMAN and o.score > 0 and o.minutes <= budget:
                o.selected = True
                budget -= o.minutes


# --------------------------------------------------------------------------- #
# サイト名 -> 実行関数。公式API等、規約で認められた手段だけをここに登録する。
EXECUTORS: dict[str, Callable[[Opportunity], str]] = {}


class Operator:
    """実行部: AUTO 案件を実行する。実行手段が無い AUTO は本人ルートに回す。"""

    def run(self, ctx: DayContext, opps: list[Opportunity]) -> None:
        for o in opps:
            if o.verdict != AUTO:
                continue
            fn = EXECUTORS.get(o.site)
            if fn is None:
                o.verdict, o.reason = HUMAN, "自動実行の手段が未登録のため本人ルートへ"
                continue
            if ctx.demo:
                ctx.executed.append(f"(デモ) {o.site}: {o.title}")
                continue
            try:
                ctx.executed.append(f"{o.site}: {o.title} → {fn(o)}")
                ctx.store.record_offers(ctx.today.isoformat(), [o])
                ctx.store.mark_done([o.id], ctx.today.isoformat())
            except Exception as exc:
                ctx.warnings.append(f"実行部: {o.site}「{o.title}」の自動実行に失敗 ({exc})")
                o.verdict, o.reason = HUMAN, "自動実行に失敗したため本人ルートへ"


# --------------------------------------------------------------------------- #
class Auditor:
    """経理部: 台帳への記録と実績集計。"""

    def feedback(self, ctx: DayContext) -> dict:
        since = (ctx.today - timedelta(days=14)).isoformat()
        return ctx.store.site_stats(since)

    def close(self, ctx: DayContext, opps: list[Opportunity]) -> dict:
        ctx.store.record_offers(ctx.today.isoformat(), opps)
        n, yen = ctx.store.month_total(ctx.today.strftime("%Y-%m"))
        return {"month_done": n, "month_yen": yen}


# --------------------------------------------------------------------------- #
class CEO:
    """社長: 各部署を順に動かし、朝の報告をまとめる。"""

    SYSTEM = (
        "あなたはポイ活カンパニーの社長です。忙しい小児科医のオーナーに、今日の方針を"
        "3文以内の日本語で簡潔に報告します。数字は与えられたものだけを使い、誇張しません。"
    )

    def run_day(self, ctx: DayContext) -> tuple[list[Opportunity], dict]:
        scout, analyst, legal = Scout(), Analyst(), Compliance()
        strategist, operator, auditor = Strategist(), Operator(), Auditor()

        opps = scout.run(ctx)
        analyst.run(ctx, opps)
        legal.run(ctx, opps)
        operator.run(ctx, opps)                       # AUTO を実行（不可なら HUMAN に戻る）
        strategist.run(ctx, opps, auditor.feedback(ctx))
        summary = auditor.close(ctx, opps)

        route = [o for o in opps if o.selected and o.verdict == HUMAN]
        summary.update(
            found=len(opps),
            route_count=len(route),
            route_minutes=sum(o.minutes for o in route),
            route_yen=sum(o.value_yen for o in route),
            hold=sum(1 for o in opps if o.verdict == HOLD),
        )
        facts = (
            f"発見 {summary['found']}件 / 今日のルート {summary['route_count']}件・"
            f"約{summary['route_minutes']:.0f}分・見込み約{summary['route_yen']:.0f}円相当 / "
            f"自動実行 {len(ctx.executed)}件 / 本人判断待ち {summary['hold']}件 / "
            f"今月の実績 {summary['month_done']}件・約{summary['month_yen']:.0f}円相当"
        )
        top = "\n".join(f"- [{o.site}] {o.title}" for o in route[:5])
        ctx.briefing = ctx.llm.ask(self.SYSTEM, f"{facts}\n上位案件:\n{top}", 600) or facts
        return opps, summary
