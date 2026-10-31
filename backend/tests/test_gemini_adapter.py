"""Gemini adapter — offline contract test with a fake client built from real google-genai SDK types.

Verifies config construction (system instruction, function declarations with
JSON schema), the manual function-calling loop, deterministic tool execution,
the numeric-fidelity guard and fallback to Tool mode. It does NOT prove live
API compatibility — that needs a real GEMINI_API_KEY (plan.md §7).
"""

import pytest

genai_types = pytest.importorskip("google.genai.types")

from app.config import get_settings  # noqa: E402
from app.services.saathi import gemini  # noqa: E402


class FakeResp:
    def __init__(self, calls=None, text=None):
        self.function_calls = calls
        self.text = text
        parts = [genai_types.Part(function_call=c) for c in calls] if calls else [genai_types.Part(text=text or "")]
        self.candidates = [genai_types.Candidate(content=genai_types.Content(role="model", parts=parts))]


class FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def generate_content(self, model, contents, config):
        assert isinstance(config, genai_types.GenerateContentConfig)
        names = [d.name for d in config.tools[0].function_declarations]
        assert "cards_best_for_spend" in names and "loans_search" in names
        assert "Vitt Saathi" in config.system_instruction
        self.seen.append(contents)
        return self.script.pop(0)


class FakeClient:
    def __init__(self, script):
        self.models = FakeModels(script)


def test_client_bounds_provider_wait_and_disables_sdk_retries(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("google.genai.Client", Client)
    monkeypatch.setattr(gemini.get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(gemini.get_settings(), "gemini_timeout_ms", 10_000)
    gemini._client()
    assert seen["http_options"] == {"timeout": 10_000, "retry_options": {"attempts": 1}}


@pytest.fixture
def gemini_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr(s, "gemini_model", "configured-model-id")
    monkeypatch.setattr(gemini, "_provider_unavailable_until", 0.0)
    yield


def test_function_calling_loop_uses_deterministic_tools(sample, gemini_on, monkeypatch):
    call = genai_types.FunctionCall(name="cards_best_for_spend", args={"amount": 30000, "category": "travel"})
    fake = FakeClient([FakeResp(calls=[call]), FakeResp(text="Use Horizon Voyager: about ₹1,500 in miles.")])
    monkeypatch.setattr(gemini, "_client", lambda *a, **k: fake)
    r = sample.post("/api/ai/chat", json={"message": "Which card for a 30k flight?", "context_type": "dashboard"}).json()
    m = r["message"]
    assert m["mode"] == "gemini"
    assert any(c["type"] == "card_ranking" for c in m["cards"])
    assert m["flags"] == []  # ₹1,500 matches the tool output (lang is reported separately)
    # second model call received the function response
    assert len(fake.models.seen) == 2


def test_model_wait_does_not_hold_sqlite_write_lock(sample, gemini_on, monkeypatch):
    from app.db import engine

    if engine.dialect.name != "sqlite":
        pytest.skip("SQLite write-lock regression")

    class Models:
        def generate_content(self, **kwargs):
            # The model call runs after the chat has inserted its user message.
            # A separate connection must be able to start a write transaction.
            with engine.connect() as other:
                other.exec_driver_sql("BEGIN IMMEDIATE")
                other.rollback()
            return FakeResp(text="I can help with your cards.")

    class Client:
        models = Models()

    monkeypatch.setattr(gemini, "_client", lambda *a, **k: Client())
    r = sample.post("/api/ai/chat", json={"message": "Help with cards", "context_type": "card"})
    assert r.status_code == 200, r.text
    assert r.json()["message"]["mode"] == "gemini"


def test_numeric_fidelity_flags_invented_amount(sample, gemini_on, monkeypatch):
    call = genai_types.FunctionCall(name="cards_best_for_spend", args={"amount": 30000, "category": "travel"})
    fake = FakeClient([FakeResp(calls=[call]), FakeResp(text="You'll get ₹9,999 back.")])
    monkeypatch.setattr(gemini, "_client", lambda *a, **k: fake)
    m = sample.post("/api/ai/chat", json={"message": "Which card?", "context_type": "dashboard"}).json()["message"]
    assert "unverified_amount:9999" in m["flags"]


def test_disallowed_tool_is_refused(sample, gemini_on, monkeypatch):
    # model tries a loan tool from the insurance context → tool error returned to the model, not executed
    call = genai_types.FunctionCall(name="loans_search", args={"purpose": "personal", "amount": 100000})

    class Models(FakeModels):
        def generate_content(self, model, contents, config):
            self.seen.append(contents)
            return self.script.pop(0)

    fake = FakeClient([])
    fake.models = Models([FakeResp(calls=[call]), FakeResp(text="That's on the Loans page.")])
    monkeypatch.setattr(gemini, "_client", lambda *a, **k: fake)
    m = sample.post("/api/ai/chat", json={"message": "loan?", "context_type": "insurance"}).json()["message"]
    assert not any(c["type"] == "loan_options" for c in m["cards"])


def test_api_failure_falls_back_to_tool_mode(sample, gemini_on, monkeypatch):
    calls = 0

    class Boom:
        class models:
            @staticmethod
            def generate_content(**kw):
                nonlocal calls
                calls += 1
                raise ConnectionError("down")

    monkeypatch.setattr(gemini, "_client", lambda *a, **k: Boom())
    m = sample.post("/api/ai/chat", json={"message": "Show my upcoming EMIs", "context_type": "dashboard"}).json()["message"]
    assert m["mode"] == "tool" and "ai_unavailable" in m["flags"]
    assert any(c["type"] == "emi_list" for c in m["cards"])
    again = sample.post("/api/ai/chat", json={"message": "Show my upcoming EMIs", "context_type": "dashboard"}).json()["message"]
    assert again["mode"] == "tool" and calls == 1
