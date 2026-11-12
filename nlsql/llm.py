"""A minimal client for LM Studio's local server (OpenAI-compatible API on localhost). Standard library only.

The server is local, so a call costs nothing but time and power. Greedy decoding (temperature 0) for repeatable runs.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# LM Studio reports the port it actually started on (`lms server status`); set LMSTUDIO_BASE_URL when it is not the default 1234
BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")


@dataclass
class Completion:
    text: str
    latency_s: float
    tokens_in: int
    tokens_out: int
    finish_reason: str
    stats: dict


class LLMUnavailable(Exception):
    pass


def list_models(base_url: str = BASE_URL) -> list[str]:
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=5) as r:
            return [m["id"] for m in json.load(r)["data"]]
    except (urllib.error.URLError, OSError) as exc:
        raise LLMUnavailable(f"LM Studio server not reachable at {base_url}: {exc}") from exc


def chat(model: str, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.0, timeout_s: float = 600,
         base_url: str = BASE_URL) -> Completion:
    if model.startswith("gemini"):                           # hosted model: same call, same result type (see nlsql/llm_gemini.py)
        from nlsql import llm_gemini
        return llm_gemini.chat(model, messages, max_tokens=max_tokens, temperature=temperature)
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": False}).encode()
    req = urllib.request.Request(f"{base_url}/chat/completions", data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            data = json.load(r)
    except (urllib.error.URLError, OSError) as exc:
        raise LLMUnavailable(f"chat call failed: {exc}") from exc
    elapsed = time.perf_counter() - t0
    choice = data["choices"][0]
    usage = data.get("usage") or {}
    return Completion(text=choice["message"].get("content") or "", latency_s=elapsed, tokens_in=int(usage.get("prompt_tokens", 0)),
                      tokens_out=int(usage.get("completion_tokens", 0)), finish_reason=choice.get("finish_reason", ""), stats=data.get("stats") or {})
