"""投稿文の生成と審査。

1. 話題（サイトで要約済みの事実）と型を選ぶ
2. Claude が候補を複数作る（スタイルガイド＝バズ投稿の型、プレイブック＝自分の過去成績からの学び を反映）
3. 機械チェック（文字数・盗用・禁止表現）＋ 別の Claude 呼び出しで事実・規約を審査
4. 合格した候補のうち見込みが最も高いものを採用
"""
from __future__ import annotations

import json
import random

from ..analysis import llm
from ..config import get_logger, settings
from ..market.analytics import match_cards
from . import guard
from .schemas import CandidateList, Review

log = get_logger()

WRITER = """あなたはポケカ（ポケモンカード）情報アカウントの中の人です。国内外のSNSの話題と買取相場をまとめたサイトの内容をもとに、
SNSに投稿する文章を書きます。

絶対に守ること:
- 書いてよい事実は「資料」にあるものだけ。数字・固有名詞・日付を作らない、盛らない
- 自分がカードを引いた・買った・売ったなどの体験談は書かない（このアカウントは情報まとめアカウント）
- 値上がり・値下がりの断定、購入・売却の推奨はしない（「〜の動き」「〜という声」と事実として伝える）
- 他人の投稿の文言をそのまま使わない。スタイルガイドは“型”の参考にするだけで、文章は毎回自分の言葉で書く
- メンション（@）は使わない。転売・詐欺など個人への攻撃につながる書き方をしない
- 日本語で書く"""

REVIEWER = """あなたはSNS投稿の審査担当です。投稿候補を、資料と照らし合わせて厳しく審査します。
不合格にする条件:
- 資料にない事実・数字・固有名詞がある、または資料と食い違う
- 体験談の捏造（自分が引いた・当てた等）、なりすまし
- 断定的な相場予測や売買の推奨
- 誹謗中傷、特定の個人・店舗への攻撃、根拠のない詐欺扱い
- 誤解を招く煽り（実際より大げさな「爆上がり」「速報」など）
appeal は、事実に忠実なまま反応が取れそうかを1〜10で評価する。"""


def topic_material(t: dict, market: dict | None) -> str:
    s = t.get("sentiment", {})
    lines = [f"話題: {t['title']}", f"カテゴリ: {t.get('category')}", f"要約: {t['summary']}",
             "要点: " + " / ".join(t.get("key_points", [])),
             f"話題になっている場所: {t.get('region')}（{', '.join(t.get('sources', []))}）",
             f"SNSの反応: {s.get('overall')}（好意的{s.get('ratio', {}).get('positive')}% 否定的{s.get('ratio', {}).get('negative')}%）",
             "好意的な声: " + " / ".join(s.get("positive_points", [])),
             "否定的な声: " + " / ".join(s.get("negative_points", []))]
    for c in match_cards(t.get("cards", []), (market or {}).get("cards", []), limit=3):
        chg = lambda v: f"{v:+.1f}%" if v is not None else "不明"
        lines.append(f"買取相場: {c['name']} {c['rarity']} 最高買取{c['price']:,}円（前日比{chg(c['chg_1d'])}、7日比{chg(c['chg_7d'])}、{len(c['shop_prices'])}店舗の集計）")
    return "\n".join(lines)


def fits_archetype(arche: str, t: dict, market: dict | None) -> bool:
    if arche == "souba":
        return bool(match_cards(t.get("cards", []), (market or {}).get("cards", []), limit=1))
    if arche == "kaigai":
        return t.get("region") in ("global", "both")
    if arche == "voice":
        return t.get("sentiment", {}).get("analyzed", 0) >= 10
    return True


