"""Gemini adapter under stress: runaway tools, bad tool names, cooldown, empty answers, voice tokens, prompt isolation.

A fake client built from the real SDK types stands in for the provider; nothing here reaches Google.
"""

import pytest

genai_types = pytest.importorskip("google.genai.types")

from app.config import get_settings  # noqa: E402
from app.errors import DomainError  # noqa: E402
from app.services.saathi import gemini  # noqa: E402


class Resp:
    def __init__(self, calls=None, text=None):
        self.function_calls = calls
        self.text = text
        parts = [genai_types.Part(function_call=c) for c in calls] if calls else [genai_types.Part(text=text or "")]
        self.candidates = [genai_types.Candidate(content=genai_types.Content(role="model", parts=parts))]


def fn(name, **args):
    return genai_types.FunctionCall(name=name, args=args)


class Client:
    """Replies from a script, or from a factory when the script runs out (for 'never stops calling tools')."""

    def __init__(self, script=(), forever=None):
        self.script, self.forever, self.requests = list(script), forever, []
        outer = self

        class Models:
            def generate_content(self, model, contents, config):
                outer.requests.append({"contents": contents, "config": config})
                if outer.script:
                    return outer.script.pop(0)
                if outer.forever:
                    return outer.forever()
                raise ConnectionError("provider down")
        self.models = Models()


@pytest.fixture(autouse=True)
def gemini_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr(s, "gemini_model", "m")
    monkeypatch.setattr(gemini, "_provider_unavailable_until", 0.0)


def chat(sample, monkeypatch, client, message="Which card for a flight?", ctx="dashboard"):
    monkeypatch.setattr(gemini, "_client", lambda *a, **k: client)
    return sample.post("/api/ai/chat", json={"message": message, "context_type": ctx}).json()["message"]


def test_a_model_that_never_stops_calling_tools_is_cut_off(sample, monkeypatch):
    client = Client(forever=lambda: Resp(calls=[fn("cards_best_for_spend", amount=1000, category="travel")]))
    m = chat(sample, monkeypatch, client)
    assert len(client.requests) == gemini.MAX_TOOL_STEPS, "the loop is bounded"
    assert m["mode"] == "gemini" and "calculations" in m["content"]
    assert m["cards"], "the tool results gathered so far are still shown"


def test_an_unknown_tool_name_is_refused_and_the_conversation_continues(sample, monkeypatch):
    client = Client([Resp(calls=[fn("drop_all_tables", confirm=True)]), Resp(text="I can't do that, but I can compare your cards.")])
    m = chat(sample, monkeypatch, client)
    assert m["content"].startswith("I can't do that")
    refused = client.requests[1]["contents"][-1].parts[0].function_response.response["result"]
    assert "error" in refused, "the model is told the tool was refused"
    assert not m["cards"]


def test_bad_tool_arguments_come_back_as_errors_not_crashes(sample, monkeypatch):
    client = Client([Resp(calls=[fn("cards_best_for_spend", amount=-50)]), Resp(text="That amount isn't valid.")])
    m = chat(sample, monkeypatch, client)
    assert m["mode"] == "gemini" and m["content"] == "That amount isn't valid."


def test_an_empty_model_answer_gets_a_polite_fallback(sample, monkeypatch):
    m = chat(sample, monkeypatch, Client([Resp(text="   ")]))
    assert m["content"] == "I don't have an answer for that."


def test_after_a_failure_the_provider_is_not_hammered_during_the_cooldown(sample, monkeypatch):
    client = Client()   # raises on the first call
    first = chat(sample, monkeypatch, client, message="Show my upcoming EMIs")
    assert "ai_unavailable" in first["flags"] and first["mode"] == "tool"
    n = len(client.requests)
    second = chat(sample, monkeypatch, client, message="Show my upcoming EMIs")
    assert len(client.requests) == n, "no provider request while cooling down"
    assert second["mode"] == "tool" and "ai_unavailable" in second["flags"]


def test_an_invented_amount_replaces_the_whole_answer(sample, monkeypatch):
    client = Client([Resp(calls=[fn("cards_best_for_spend", amount=30000, category="travel")]), Resp(text="You'll earn ₹9,999 back!")])
    m = chat(sample, monkeypatch, client)
    assert "9,999" not in m["content"] and "couldn't verify every amount" in m["content"]
    assert any(c["type"] == "card_ranking" for c in m["cards"]), "the calculated result is still on screen"


# --- ephemeral voice tokens -----------------------------------------------------------------------------

CTX = {"type": "dashboard"}


def test_voice_is_unavailable_until_live_is_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_live_model", None)
    with pytest.raises(DomainError) as exc:
        gemini.live_session_token(CTX, "sys")
    assert exc.value.status_code == 503 and exc.value.code == "INTEGRATION_NOT_CONFIGURED"


def test_a_voice_token_is_single_use_short_lived_and_never_the_api_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_live_model", "live-model")
    seen = {}

    class Tokens:
        def create(self, config):
            seen.update(config)
            return type("T", (), {"name": "auth_tokens/ephemeral-123"})()

    monkeypatch.setattr(gemini, "_client", lambda *a, **k: type("C", (), {"auth_tokens": Tokens()})())
    out = gemini.live_session_token(CTX, "be helpful")
    assert out["token"] == "auth_tokens/ephemeral-123" and out["model"] == "live-model" and out["system_instruction"] == "be helpful"
    assert seen["uses"] == 1 and (seen["expire_time"] - seen["new_session_expire_time"]).total_seconds() > 0
    assert "test-key" not in str(out), "the long-lived API key must never reach the browser"


def test_a_provider_error_during_token_minting_becomes_a_friendly_503(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_live_model", "live-model")

    class Tokens:
        def create(self, config):
            raise RuntimeError("quota exceeded for key test-key")

    monkeypatch.setattr(gemini, "_client", lambda *a, **k: type("C", (), {"auth_tokens": Tokens()})())
    with pytest.raises(DomainError) as exc:
        gemini.live_session_token(CTX, "sys")
    assert exc.value.code == "VOICE_UNAVAILABLE" and "test-key" not in exc.value.message


# --- context isolation reaches the prompt ----------------------------------------------------------------

def test_the_insurance_prompt_carries_no_banking_data(sample, monkeypatch):
    client = Client([Resp(text="ok")])
    chat(sample, monkeypatch, client, message="What does my policy cover?", ctx="insurance")
    prompt = str(client.requests[0]["config"].system_instruction).lower()
    for banned in ("swiggy", "zomato", "croma", "salary", "transactions", "merchant"):
        assert banned not in prompt, f"insurance context leaked {banned!r}"
