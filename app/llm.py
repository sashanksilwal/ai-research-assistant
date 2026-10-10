"""Gemini client: one place for model config, retries/fallbacks, and readable errors."""
import asyncio
import os

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .config import GEMINI_FALLBACK_MODELS, GEMINI_MODEL

_client: genai.Client | None = None


class LLMError(Exception):
    pass


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        # Check first: constructing a client without a key leaves a half-built object
        # whose cleanup logs an AttributeError traceback.
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            raise LLMError("GEMINI_API_KEY is not set. Add it to .env and restart the server.")
        _client = genai.Client()  # reads GEMINI_API_KEY from the environment
    return _client


def _config(system: str | None, schema: type[BaseModel] | None) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json" if schema else None,
        response_schema=schema,
        # We never pass tools; disabling this also silences the SDK's AFC warning.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


async def generate(prompt: str, system: str | None = None, schema: type[BaseModel] | None = None):
    """Return the response text, or a parsed `schema` instance when one is given."""
    resp = await _generate_with_fallback(prompt, _config(system, schema))
    if schema:
        if resp.parsed is None:
            raise LLMError("Gemini returned output that did not match the expected format.")
        return resp.parsed
    if not resp.text:
        raise LLMError("Gemini returned an empty response.")
    return resp.text


RETRYABLE = {429, 500, 503, 504}
# Some models accept a request and then never answer (seen with gemini-3.8-flash on Oct 10); without a
# limit the request hangs forever. A full-paper summary normally takes 5-20 s.
MODEL_TIMEOUT_S = 40


async def _generate_with_fallback(prompt: str, config: types.GenerateContentConfig):
    """Try each model in turn on 429/5xx or timeout; after a full pass, wait and retry the models that
    returned errors (not the ones that timed out, so the worst case stays around two minutes)."""
    models = [GEMINI_MODEL, *[m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]]
    last_error: LLMError | None = None
    for attempt in range(2):
        if attempt:
            if not models:
                break
            await asyncio.sleep(3)
        for model in list(models):
            try:
                return await asyncio.wait_for(
                    _get_client().aio.models.generate_content(model=model, contents=prompt, config=config),
                    MODEL_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                models.remove(model)
                last_error = LLMError("Gemini did not respond in time. Try again shortly.")
            except errors.APIError as e:
                if e.code not in RETRYABLE:
                    raise _readable(e) from e
                last_error = _readable(e)
    raise last_error


def _readable(e: errors.APIError) -> LLMError:
    if e.code == 429:
        return LLMError("Gemini rate limit or quota reached on all models. Wait a minute and try again.")
    if e.code in (500, 503, 504):
        return LLMError("Gemini is temporarily unavailable (high demand). Try again shortly.")
    if e.code in (400, 401, 403) and "API key" in str(e.message):
        return LLMError("Gemini rejected the API key. Check GEMINI_API_KEY in .env.")
    return LLMError(f"Gemini error {e.code}: {e.message}")
