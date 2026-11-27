"""Claude 呼び出し（任意）。キーが無い・失敗した場合は None を返し、
呼び出し側はルールベースの処理にフォールバックする。"""

from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger("poikatsu")

MODEL = "claude-opus-5-5"


class LLM:
    def __init__(self, enabled: bool = True):
        self._client = None
        key = os.getenv("ANTHROPIC_API_KEY", "")
        self.enabled = enabled and bool(key) and not key.startswith("sk-ant-xxxx")
        if self.enabled:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except ImportError:
                log.warning("anthropic パッケージが無いため、AIなし（ルールベース）で動きます")
                self.enabled = False

    def ask(self, system: str, prompt: str, max_tokens: int = 4000) -> str | None:
        if not self.enabled:
            return None
        try:
            resp = self._client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                output_config={"effort": "low"},
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # APIの不調で日次運用を止めない
            log.warning("Claude 呼び出し失敗（ルールベースで続行）: %s", exc)
            return None
        if resp.stop_reason != "end_turn":
            log.warning("Claude 応答が完了しませんでした (stop_reason=%s)", resp.stop_reason)
            return None
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def ask_json(self, system: str, prompt: str):
        text = self.ask(system, prompt)
        if not text:
            return None
        m = re.search(r"(\[.*\]|\{.*\})", text, re.S)
        try:
            return json.loads(m.group(1)) if m else None
        except json.JSONDecodeError:
            log.warning("Claude の JSON を解釈できませんでした")
            return None
