"""Anthropic Messages API over urllib. No SDK, no dependency. Needs ANTHROPIC_API_KEY."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from ..prompt import parse, render


def make(model: str, max_tokens: int = 400, retries: int = 4):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")

    def respond(task: dict) -> dict | None:
        system, user = render(task)
        body = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            f"{base}/v1/messages", data=body, method="POST",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.loads(r.read())
                text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
                respond.last_raw = text
                return parse(text)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                respond.last_raw = f"HTTP {e.code}: {e.read()[:300]!r}"
                return None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                respond.last_raw = f"error: {e}"
                return None
        return None

    respond.last_raw = ""
    return respond
