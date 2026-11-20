"""One-time helper: let the site owner allow "send email as me" and save the long-lived refresh token to a local file.

Run it inside Docker so nothing needs to be installed (the project root is mounted at /app):

    docker compose --profile dev run --rm -p 127.0.0.1:8765:8765 app python scripts/gmail_authorize.py

It reads GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET from .env, prints a Google sign-in address, waits for Google to call back on
http://127.0.0.1:8765, and writes the refresh token to `.gmail_refresh_token` in the project root (git-ignored).
The token is NEVER printed. Copy it from that file into the Render environment variable GMAIL_REFRESH_TOKEN, then delete the file.
"""
import base64
import hashlib
import http.server
import os
import secrets
import sys
import threading
import urllib.parse
from pathlib import Path

import httpx

PORT = 8765
SCOPE = "https://www.googleapis.com/auth/gmail.send"
OUT = Path(__file__).resolve().parents[2] / ".gmail_refresh_token"
REDIRECT = f"http://127.0.0.1:{PORT}"


DONE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Email permission saved</title><style>
:root{color-scheme:light dark}*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;font:16px/1.6 system-ui,Segoe UI,Arial,sans-serif;background:#f7f6f3;color:#14161c;padding:24px}
@media(prefers-color-scheme:dark){body{background:#0b0d13;color:#eceef6}.card{background:#141824!important;border-color:#242a3a!important}p{color:#a2a9bd!important}}
.card{max-width:440px;text-align:center;background:#fff;border:1px solid #e4e1da;border-radius:22px;padding:38px 32px;box-shadow:0 24px 60px -28px rgba(60,50,140,.4)}
.ok{width:64px;height:64px;border-radius:50%;margin:0 auto 18px;display:grid;place-items:center;color:#fff;font-size:32px;background:linear-gradient(135deg,#4f46e5,#8b5cf6 55%,#d946ef)}
h1{margin:0 0 8px;font-size:1.5rem;letter-spacing:-.02em}p{margin:0 0 10px;color:#5e6577}
.hint{margin-top:18px;font-size:14px}
</style></head><body><main class="card"><div class="ok">&#10003;</div>
<h1>All set</h1><p>Rankwise can now send password reset emails from your Gmail address.</p>
<p>You can close this tab and go back to the app. The next steps are in your chat with Claude.</p>
<p class="hint">You can cancel this permission any time at myaccount.google.com/permissions.</p></main></body></html>""".encode("utf-8")


def main() -> int:
    cid, secret = os.getenv("GMAIL_CLIENT_ID", "").strip(), os.getenv("GMAIL_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env first.")
        return 1
    state = secrets.token_urlsafe(16)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE, "state": state,
        "access_type": "offline", "prompt": "consent", "code_challenge": challenge, "code_challenge_method": "S256"})
    result: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state or "code" not in q:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Waiting for the Google sign-in. If you see this, start again.")
                return
            result["code"] = q["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DONE_PAGE)
            done.set()

        def log_message(self, *args):  # keep the authorization code out of the logs
            pass

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("OPEN_THIS_ADDRESS_IN_CHROME:\n" + url + "\n", flush=True)
    if not done.wait(timeout=600):
        print("Timed out waiting for Google.")
        return 1
    server.shutdown()
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
        "client_id": cid, "client_secret": secret, "code": result["code"], "code_verifier": verifier,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
    body = r.json()
    if r.status_code != 200 or not body.get("refresh_token"):
        print("Google did not return a refresh token:", body.get("error", r.status_code), body.get("error_description", ""))
        return 1
    OUT.write_text(body["refresh_token"], encoding="utf-8")
    print(f"SAVED: refresh token written to {OUT.name} (not shown). Copy it into Render as GMAIL_REFRESH_TOKEN, then delete the file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
