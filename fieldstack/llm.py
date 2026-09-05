"""
LLM gateway. One place that knows how to call a model; modules ask for structured
output and get a dict back. Swap providers or models per task here without touching
any module.

  ClaudeGateway   Anthropic SDK, structured output via output_config.format, adaptive thinking,
                  cached system prompt, usage recorded on every call.
  MockGateway     returns None from structured(); callers fall back to template text.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

DEFAULT_MODEL = "claude-opus-5"


@dataclass
class CallRecord:
    purpose: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int


class LLMGateway(Protocol):
    provider: str
    model: str
    calls: list[CallRecord]

    def structured(self, *, system: str, user: str, schema: dict, purpose: str, effort: str = "high") -> Optional[dict]: ...


@dataclass
class MockGateway:
    provider: str = "mock"
    model: str = "template"
    calls: list[CallRecord] = field(default_factory=list)

    def structured(self, *, system: str, user: str, schema: dict, purpose: str, effort: str = "high") -> Optional[dict]:
        return None


class ClaudeGateway:
    provider = "claude"

    def __init__(self, model: str = DEFAULT_MODEL):
        import anthropic
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.calls: list[CallRecord] = []

    def structured(self, *, system: str, user: str, schema: dict, purpose: str, effort: str = "high") -> Optional[dict]:
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=16000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            ) as stream:
                response = stream.get_final_message()
        except self._anthropic.AuthenticationError:
            raise RuntimeError("Claude credentials rejected. Set ANTHROPIC_API_KEY or run `ant auth login`.")
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request: "
                               f"{getattr(response.stop_details, 'explanation', None) or 'no detail'}")
        self.calls.append(CallRecord(
            purpose=purpose, model=response.model, input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=response.usage.cache_read_input_tokens or 0))
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    @property
    def usage(self) -> dict[str, Any]:
        return {"calls": len(self.calls),
                "input_tokens": sum(c.input_tokens for c in self.calls),
                "output_tokens": sum(c.output_tokens for c in self.calls),
                "cache_read_input_tokens": sum(c.cache_read_input_tokens for c in self.calls)}


def credentials_present() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "anthropic"
    return cfg.exists() and any(cfg.iterdir())


def make_gateway(provider: str = "auto", model: str = DEFAULT_MODEL) -> LLMGateway:
    if provider == "mock" or (provider == "auto" and not credentials_present()):
        return MockGateway()
    return ClaudeGateway(model=model)
