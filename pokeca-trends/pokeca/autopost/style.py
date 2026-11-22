"""伸びている投稿から「型」（構成・掴み・長さ・絵文字の使い方）を抽出する。文言はコピーしない。"""
from __future__ import annotations

from ..analysis import llm
from ..analysis.topics import engagement
from ..models import Post
from .schemas import StyleGuide

SYSTEM = """あなたはSNS運用のアナリストです。ポケカ（ポケモンカード）関連で反応が大きかった投稿と小さかった投稿を比べ、
伸びる投稿の「型」を抽象化して説明してください。
- 文章の構成・冒頭の掴み方・文字数・改行・絵文字・ハッシュタグ・語り口 を分析する
- 具体的な文言やフレーズをそのまま書き出さない（型として一般化する）
- 個人のアカウント名や個人を特定できる情報は出さない"""


def build(posts: list[Post], n_top: int = 30, n_bottom: int = 15) -> dict:
    ranked = sorted([p for p in posts if p.text], key=engagement, reverse=True)
    if len(ranked) < 5:
        return default()
    top, bottom = ranked[:n_top], ranked[-n_bottom:]
    fmt = lambda p: f"- ({p.source}/{'国内' if p.region == 'ja' else '海外'} いいね{p.likes} 返信{p.comments_count} 拡散{p.shares}) {' '.join(p.text.split())[:280]}"
    prompt = ("## 反応が大きかった投稿\n" + "\n".join(map(fmt, top)) +
              "\n\n## 反応が小さかった投稿\n" + "\n".join(map(fmt, bottom)))
    return llm.parse(StyleGuide, system=SYSTEM, content=prompt, effort="medium").model_dump()


def offline(posts: list[Post]) -> dict:
    ranked = sorted([p for p in posts if p.text], key=engagement, reverse=True)[:30]
    if not ranked:
        return default()
    avg = sum(len(p.text) for p in ranked) / len(ranked)
    tags = sum("#" in p.text for p in ranked) / len(ranked)
    g = default()
    g["length_tip"] = f"上位投稿の平均は約{avg:.0f}文字"
    g["emoji_hashtag_tip"] = f"上位投稿の{tags:.0%}がハッシュタグを使用"
    return g


def default() -> dict:
    return {"patterns": [{"name": "要点先出し", "structure": "1行目で結論・数字、2行目以降で補足", "why_it_works": "タイムラインで目に留まる"}],
            "hooks": ["数字から入る", "【】で見出しをつける"], "length_tip": "短め（2〜4行）",
            "emoji_hashtag_tip": "ハッシュタグは1〜2個", "avoid": ["根拠のない煽り", "長文の一段落"]}
