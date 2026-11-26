"""自動投稿で Claude に返させる構造化データ。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class StylePattern(BaseModel):
    name: str = Field(description="型の名前（例: 【速報】見出し＋1行要約）")
    structure: str = Field(description="文の組み立て方を抽象化した説明。元投稿の文言はコピーしない")
    why_it_works: str


class StyleGuide(BaseModel):
    patterns: list[StylePattern] = Field(description="伸びている投稿に共通する型（5つまで）")
    hooks: list[str] = Field(description="冒頭の掴みの“型”（例: 数字から入る、【】で見出し）。具体的な文言の丸写しは不可")
    length_tip: str = Field(description="伸びている投稿の文字数・改行の傾向")
    emoji_hashtag_tip: str = Field(description="絵文字・ハッシュタグの使い方の傾向")
    avoid: list[str] = Field(description="伸びていない投稿・反感を買っている投稿に共通する特徴")


class Candidate(BaseModel):
    text: str = Field(description="投稿本文（ハッシュタグ込み）")
    facts_used: list[str] = Field(description="本文中の事実が、与えられた資料のどの記述に基づくか")


class CandidateList(BaseModel):
    candidates: list[Candidate]


class ReviewItem(BaseModel):
    index: int
    approved: bool
    issues: list[str] = Field(description="問題点。無ければ空")
    appeal: int = Field(description="反応の取れやすさの見込み 1〜10")


class Review(BaseModel):
    items: list[ReviewItem]


class Playbook(BaseModel):
    insights: list[str] = Field(description="自分の過去投稿の成績から分かったこと（数字の根拠つき）")
    do: list[str] = Field(description="次の投稿で続けること・増やすこと")
    dont: list[str] = Field(description="次の投稿で避けること")
