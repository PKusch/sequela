"""Any OpenAI-compatible chat endpoint over urllib: OpenAI, Gemini's compatibility
layer, Ollama, LM Studio, vLLM. OPENAI_API_KEY and OPENAI_BASE_URL are honoured."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from ..prompt import parse, render


def make(model: str, base_url: str | None = None, api_key: str | None = None,
         max_tokens: int = 400, retries: int = 4):
    key = api_key or os.environ.get("OPENAI_API_KEY")
    base = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set (any value works for a local server)")

    def respond(task: dict) -> dict | None:
        system, user = render(task)
        body = json.dumps({
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            f"{base}/chat/completions", data=body, method="POST",
            headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
        )
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.loads(r.read())
                text = data["choices"][0]["message"]["content"] or ""
                respond.last_raw = text
                return parse(text)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                respond.last_raw = f"HTTP {e.code}: {e.read()[:300]!r}"
                return None
            except (urllib.error.URLError, TimeoutError, KeyError) as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                respond.last_raw = f"error: {e}"
                return None
        return None

    respond.last_raw = ""
    return respond
