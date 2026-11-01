import importlib.util

import pytest
from pydantic import BaseModel

from app import llm
from helpers import HANG, api_error, blocked_reply, prompt_blocked_reply, reply, run

ALL_MODELS = ["model-primary", "model-backup-1", "model-backup-2"]


class Schema(BaseModel):
    value: int


def test_generate_returns_text(gemini):
    gemini.script(reply("hello"))
    assert run(llm.generate("prompt", system="be brief")) == "hello"
    call = gemini.calls[0]
    assert (call.model, call.contents) == ("model-primary", "prompt")
    assert call.config.system_instruction == "be brief"
    assert call.config.response_mime_type is None


def test_generate_disables_automatic_function_calling(gemini):
    run(llm.generate("p"))
    assert gemini.calls[0].config.automatic_function_calling.disable is True


def test_generate_joins_a_reply_split_into_parts(gemini):
    parts = [{"text": "Hello "}, {"text": "world"}]
    gemini.script({"candidates": [{"content": {"role": "model", "parts": parts}}]})
    assert run(llm.generate("p")) == "Hello world"


def test_generate_returns_parsed_schema(gemini):
    gemini.script(reply(data={"value": 1}))
    assert run(llm.generate("p", schema=Schema)) == Schema(value=1)
    assert gemini.calls[0].config.response_mime_type == "application/json"


@pytest.mark.parametrize("bad_reply", [reply("not json"), reply(data={"value": "many"}), reply(data={}), blocked_reply()])
def test_generate_rejects_output_that_does_not_match_schema(gemini, bad_reply):
    gemini.script(bad_reply)
    with pytest.raises(llm.LLMError, match="did not match"):
        run(llm.generate("p", schema=Schema))


@pytest.mark.parametrize("empty", [reply(""), blocked_reply(), blocked_reply("MAX_TOKENS"), prompt_blocked_reply()])
def test_generate_rejects_an_empty_response(gemini, empty):
    gemini.script(empty)
    with pytest.raises(llm.LLMError, match="empty response"):
        run(llm.generate("p"))


@pytest.mark.parametrize("code", [429, 500, 503, 504])
def test_retryable_error_moves_to_the_next_model(gemini, code):
    gemini.script(api_error(code), reply("from backup"))
    assert run(llm.generate("p")) == "from backup"
    assert gemini.models_tried == ALL_MODELS[:2]


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_non_retryable_error_stops_immediately(gemini, sleeps, code):
    gemini.script(api_error(code))
    with pytest.raises(llm.LLMError):
        run(llm.generate("p"))
    assert gemini.models_tried == ALL_MODELS[:1]
    assert sleeps == []


def test_two_full_passes_with_a_pause_before_giving_up(gemini, sleeps):
    gemini.script(api_error(429))
    with pytest.raises(llm.LLMError, match="rate limit or quota"):
        run(llm.generate("p"))
    assert gemini.models_tried == ALL_MODELS * 2
    assert sleeps == [3]


def test_second_pass_can_succeed(gemini):
    gemini.script(api_error(503), api_error(503), api_error(503), reply("recovered"))
    assert run(llm.generate("p")) == "recovered"
    assert len(gemini.calls) == 4


def test_primary_model_is_not_tried_twice_when_also_a_fallback(gemini, monkeypatch):
    monkeypatch.setattr(llm, "GEMINI_FALLBACK_MODELS", ["model-primary", "other"])
    gemini.script(api_error(503), reply("ok"))
    run(llm.generate("p"))
    assert gemini.models_tried == ["model-primary", "other"]


def test_hanging_model_times_out_and_the_next_answers(gemini, monkeypatch):
    monkeypatch.setattr(llm, "MODEL_TIMEOUT_S", 0.3)  # also bounds the healthy model, so not too tight
    gemini.by_model = {"model-primary": HANG}
    gemini.script(reply("from backup"))
    assert run(llm.generate("p")) == "from backup"
    assert gemini.models_tried == ALL_MODELS[:2]


def test_all_models_hanging_gives_up_after_one_pass(gemini, monkeypatch, sleeps):
    monkeypatch.setattr(llm, "MODEL_TIMEOUT_S", 0.01)
    gemini.script(HANG)
    with pytest.raises(llm.LLMError, match="did not respond in time"):
        run(llm.generate("p"))
    assert gemini.models_tried == ALL_MODELS
    assert sleeps == []


def test_timed_out_models_are_skipped_on_the_second_pass(gemini, monkeypatch):
    monkeypatch.setattr(llm, "MODEL_TIMEOUT_S", 0.01)
    gemini.by_model = {"model-primary": HANG, "model-backup-1": api_error(503), "model-backup-2": api_error(503)}
    with pytest.raises(llm.LLMError, match="temporarily unavailable"):
        run(llm.generate("p"))
    assert gemini.models_tried == ALL_MODELS + ALL_MODELS[1:]


def test_every_model_answers_within_the_documented_40_seconds():
    assert 0 < llm.MODEL_TIMEOUT_S <= 40


@pytest.mark.parametrize(
    "code, message, expected",
    [
        (429, "x", "rate limit or quota"),
        (500, "x", "temporarily unavailable"),
        (503, "x", "temporarily unavailable"),
        (504, "x", "temporarily unavailable"),
        (400, "API key not valid", "rejected the API key"),
        (401, "API key expired", "rejected the API key"),
        (403, "bad API key", "rejected the API key"),
        (400, "Invalid argument", "Gemini error 400: Invalid argument"),
        (404, "no such model", "Gemini error 404: no such model"),
    ],
)
def test_readable_error_messages(code, message, expected):
    assert expected in str(llm._readable(api_error(code, message)))


def test_fresh_process_without_a_key_gets_a_readable_error(monkeypatch):
    """Loads a second copy of the module, because the fixtures reset the first copy's client."""
    monkeypatch.setattr(llm.genai, "Client", type("Client", (), {}))  # the module annotates with this type
    spec = importlib.util.spec_from_file_location("app.llm_fresh", llm.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    with pytest.raises(fresh.LLMError, match="GEMINI_API_KEY is not set"):
        fresh._get_client()


def test_missing_key_is_a_readable_error():
    with pytest.raises(llm.LLMError, match="GEMINI_API_KEY is not set"):
        run(llm.generate("p"))


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
def test_client_is_built_once_when_a_key_exists(monkeypatch, name):
    built = []
    monkeypatch.setenv(name, "test-key")
    monkeypatch.setattr(llm.genai, "Client", lambda: built.append(1) or object())
    assert llm._get_client() is llm._get_client()
    assert len(built) == 1


@pytest.mark.xfail(strict=True, raises=ConnectionError, reason="BUG: only APIError is caught; a network failure escapes as a raw exception")
def test_network_failure_becomes_a_readable_error(gemini):
    gemini.script(ConnectionError("network unreachable"))
    with pytest.raises(llm.LLMError):
        run(llm.generate("p"))
