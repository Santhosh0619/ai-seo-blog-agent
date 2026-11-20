"""Send email through the Gmail API over HTTPS (free; works on hosts that block SMTP).

Mail is sent from the owner's own Gmail account, so it is authenticated by Google itself (SPF/DKIM) and lands in the inbox,
not in spam. Credentials come from environment variables and are never logged.
"""
import base64
import logging
import time
from email.message import EmailMessage

import httpx

from .config import PRODUCT_NAME, settings

log = logging.getLogger("seo.mail")
_token: dict = {"value": "", "until": 0.0}


def configured() -> bool:
    return settings.email_enabled


async def _access_token(client: httpx.AsyncClient) -> str:
    if _token["value"] and time.time() < _token["until"] - 60:
        return _token["value"]
    r = await client.post("https://oauth2.googleapis.com/token", timeout=15, data={
        "client_id": settings.gmail_client_id, "client_secret": settings.gmail_client_secret,
        "refresh_token": settings.gmail_refresh_token, "grant_type": "refresh_token"})
    r.raise_for_status()
    body = r.json()
    _token.update(value=body["access_token"], until=time.time() + int(body.get("expires_in", 3000)))
    return _token["value"]


def build_message(to: str, subject: str, text: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{PRODUCT_NAME} <{settings.gmail_sender}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


async def send_mail(to: str, subject: str, text: str, html: str) -> bool:
    """Returns True when Gmail accepted the message. Never raises."""
    if not configured():
        return False
    try:
        raw = base64.urlsafe_b64encode(build_message(to, subject, text, html).as_bytes()).decode()
        async with httpx.AsyncClient() as client:
            token = await _access_token(client)
            r = await client.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", timeout=20,
                                  headers={"Authorization": f"Bearer {token}"}, json={"raw": raw})
        if r.status_code != 200:
            log.warning("Gmail API refused the message (HTTP %s)", r.status_code)
            _token["value"] = ""
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("sending email failed (%s)", type(exc).__name__)
        _token["value"] = ""
        return False


def reset_email(link: str, minutes: int = 30) -> tuple[str, str, str]:
    subject = f"Reset your {PRODUCT_NAME} password"
    text = (f"Hi,\n\nSomeone asked to reset the password for your {PRODUCT_NAME} account.\n\nOpen this link to choose a new password "
            f"(valid for {minutes} minutes, one use):\n{link}\n\nIf this was not you, ignore this email: your password stays the same.\n")
    html = (f'<div style="font:16px/1.6 system-ui,Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;color:#14161c">'
            f'<h2 style="margin:0 0 12px">Reset your password</h2>'
            f"<p>Someone asked to reset the password for your {PRODUCT_NAME} account.</p>"
            f'<p><a href="{link}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:10px">Choose a new password</a></p>'
            f'<p style="color:#5e6577;font-size:14px">The link is valid for {minutes} minutes and works once. If the button does not work, copy this address into your browser:<br>{link}</p>'
            f'<p style="color:#5e6577;font-size:14px">If this was not you, ignore this email. Your password stays the same.</p></div>')
    return subject, text, html


def google_only_email() -> tuple[str, str, str]:
    subject = f"Signing in to {PRODUCT_NAME}"
    text = (f"Hi,\n\nSomeone asked to reset a password for your {PRODUCT_NAME} account, but your account signs in with Google "
            f"and has no password. Open the sign-in page and click \"Continue with Google\" with this email address.\n\nIf this was not you, ignore this email.\n")
    html = (f'<div style="font:16px/1.6 system-ui,Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;color:#14161c">'
            f"<h2>Your account signs in with Google</h2><p>Someone asked to reset a password for your {PRODUCT_NAME} account, "
            f"but your account has no password. Open the sign-in page and click <b>Continue with Google</b> using this email address.</p>"
            f'<p style="color:#5e6577;font-size:14px">If this was not you, ignore this email.</p></div>')
    return subject, text, html
