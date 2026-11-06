"""The one function the agent uses to call Gemini: structured output + timeout + bounded retry + model fallback."""
import asyncio
import logging

from pydantic import BaseModel

from .config import settings
from .errors import INVALID_API_KEY, MISSING_API_KEY, RATE_LIMITED, UPSTREAM_ERROR, AppError, map_exception

log = logging.getLogger("seo.llm")
BACKOFF = [1.0, 3.0]
RATE_LIMIT_WAIT = 4.0


def _wait_for(err: AppError, attempt: int, retries: int, last_model: bool) -> float | None:
    if err is RATE_LIMITED:  # free-tier limits are per model: move on to the next model, else wait once
        return RATE_LIMIT_WAIT if (attempt == 0 and last_model) else None
    if err.transient and attempt < retries:
        return BACKOFF[min(attempt, len(BACKOFF) - 1)]
    return None


async def structured(schema: type[BaseModel], system: str, user: str) -> BaseModel:
    """Return a validated `schema` instance. Tries the main model, then the fallback models."""
    if not settings.key_configured:
        raise MISSING_API_KEY
    models = [settings.llm_model, *[m for m in settings.fallback_models if m != settings.llm_model]]
    last: AppError = UPSTREAM_ERROR
    for i, model in enumerate(models):
        final = i == len(models) - 1
        try:
            return await _call(model, schema, system, user, retries=settings.max_retries if final else 1, final=final)
        except AppError as err:
            if err in (INVALID_API_KEY, MISSING_API_KEY):
                raise
            last = err
            log.warning("model %s failed (%s)%s", model, err.code, "" if final else ", trying the next model")
    raise last


async def _call(model: str, schema: type[BaseModel], system: str, user: str, retries: int, final: bool) -> BaseModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=model, google_api_key=settings.gemini_api_key, temperature=0.5,
        timeout=settings.llm_timeout, max_retries=0, max_output_tokens=8192,
    ).with_structured_output(schema)
    attempt = 0
    while True:
        try:
            res = await asyncio.wait_for(llm.ainvoke([("system", system), ("human", user)]), settings.llm_timeout + 5)
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
