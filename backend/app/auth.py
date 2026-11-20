"""Sign up, sign in (email + password, or Google), sessions and the current-user dependency.

Passwords: scrypt (standard library) with a random salt. Sessions: random token in an httpOnly, SameSite=Lax cookie;
only a SHA-256 hash of the token is stored. Failed attempts are rate-limited per IP and per email.
"""
import asyncio
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from . import db, mailer
from .config import settings
from .errors import (AUTH_REQUIRED, BAD_CREDENTIALS, BAD_RESET, EMAIL_OFF, EMAIL_TAKEN, TOO_MANY, WEAK_INPUT, AppError)

COOKIE = "sid"
MAX_AGE = 30 * 24 * 3600
router = APIRouter(prefix="/api/auth")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
_hits: dict[str, deque] = defaultdict(deque)


# ---- passwords -------------------------------------------------------------------------------------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(pw: str, stored: str | None) -> bool:
    try:
        _, salt, h = (stored or "").split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, bytes.fromhex(h))
    except (ValueError, TypeError):
        hashlib.scrypt(b"x", salt=b"0" * 16, n=2 ** 14, r=8, p=1, dklen=32)  # keep timing similar for unknown users
        return False


# ---- helpers ---------------------------------------------------------------------------------------
def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?"))


def _limit(key: str, limit: int, window: int = 600) -> None:
    now, q = time.time(), _hits[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        raise TOO_MANY
    q.append(now)


def public_base(request: Request) -> str:
    if settings.public_url:
        return settings.public_url
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    return f"{proto}://{host}"


def _secure(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip() == "https"


def set_session(response, request: Request, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="lax", secure=_secure(request), path="/")


def public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "has_password": bool(u["password_hash"]), "google": bool(u["google_sub"])}


async def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        raise AUTH_REQUIRED
    user = await asyncio.to_thread(db.session_user, token)
    if not user:
        raise AUTH_REQUIRED
    return user


class Creds(BaseModel):
    email: str
    password: str
    name: str = ""


# ---- email + password ------------------------------------------------------------------------------
@router.post("/signup")
async def signup(c: Creds, request: Request):
    email = c.email.strip().lower()
    _limit(f"signup:{client_ip(request)}", 8)
    if not _EMAIL.match(email) or not (8 <= len(c.password) <= 128):
        raise WEAK_INPUT
    pw_hash = await asyncio.to_thread(hash_password, c.password)
    user = await asyncio.to_thread(db.create_user, email, c.name.strip()[:60], pw_hash)
    if not user:
        raise EMAIL_TAKEN
    token = await asyncio.to_thread(db.create_session, user["id"])
    resp = JSONResponse({"user": public_user(user)})
    set_session(resp, request, token)
    return resp


@router.post("/login")
async def login(c: Creds, request: Request):
    email = c.email.strip().lower()
    _limit(f"login-ip:{client_ip(request)}", 20)
    _limit(f"login-email:{email}", 8)
    user = await asyncio.to_thread(db.user_by_email, email)
    ok = await asyncio.to_thread(verify_password, c.password, user["password_hash"] if user else None)
    if not user or not ok:
        raise BAD_CREDENTIALS
    token = await asyncio.to_thread(db.create_session, user["id"])
    resp = JSONResponse({"user": public_user(user)})
    set_session(resp, request, token)
    return resp


# ---- password reset by email ---------------------------------------------------------------------------------
_pending: set = set()  # keeps fire-and-forget mail tasks alive


class Forgot(BaseModel):
    email: str


class Reset(BaseModel):
    token: str
    password: str


async def _send_reset(user: dict, base: str) -> None:
    try:
        if user["password_hash"]:
            token = await asyncio.to_thread(db.create_reset, user["id"])
            subject, text, html = mailer.reset_email(f"{base}/reset#t={token}")  # in the #fragment: it never reaches server logs
        else:
            subject, text, html = mailer.google_only_email()
        await mailer.send_mail(user["email"], subject, text, html)
    except Exception:  # noqa: BLE001
        pass


@router.post("/forgot")
async def forgot(body: Forgot, request: Request):
    if not mailer.configured():
        raise EMAIL_OFF
    email = body.email.strip().lower()
    _limit(f"forgot-ip:{client_ip(request)}", 6)
    _limit(f"forgot-email:{email}", 3)
    if _EMAIL.match(email):
        user = await asyncio.to_thread(db.user_by_email, email)
        if user:  # sent in the background, so the answer is the same (and as fast) whether or not the account exists
            t = asyncio.create_task(_send_reset(user, public_base(request)))
            _pending.add(t)
            t.add_done_callback(_pending.discard)
    return {"ok": True}


@router.post("/reset")
async def reset(body: Reset, request: Request):
    _limit(f"reset-ip:{client_ip(request)}", 12)
    if not (8 <= len(body.password) <= 128):
        raise WEAK_INPUT
    uid = await asyncio.to_thread(db.consume_reset, body.token.strip())
    if uid is None:
        raise BAD_RESET
    pw_hash = await asyncio.to_thread(hash_password, body.password)
    await asyncio.to_thread(db.set_password, uid, pw_hash)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        await asyncio.to_thread(db.delete_session, token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return {"user": public_user(user)}


# ---- Google sign-in (authorization-code flow, server side) -------------------------------------------
GSTATE = "g_state"


@router.get("/google/start")
async def google_start(request: Request):
    if not settings.google_enabled:
        return RedirectResponse("/login?error=google_off")
    state = secrets.token_urlsafe(24)
    qs = urlencode({"client_id": settings.google_client_id, "redirect_uri": f"{public_base(request)}/api/auth/google/callback",
                    "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account"})
    resp = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{qs}")
    resp.set_cookie(GSTATE, state, max_age=600, httponly=True, samesite="lax", secure=_secure(request), path="/api/auth/google")
    return resp


@router.get("/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    def fail(reason: str):
        r = RedirectResponse(f"/login?error={reason}")
        r.delete_cookie(GSTATE, path="/api/auth/google")
        return r

    if not settings.google_enabled or error or not code:
        return fail("google_cancelled")
    saved = request.cookies.get(GSTATE, "")
    if not saved or not hmac.compare_digest(saved, state):
        return fail("google_state")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            tok = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "redirect_uri": f"{public_base(request)}/api/auth/google/callback", "grant_type": "authorization_code"})
            tok.raise_for_status()
            info = await client.get("https://openidconnect.googleapis.com/v1/userinfo",
                                    headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
            info.raise_for_status()
            g = info.json()
    except Exception:  # noqa: BLE001
        return fail("google_failed")
    email = (g.get("email") or "").lower()
    if not g.get("email_verified") or not email or not g.get("sub"):
        return fail("google_email")
    try:
        user = await asyncio.to_thread(db.user_by_google, g["sub"]) or await asyncio.to_thread(db.user_by_email, email)
        if user and not user["google_sub"]:
            await asyncio.to_thread(db.link_google, user["id"], g["sub"], g.get("name", ""))
        if not user:
            user = await asyncio.to_thread(db.create_user, email, (g.get("name") or "")[:60], None, g["sub"])
        token = await asyncio.to_thread(db.create_session, user["id"])
    except AppError:
        return fail("google_failed")
    resp = RedirectResponse("/app", status_code=303)
    resp.delete_cookie(GSTATE, path="/api/auth/google")
    set_session(resp, request, token)
    return resp
