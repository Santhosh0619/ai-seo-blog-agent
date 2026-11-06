"""Typed, friendly errors. Any provider/network failure is mapped to one of these."""
import asyncio
import socket

import httpx


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 500, transient: bool = False):
        super().__init__(message)
        self.code, self.message, self.status, self.transient = code, message, status, transient

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


MISSING_API_KEY = AppError("MISSING_API_KEY", "The AI service isn't configured. Add GEMINI_API_KEY to the .env file and restart the server.", 503)
INVALID_API_KEY = AppError("INVALID_API_KEY", "The AI service rejected the API key. Please check that GEMINI_API_KEY is correct.", 401)
RATE_LIMITED = AppError("RATE_LIMITED", "The free AI usage limit was reached. Please wait a minute and try again.", 429)
TIMEOUT = AppError("TIMEOUT", "The AI service took too long to respond. Please try again.", 504, transient=True)
UPSTREAM_ERROR = AppError("UPSTREAM_ERROR", "Something went wrong while talking to the AI service. Please try again in a moment.", 502, transient=True)
DB_UNAVAILABLE = AppError("DB_UNAVAILABLE", "The database is unavailable right now. Please try again shortly.", 503)
BUSY = AppError("BUSY", "A blog is already being created. Please wait for it to finish.", 409)
RUN_LIMIT = AppError("RUN_LIMIT", "The hourly limit for blog creation was reached (this protects the free AI quota). Please try again later.", 429)


def map_exception(exc: BaseException) -> AppError:
    if isinstance(exc, AppError):
        return exc
    chain, cur = [], exc
    while cur is not None and len(chain) < 6:
        chain.append(cur)
        cur = cur.__cause__ or cur.__context__
    text = " ".join(f"{type(e).__name__} {e}" for e in chain).lower()
    if any(isinstance(e, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)) for e in chain) \
            or "timed out" in text or "deadline" in text:
        return TIMEOUT
    if "api_key_invalid" in text or "api key not valid" in text or "invalid api key" in text \
            or "permission_denied" in text or "unauthenticated" in text or " 401" in text or " 403" in text:
        return INVALID_API_KEY
    if "resource_exhausted" in text or "quota" in text or "rate limit" in text or " 429" in text \
            or "too many requests" in text:
        return RATE_LIMITED
    return UPSTREAM_ERROR
