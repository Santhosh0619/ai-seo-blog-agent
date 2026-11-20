"""Typed, friendly errors. Any provider/network failure is mapped to one of these."""
import asyncio

import httpx


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 500, transient: bool = False, needs_key: bool = False):
        super().__init__(message)
        self.code, self.message, self.status, self.transient, self.needs_key = code, message, status, transient, needs_key

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "needs_key": self.needs_key}}


MISSING_API_KEY = AppError("MISSING_API_KEY", "Free runs are not available right now. Add your own free Gemini key in Advanced settings to continue.", 503, needs_key=True)
INVALID_API_KEY = AppError("INVALID_API_KEY", "Gemini rejected the API key. Please check the key and try again.", 401, needs_key=True)
RATE_LIMITED = AppError("RATE_LIMITED", "The Gemini free usage limit was reached. Wait a minute, or add your own free Gemini key.", 429, needs_key=True)
TIMEOUT = AppError("TIMEOUT", "The AI service took too long to respond. Please try again.", 504, transient=True)
UPSTREAM_ERROR = AppError("UPSTREAM_ERROR", "Something went wrong while talking to the AI service. Please try again in a moment.", 502, transient=True)
DB_UNAVAILABLE = AppError("DB_UNAVAILABLE", "The database is unavailable right now. Please try again shortly.", 503)
BUSY = AppError("BUSY", "You already have a blog being created. Please wait for it to finish.", 409)
SERVER_BUSY = AppError("SERVER_BUSY", "The server is busy with other blogs. Please try again in a minute.", 503)
FREE_LIMIT = AppError("FREE_LIMIT", "You used your free runs for today. Add your own free Gemini key to keep creating blogs.", 429, needs_key=True)
FREE_CAPACITY = AppError("FREE_CAPACITY", "Today's free capacity is used up. Add your own free Gemini key to continue.", 429, needs_key=True)
AUTH_REQUIRED = AppError("AUTH_REQUIRED", "Please sign in to continue.", 401)
BAD_CREDENTIALS = AppError("BAD_CREDENTIALS", "Email or password is not correct.", 401)
EMAIL_TAKEN = AppError("EMAIL_TAKEN", "An account with this email already exists. Try signing in.", 409)
WEAK_INPUT = AppError("WEAK_INPUT", "Please enter a valid email and a password of at least 8 characters.", 422)
TOO_MANY = AppError("TOO_MANY", "Too many attempts. Please wait a few minutes and try again.", 429)
EMAIL_OFF = AppError("EMAIL_OFF", "Password reset by email is not set up on this server yet.", 503)
BAD_RESET = AppError("BAD_RESET", "This reset link is invalid or has expired. Please request a new one.", 400)
NOT_FOUND = AppError("NOT_FOUND", "We could not find that page.", 404)
FORBIDDEN = AppError("FORBIDDEN", "This request was blocked for security reasons.", 403)
BAD_SITE = AppError("BAD_SITE", "That website address cannot be used. Enter a public http(s) address, for example https://example.com.", 422)
BAD_INPUT = AppError("BAD_INPUT", "Please check the form: the topic is required (3 to 120 characters).", 422)


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
