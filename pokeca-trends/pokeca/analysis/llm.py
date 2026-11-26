"""Claude API 呼び出し（構造化出力）。

- 出力は Pydantic モデルでスキーマ固定（JSON崩れが起きない）
- 長い入力に備えてストリーミングで受け取る
- 安全分類器による拒否時は server-side fallback で別モデルが続行する
"""
from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from ..config import env, get_logger, settings

log = get_logger()
T = TypeVar("T", bound=BaseModel)
_client = None


def available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(env("ANTHROPIC_API_KEY") or env("ANTHROPIC_AUTH_TOKEN"))


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(max_retries=4)
    return _client


def parse(schema: type[T], *, system: str, content, model: str | None = None,
          effort: str = "medium", max_tokens: int = 64000) -> T:
    """content は文字列、または画像ブロックを含む content ブロック配列。"""
    cfg = settings()["claude"]
    with client().beta.messages.stream(
        model=model or cfg["model"],
        max_tokens=max_tokens,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"Claude が処理を拒否しました: {getattr(msg, 'stop_details', None)}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("出力が max_tokens に達しました。入力件数を減らしてください。")
    if msg.parsed_output is None:
        raise RuntimeError("構造化出力の解析に失敗しました")
    return msg.parsed_output
