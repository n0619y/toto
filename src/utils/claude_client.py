"""Claude API クライアントのラッパー。

- .env から ANTHROPIC_API_KEY を読み込む
- 安全・倫理要件をシステムプロンプトに常時注入する
- API失敗時に最大3回（設定可）リトライする
- anthropic パッケージが無い／キー未設定でもプログラム全体が落ちないよう
  分かりやすい例外メッセージを出す
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

from dotenv import load_dotenv

from .common import get_logger, load_settings, reviewer_display

load_dotenv()  # .env を読み込む
logger = get_logger()

# すべてのClaude呼び出しに常時付与する安全・倫理プロンプト（依頼の絶対遵守要件）
SAFETY_SYSTEM_PROMPT = f"""あなたは小児科領域の保護者向けコンテンツを作成する、医療ライティングの専門家です。
以下のルールを「絶対に」守ってください。違反は許されません。

【安全・倫理ルール】
1. あなたは診断・処方を行いません。「〜と診断できます」「この薬を飲ませましょう」のような
   断定的な診断・処方表現は禁止です。
2. すべての医学的記述には、必ず受診を促す視点を含めてください。
3. 緊急症状（けいれん、意識障害、呼吸困難、ぐったりして反応が乏しい、脱水、
   生後3か月未満の発熱など）に該当しうる内容では、冒頭に「すぐ医療機関を受診してください」
   という主旨の警告を必ず置いてください。
4. 商品名・薬剤の商品名は使わず、必ず一般名（成分名）で記載してください。
5. 個人情報・特定の症例・症例画像は一切扱いません。
6. 出典のない医学的主張は書かないでください。提供された出典情報の範囲で記述します。
7. 文末には必ず「本コンテンツは一般的情報提供です。診断・治療は必ず医療機関に
   ご相談ください」という主旨の免責文を入れてください。
8. すべての成果物に監修者表記「{reviewer_display()}」を含めてください。

【トーン】
- 対象読者: 未就学児〜小学生の保護者
- やさしく、専門用語には注釈をつけ、断定を避けつつ実用的に。保護者の不安に寄り添う。
"""


class ClaudeClient:
    """Claude API を安全に呼び出すための薄いラッパークラス。"""

    def __init__(self) -> None:
        cfg = load_settings()["claude"]
        self.model: str = cfg["model"]
        self.max_tokens: int = cfg.get("max_tokens", 8000)
        self.temperature: float = cfg.get("temperature", 0.5)
        self.max_retries: int = cfg.get("max_retries", 3)
        self._client = None  # 遅延初期化

    def _get_client(self):
        """anthropic クライアントを遅延生成する。"""
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:  # パッケージ未導入
            raise RuntimeError(
                "anthropic パッケージが見つかりません。\n"
                "  pip install -r requirements.txt を実行してください。"
            ) from exc

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key or api_key.startswith("sk-ant-xxxx"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY が設定されていません。\n"
                "  .env ファイルに実際のAPIキーを記入してください。\n"
                "  取得方法は README.md を参照してください。"
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """プロンプトを投げてテキスト応答を返す。

        安全プロンプトは常に先頭に付与される。失敗時は指数バックオフでリトライ。
        """
        client = self._get_client()

        # 安全プロンプトは常に付与し、呼び出し側の追加systemを連結する
        full_system = SAFETY_SYSTEM_PROMPT
        if system:
            full_system += "\n\n【今回のタスク固有の指示】\n" + system

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    temperature=(
                        temperature if temperature is not None else self.temperature
                    ),
                    system=full_system,
                    messages=[{"role": "user", "content": prompt}],
                )
                # テキストブロックを結合して返す
                parts: List[str] = [
                    block.text for block in resp.content if getattr(block, "type", "") == "text"
                ]
                return "\n".join(parts).strip()
            except Exception as exc:  # APIエラー全般
                last_error = exc
                wait = 2 ** attempt  # 2s, 4s, 8s...
                logger.warning(
                    "Claude API 呼び出し失敗 (試行 %d/%d): %s — %d秒待機してリトライ",
                    attempt, self.max_retries, exc, wait,
                )
                if attempt < self.max_retries:
                    time.sleep(wait)

        raise RuntimeError(
            f"Claude API がリトライ上限({self.max_retries}回)に達しました: {last_error}"
        )
