"""The Gemini client, tested against a fake local server: no key, network or quota is used."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from nlsql import llm, llm_gemini
from nlsql.llm_gemini import DailyQuotaExhausted, LLMUnavailable, chat, parse_response, to_gemini

KEY = "test-key-should-never-leak"


class Fake:
    """A scripted server: each request pops the next (status, body, headers); the requests it saw are kept."""
    def __init__(self, script):
        self.script, self.seen = list(script), []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.seen.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
                status, payload, headers = outer.script.pop(0) if outer.script else outer.script_last
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *a):
                pass
        self.script_last = (200, ok("x"), None)
        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1beta"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def ok(text, thoughts=0, finish="STOP"):
    return {"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": text}] if thoughts else [{"text": text}]}, "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 5, "thoughtsTokenCount": thoughts, "totalTokenCount": 16 + thoughts}}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "6000")
    monkeypatch.setattr(llm_gemini.time, "sleep", lambda s: None)
    monkeypatch.setattr(llm_gemini, "_last_call", 0.0)
    return tmp_path / "usage.json"


@pytest.fixture
def server():
    made = []

    def make(script):
        f = Fake(script)
        made.append(f)
        return f
    yield make
    for f in made:
        f.close()


MSGS = [{"role": "system", "content": "RULES"}, {"role": "user", "content": "Q1"}, {"role": "assistant", "content": "SELECT 1"}, {"role": "user", "content": "Q2"}]


def test_messages_become_a_system_instruction_and_alternating_contents():
    system, contents = to_gemini(MSGS)
    assert system == {"parts": [{"text": "RULES"}]}
    assert [c["role"] for c in contents] == ["user", "model", "user"] and contents[1]["parts"][0]["text"] == "SELECT 1"


def test_thought_parts_are_not_part_of_the_answer_but_are_counted_as_output_tokens():
    text, finish, tin, tout, stats = parse_response(ok("SELECT 2", thoughts=40))
    assert text == "SELECT 2" and finish == "STOP" and tin == 11 and tout == 45 and stats["thoughts_tokens"] == 40


def test_a_blocked_reply_has_empty_text_and_says_why():
    text, finish, *_ = parse_response({"promptFeedback": {"blockReason": "SAFETY"}})
    assert text == "" and finish == "SAFETY"


def test_a_call_returns_a_completion_and_sends_the_key_only_in_a_header(env, server):
    f = server([(200, ok("SELECT 3"), None)])
    c = chat("gemini-test", MSGS, base_url=f.url, usage_path=env, max_tokens=777, temperature=0.0)
    assert c.text == "SELECT 3" and c.tokens_in == 11 and c.finish_reason == "STOP"
    seen = f.seen[0]
    assert seen["key"] == KEY and KEY not in seen["path"] and seen["path"] == "/v1beta/models/gemini-test:generateContent"
    assert seen["body"]["generationConfig"] == {"temperature": 0.0, "maxOutputTokens": 777} and seen["body"]["systemInstruction"]["parts"][0]["text"] == "RULES"


def test_a_429_is_retried_with_the_server_asked_delay_and_then_succeeds(env, server):
    f = server([(429, {"error": {"message": "slow down"}}, {"Retry-After": "1"}), (503, {"error": {}}, None), (200, ok("SELECT 4"), None)])
    assert chat("gemini-test", MSGS, base_url=f.url, usage_path=env).text == "SELECT 4" and len(f.seen) == 3


def test_a_daily_quota_429_stops_at_once_instead_of_retrying(env, server):
    f = server([(429, {"error": {"message": "Quota exceeded for metric GenerateRequestsPerDayPerProjectPerModel"}}, None)])
    with pytest.raises(DailyQuotaExhausted):
        chat("gemini-test", MSGS, base_url=f.url, usage_path=env)
    assert len(f.seen) == 1


def test_the_own_daily_cap_stops_before_sending(env, server, monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_CAP", "2")
    f = server([(200, ok("a"), None)])
    chat("gemini-test", MSGS, base_url=f.url, usage_path=env)
    chat("gemini-test", MSGS, base_url=f.url, usage_path=env)
    with pytest.raises(DailyQuotaExhausted, match="cap of 2"):
        chat("gemini-test", MSGS, base_url=f.url, usage_path=env)
    assert len(f.seen) == 2 and llm_gemini.requests_today(env) == 2


def test_a_bad_request_is_not_retried_and_the_error_never_contains_the_key(env, server):
    f = server([(400, {"error": {"message": f"API key {KEY} not valid"}}, None)])
    with pytest.raises(LLMUnavailable) as e:
        chat("gemini-test", MSGS, base_url=f.url, usage_path=env)
    assert KEY not in str(e.value) and len(f.seen) == 1


def test_a_dropped_connection_is_retried_then_reported(env, monkeypatch):
    monkeypatch.setattr(llm_gemini.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(ConnectionResetError("WinError 10053")))
    with pytest.raises(LLMUnavailable, match="3 attempts"):
        chat("gemini-test", MSGS, base_url="http://127.0.0.1:1", usage_path=env, max_retries=2)


def test_the_limiter_spaces_calls_to_the_requests_per_minute(monkeypatch):
    sleeps, clock = [], [100.0]
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "15")
    monkeypatch.setattr(llm_gemini, "_last_call", 0.0)
    monkeypatch.setattr(llm_gemini.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(llm_gemini.time, "sleep", lambda s: (sleeps.append(round(s, 2)), clock.__setitem__(0, clock[0] + s)))
    llm_gemini._wait_for_slot()
    clock[0] += 1.0
    llm_gemini._wait_for_slot()
    assert sleeps == [3.0]                                  # 15 per minute is one every 4 s; 1 s had passed


def test_a_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm_gemini, "_read_env_file", lambda p: {})
    with pytest.raises(LLMUnavailable, match="GEMINI_API_KEY"):
        llm_gemini.api_key()


def test_llm_chat_routes_gemini_models_to_the_hosted_client(monkeypatch):
    called = {}
    monkeypatch.setattr(llm_gemini, "chat", lambda model, messages, **kw: called.update(model=model, kw=kw) or "routed")
    assert llm.chat("gemini-3.5-flash-lite", MSGS, max_tokens=99) == "routed" and called["model"] == "gemini-3.5-flash-lite" and called["kw"]["max_tokens"] == 99
