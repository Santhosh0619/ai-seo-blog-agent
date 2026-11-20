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
            self.wfile.write(b"<h2>Done. You can close this tab.</h2><p>Go back to the terminal.</p>")
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
