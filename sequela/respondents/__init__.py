"""
Things that answer tasks. Two kinds:

- reference respondents: deterministic policies with a known flaw each, used
  to check that the scorer sees what it claims to see and to give a scale.
  They are not models and are never reported as models.
- backends: live model APIs. Anthropic's Messages API and any
  OpenAI-compatible chat endpoint (which covers OpenAI, Gemini's compatibility
  layer, Ollama, LM Studio, vLLM).

A respondent is a callable task -> normalised report or None.
"""
from __future__ import annotations

from collections.abc import Callable

from . import reference

Respondent = Callable[[dict], dict | None]


def resolve(spec: str) -> tuple[str, Respondent]:
    """'reference:trusting' | 'anthropic:claude-sonnet-5' | 'openai:gpt-5' | 'ollama:llama3.2'"""
    kind, _, arg = spec.partition(":")
    if kind == "reference":
        if arg not in reference.POLICIES:
            raise SystemExit(f"unknown reference policy '{arg}'; choose from {', '.join(reference.POLICIES)}")
        return f"reference:{arg}", reference.POLICIES[arg]
    if kind == "anthropic":
        from .anthropic_backend import make
        model = arg or "claude-sonnet-5"
        return f"anthropic:{model}", make(model)
    if kind in ("openai", "ollama"):
        from .openai_backend import make
        import os
        if kind == "ollama":
            base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            return f"ollama:{arg}", make(arg, base_url=base, api_key="ollama")
        return f"openai:{arg}", make(arg)
    raise SystemExit(f"unknown respondent kind '{kind}'")
