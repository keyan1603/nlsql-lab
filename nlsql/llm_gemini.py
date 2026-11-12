"""A minimal Gemini client with the same shape as nlsql.llm.chat. Standard library only.

Free-tier discipline, per the series conventions: one model (gemini-3.5-flash-lite), a requests-per-minute limiter
(REQUESTS_PER_MINUTE, default 15), backoff on 429/5xx and on dropped connections, and a hard cap on requests per day
(GEMINI_DAILY_CAP, default 450 of the 500 the free tier allows) kept in runs/gemini_usage.json, so a long run stops
before it burns the quota. The key is read from GEMINI_API_KEY (environment or the lab's .env) and goes only in a
request header, never in a URL, a log line or an error message.
"""

from __future__ import annotations

import http.client
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from nlsql.config import ROOT, _read_env_file
from nlsql.llm import Completion, LLMUnavailable

DEFAULT_MODEL = "gemini-3.5-flash-lite"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
USAGE_FILE = ROOT / "runs" / "gemini_usage.json"
RETRYABLE = {429, 500, 502, 503, 504}
TRANSPORT_ERRORS = (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException, OSError)


class DailyQuotaExhausted(LLMUnavailable):
    """Either our own daily cap or the service's per-day quota has been reached; retrying today will not help."""


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or _read_env_file(ROOT / ".env").get("GEMINI_API_KEY", "")
    if not key:
        raise LLMUnavailable("GEMINI_API_KEY is not set (environment variable or the lab's .env file)")
    return key


def _setting(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or _read_env_file(ROOT / ".env").get(name) or default)
    except ValueError:
        return default


# ---- rate limit and daily cap
_last_call = 0.0


def _wait_for_slot() -> None:
    """Space calls so we never exceed REQUESTS_PER_MINUTE."""
    global _last_call
    gap = 60.0 / max(_setting("REQUESTS_PER_MINUTE", 15), 1)
    now = time.monotonic()
    if _last_call and now - _last_call < gap:
        time.sleep(gap - (now - _last_call))
    _last_call = time.monotonic()


def requests_today(path: Path | None = None) -> int:
    p = path or USAGE_FILE
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get(date.today().isoformat(), 0))
    except (OSError, ValueError):
        return 0


def _count_request(path: Path | None = None) -> None:
    p = path or USAGE_FILE
    cap = int(_setting("GEMINI_DAILY_CAP", 450))
    used = requests_today(p)
    if used >= cap:
        raise DailyQuotaExhausted(f"daily request cap of {cap} reached ({used} sent today); raise GEMINI_DAILY_CAP only if the quota allows it")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({date.today().isoformat(): used + 1}), encoding="utf-8")


# ---- message conversion and response parsing
def to_gemini(messages: list[dict]) -> tuple[dict | None, list[dict]]:
    """OpenAI-style chat messages to Gemini's systemInstruction plus alternating user/model contents."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages if m["role"] != "system"]
    return ({"parts": [{"text": system}]} if system else None), contents


def parse_response(data: dict) -> tuple[str, str, int, int, dict]:
    cands = data.get("candidates") or []
    parts = ((cands[0].get("content") or {}).get("parts") or []) if cands else []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    finish = (cands[0].get("finishReason") if cands else None) or (data.get("promptFeedback") or {}).get("blockReason", "") or "no_candidates"
    u = data.get("usageMetadata") or {}
    thoughts = int(u.get("thoughtsTokenCount", 0))
    return text, finish, int(u.get("promptTokenCount", 0)), int(u.get("candidatesTokenCount", 0)) + thoughts, {"thoughts_tokens": thoughts, "total_tokens": int(u.get("totalTokenCount", 0))}


# ---- the call
def chat(model: str, messages: list[dict], max_tokens: int = 4096, temperature: float = 0.0, timeout_s: float = 120,
         base_url: str = BASE_URL, max_retries: int = 6, usage_path: Path | None = None) -> Completion:
    system, contents = to_gemini(messages)
    body = {"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = system
    payload = json.dumps(body).encode()
    key = api_key()
    url = f"{base_url}/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    t0 = time.perf_counter()
    last = "no attempt made"
    for attempt in range(max_retries + 1):
        _count_request(usage_path)
        _wait_for_slot()
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                data = json.load(r)
            text, finish, tin, tout, stats = parse_response(data)
            return Completion(text=text, latency_s=time.perf_counter() - t0, tokens_in=tin, tokens_out=tout, finish_reason=finish, stats=stats)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400].replace(key, "***")
            if exc.code == 429 and ("PerDay" in detail or "per day" in detail.lower()):
                raise DailyQuotaExhausted(f"the service's daily quota is exhausted: {detail[:160]}") from None
            if exc.code not in RETRYABLE:
                raise LLMUnavailable(f"Gemini returned HTTP {exc.code}: {detail[:200]}") from None
            last = f"HTTP {exc.code}"
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = float(retry_after) if retry_after and retry_after.replace(".", "").isdigit() else None
        except TRANSPORT_ERRORS as exc:
            last = f"{type(exc).__name__}"
            delay = None
        if attempt == max_retries:
            break
        time.sleep(delay if delay is not None else min(60.0, 2.0 ** attempt + random.random()))
    raise LLMUnavailable(f"Gemini call failed after {max_retries + 1} attempts (last: {last})")
