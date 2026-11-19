"""The one function the agent uses to call Gemini: structured output + timeout + bounded retry + model fallback.

The key used for a run is held in a ContextVar for that run only. It is never written to the database,
logs, events or error messages.
"""
import asyncio
import hashlib
import logging
import time
from contextvars import ContextVar

from pydantic import BaseModel

from .config import settings
from .errors import INVALID_API_KEY, MISSING_API_KEY, RATE_LIMITED, UPSTREAM_ERROR, AppError, map_exception

log = logging.getLogger("seo.llm")
BACKOFF = [1.0, 3.0]
RATE_LIMIT_WAIT = 4.0

# Circuit breaker: a model that just failed is tried last for a few minutes, so one overloaded model does not slow every call.
# Overload/timeouts are global; quota (429) is per key, because another key may still have quota.
_bad: dict[tuple[str, str], float] = {}


def _kid(scope_key: bool) -> str:
    return hashlib.sha256(current_key().encode()).hexdigest()[:8] if scope_key else "*"


def _mark_bad(model: str, err: AppError) -> None:
    secs = 600 if err is RATE_LIMITED else 150
    _bad[(_kid(err is RATE_LIMITED), model)] = time.time() + secs


def _is_bad(model: str) -> bool:
    now = time.time()
    return _bad.get(("*", model), 0) > now or _bad.get((_kid(True), model), 0) > now


# The Gemini key for the current run (the user's own key, or None to use the shared key).
run_key: ContextVar[str | None] = ContextVar("run_key", default=None)


def current_key() -> str:
    return run_key.get() or (settings.gemini_api_key if settings.key_configured else "")


def _wait_for(err: AppError, attempt: int, retries: int, last_model: bool) -> float | None:
    if err is RATE_LIMITED:  # free-tier limits are per model: move on to the next model, else wait once
        return RATE_LIMIT_WAIT if (attempt == 0 and last_model) else None
    if err.transient and attempt < retries:
        return BACKOFF[min(attempt, len(BACKOFF) - 1)]
    return None


async def structured(schema: type[BaseModel], system: str, user: str, temperature: float = 0.5, timeout: float | None = None) -> BaseModel:
    """Return a validated `schema` instance. Tries the main model, then the fallback models."""
    if not current_key():
        raise MISSING_API_KEY
    configured = [settings.llm_model, *[m for m in settings.fallback_models if m != settings.llm_model]]
    models = [m for m in configured if not _is_bad(m)] + [m for m in configured if _is_bad(m)]
    last: AppError = UPSTREAM_ERROR
    for i, model in enumerate(models):
        final = i == len(models) - 1
        try:
            return await _call(model, schema, system, user, temperature, timeout or settings.llm_timeout, retries=settings.max_retries if final else 0, final=final)
        except AppError as err:
            if err in (INVALID_API_KEY, MISSING_API_KEY):
                raise
            last = err
            _mark_bad(model, err)
            log.warning("model %s failed (%s)%s", model, err.code, "" if final else ", trying the next model")
    raise last


async def _call(model: str, schema: type[BaseModel], system: str, user: str, temperature: float, timeout: float, retries: int, final: bool) -> BaseModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=model, google_api_key=current_key(), temperature=temperature,
        timeout=timeout, max_retries=0, max_output_tokens=8192,
    ).with_structured_output(schema)
    attempt = 0
    while True:
        try:
            res = await asyncio.wait_for(llm.ainvoke([("system", system), ("human", user)]), timeout + 5)
            if res is None:
                raise UPSTREAM_ERROR
            return res if isinstance(res, schema) else schema.model_validate(res)
        except Exception as exc:  # noqa: BLE001
            err = map_exception(exc)
            wait = _wait_for(err, attempt, retries, final)
            log.warning("LLM call failed on %s (%s), attempt %d", model, err.code, attempt + 1)
            if wait is None:
                raise err from exc
            await asyncio.sleep(wait)
            attempt += 1
