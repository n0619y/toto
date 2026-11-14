"""Claude に返させる構造化データの定義。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["新弾・新商品", "高騰・相場", "抽選・再販・在庫", "大会・デッキ", "開封・引き報告",
                   "偽物・詐欺・トラブル", "公式・イベント", "コレクション・鑑定", "その他"]
Label = Literal["positive", "negative", "neutral"]


class TopicItem(BaseModel):
    topic_key: str = Field(description="話題を表す英小文字とハイフンのID。前日と同じ話題なら前日のIDを再利用する")
    title: str = Field(description="日本語の見出し（30文字以内）")
    summary: str = Field(description="日本語の要約（2〜4文）。海外の話題も日本語で書く")
    key_points: list[str] = Field(description="要点の箇条書き（日本語、3つまで）")
    category: Category
    cards: list[str] = Field(description="話題に登場するカード名・商品名（日本語名があれば日本語）")
    post_ids: list[str] = Field(description="この話題に属する投稿ID（p1 形式）")


class TopicList(BaseModel):
    topics: list[TopicItem]


class ItemLabel(BaseModel):
    id: str
    label: Label


class SentimentResult(BaseModel):
    labels: list[ItemLabel] = Field(description="各コメントの判定（全件）")
    reaction_summary: str = Field(description="コメント欄の反応の要約（日本語、2〜3文）")
    positive_points: list[str] = Field(description="好意的な意見の代表例（日本語に要約、3つまで）")
    negative_points: list[str] = Field(description="否定的な意見の代表例（日本語に要約、3つまで）")


class BuylistRow(BaseModel):
    card_name: str
    card_number: str = Field(description="型番（例: 201/165）。不明なら空文字")
    rarity: str = Field(description="SAR/SR/AR/UR/HR/CHR/RR/PROMO など。不明なら空文字")
    price: int = Field(description="買取価格（円、整数）")
    condition: str = Field(description="状態条件（美品/PSA10/BOXシュリンク付きなど）。無ければ空文字")


class BuylistExtraction(BaseModel):
    rows: list[BuylistRow]


class MarketCommentary(BaseModel):
    headline: str = Field(description="今日の相場の見出し（日本語、40文字以内）")
    commentary: str = Field(description="相場の動きの解説（日本語、3〜6文）。SNSの話題との関連があれば触れる")
    watch_cards: list[str] = Field(description="注目カード（5枚まで）")