def compose(platform: str, topic: dict, archetype: str, style: dict, playbook: dict | None,
            market: dict | None, sources: list[str], own: list[str], use_ai: bool) -> dict | None:
    cfg = settings()["autopost"]
    limit = "全角140字（Xの上限。改行・ハッシュタグ込み）" if platform == "x" else "500字以内（短めが望ましい）"
    link = cfg.get("site_url") if cfg.get("site_url") and random.random() < cfg.get("link_ratio", 0) else ""
    material = topic_material(topic, market)
    if not use_ai:
        cands = [offline_text(platform, topic, archetype, market)]
        reviews = [{"approved": True, "issues": [], "appeal": 5}]
    else:
        prompt = (f"## 投稿先\n{platform}（{limit}）\n\n## 今回の型\n{cfg['archetypes'][archetype]}\n\n"
                  f"## 資料（書いてよい事実はここだけ）\n{material}\n\n"
                  f"## スタイルガイド（伸びている投稿の型。文言は真似しない）\n{json.dumps(style, ensure_ascii=False)}\n\n"
                  f"## 自分の過去投稿の成績から学んだこと\n{json.dumps(playbook or {}, ensure_ascii=False)}\n\n"
                  + (f"## 本文の最後に付けるURL\n{link}\n\n" if link else "")
                  + f"違う切り口で候補を{cfg.get('candidates', 3)}つ作ってください。ハッシュタグは{cfg.get('max_hashtags', 2)}個まで。")
        cands = [c.text.strip() for c in llm.parse(CandidateList, system=WRITER, content=prompt, effort="medium").candidates]
        rv = llm.parse(Review, system=REVIEWER, effort="medium", content=(
            f"## 資料\n{material}\n\n## 候補\n" + "\n\n".join(f"[{i}]\n{c}" for i, c in enumerate(cands))))
        by_i = {r.index: r for r in rv.items}
        reviews = [by_i[i].model_dump() if i in by_i else {"approved": False, "issues": ["審査結果なし"], "appeal": 0}
                   for i in range(len(cands))]

    best = None
    for text, rv in zip(cands, reviews):
        issues = guard.check(platform, text, sources, own, cfg, cfg.get("site_url", ""))
        rv = {**rv, "issues": rv.get("issues", []) + issues, "approved": rv.get("approved") and not issues}
        log.info("[%s/%s] 候補 %s: %s", platform, archetype, "合格" if rv["approved"] else "不合格",
                 "; ".join(rv["issues"]) or text.replace("\n", " ")[:50])
        if rv["approved"] and (best is None or rv["appeal"] > best["review"]["appeal"]):
            best = {"text": text, "review": rv}
    return best


# ---------- APIキー無しのテンプレート生成（デモ・動作確認用） ----------
def offline_text(platform: str, t: dict, arche: str, market: dict | None) -> str:
    s = t.get("sentiment", {})
    r = s.get("ratio", {})
    tag = "#ポケカ"
    t = {**t, "title": t["title"].replace("「", "").replace("」", "")}
    cards = match_cards(t.get("cards", []), (market or {}).get("cards", []), limit=1)
    body = {
        "sokuho": f"【話題】{t['title']}\n{len(t.get('sources', []))}つのSNSで計{t.get('post_count', 0)}件の投稿",
        "question": f"{t['title']}\nSNSでは好意的{r.get('positive')}%・否定的{r.get('negative')}%と反応が分かれています。みなさんはどう思いますか？",
        "matome": f"今日のポケカ話題{t['rank']}位：{t['title']}\n・反応: {s.get('overall')}\n・話題の場所: {'・'.join(t.get('sources', []))}",
        "souba": (f"{cards[0]['name']} {cards[0]['rarity']} の最高買取は{cards[0]['price']:,}円"
                  f"（7日比{cards[0]['chg_7d']:+.1f}%）。SNSでも「{t['title']}」が話題です" if cards and cards[0]["chg_7d"] is not None
                  else f"{t['title']}"),
        "kaigai": f"海外SNSで話題：{t['title']}\n反応は「{s.get('overall')}」",
        "voice": f"「{t['title']}」へのSNSの反応は{s.get('overall')}。好意的{r.get('positive')}% / 否定的{r.get('negative')}%",
    }[arche]
    text = f"{body}\n{tag}"
    while platform == "x" and not guard.fits("x", text):
        body = body[:-5]
        text = f"{body}…\n{tag}"
    return text
