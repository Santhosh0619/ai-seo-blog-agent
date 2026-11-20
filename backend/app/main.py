import asyncio
import base64
import io
import json
import logging
import re
import zipfile
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, db, mailer, page, safeurl
from .agent import run_agent
from .auth import current_user, public_base
from .config import PRODUCT_NAME, ROOT, settings, startup_report
from .errors import (BUSY, FORBIDDEN, INVALID_API_KEY, MISSING_API_KEY, NOT_FOUND, SERVER_BUSY, AppError)
from .llm import current_key, run_key
from .models import BlogRequest

# Anything that looks like an API key is redacted from every log line, whatever the source.
_KEYLIKE = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{20,}|GOCSPX-[0-9A-Za-z_\-]{10,}|1//[0-9A-Za-z_\-]{20,}|postgres(?:ql)?://\S+)")


class _Redact(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        red = _KEYLIKE.sub("[REDACTED]", msg)
        for s in (settings.gemini_api_key, settings.db_password, settings.gmail_client_secret, settings.gmail_refresh_token, current_key()):
            if s and len(s) >= 8:
                red = red.replace(s, "[REDACTED]")
        if red != msg:
            record.msg, record.args = red, ()
        return True


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for h in logging.getLogger().handlers:
    h.addFilter(_Redact())
for _n in ("httpx", "httpx2", "google_genai", "httpcore"):
    logging.getLogger(_n).setLevel(logging.WARNING)  # request URLs can carry query strings
log = logging.getLogger("seo.api")
_active: set[int] = set()  # users with a run in progress (one run per user, a few at a time overall)


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_report()
    try:
        await asyncio.to_thread(db.init)
    except AppError:
        log.error("Database not reachable. Start it with: docker compose up -d db")
    yield
    db.close()


app = FastAPI(title=f"{PRODUCT_NAME} API", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Content-Type", "X-Gemini-Key"])

APP_CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
           "frame-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
PAGE_CSP = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"


@app.middleware("http")
async def security(request: Request, call_next):
    # CSRF defence in depth (cookies are also SameSite=Lax): state-changing API calls must come from our own origin.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin:
            host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
            if urlparse(origin).netloc != host and origin not in settings.cors_origins and origin != settings.public_url:
                return JSONResponse(FORBIDDEN.to_dict(), status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if "Content-Security-Policy" not in resp.headers and (resp.headers.get("content-type", "").startswith("text/html")):
        resp.headers["Content-Security-Policy"] = APP_CSP
    return resp


app.include_router(auth.router)


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    return JSONResponse(exc.to_dict(), status_code=exc.status)


def _sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.get("/health")
async def health():
    ok = await asyncio.to_thread(db.ping)
    return {"status": "ok" if ok else "degraded", "db_connected": ok, "shared_key": settings.key_configured}


@app.get("/api/meta")
async def meta():
    return {"product": PRODUCT_NAME, "google": settings.google_enabled, "email_reset": mailer.configured(), "free_runs_per_day": settings.free_runs_per_day, "model": settings.llm_model}


@app.get("/api/quota")
async def quota(user: dict = Depends(current_user)):
    s = await asyncio.to_thread(db.free_status, user["id"])
    return {**s, "free_available": settings.key_configured and s["left"] > 0 and s["capacity_left"] > 0}


# ---- creating a blog (Server-Sent Events) ----------------------------------------------------------------
@app.post("/api/blog/create")
async def create_blog(request: Request, req: BlogRequest, user: dict = Depends(current_user)):
    own = (request.headers.get("x-gemini-key") or "").strip()
    if own and not re.fullmatch(r"[A-Za-z0-9._\-]{20,200}", own):
        raise INVALID_API_KEY
    if not own and not settings.key_configured:
        raise MISSING_API_KEY
    origin = safeurl.normalize_site(req.site_url)
    req.site_url = origin
    uid = user["id"]
    if uid in _active:
        raise BUSY
    if len(_active) >= settings.max_concurrent_runs:
        raise SERVER_BUSY
    run_id = await asyncio.to_thread(db.start_run, uid, req.topic, bool(own))  # raises FREE_LIMIT / FREE_CAPACITY when free runs are used up
    _active.add(uid)

    async def stream():
        status = "failed"
        run_key.set(own or None)  # held for this run only; never stored or logged
        try:
            async for ev in run_agent(req, uid, origin):
                if ev["event"] == "done":
                    status = "done"
                yield _sse(ev["event"], ev["data"])
        finally:
            _active.discard(uid)
            try:
                await asyncio.shield(asyncio.to_thread(db.finish_run, run_id, status))
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---- the user's own pages (everything is scoped by user id) ------------------------------------------------
@app.get("/api/pages")
async def pages(user: dict = Depends(current_user)):
    return {"pages": await asyncio.to_thread(db.list_pages, user["id"])}


async def _own_page(user: dict, page_id: int) -> dict:
    p = await asyncio.to_thread(db.get_page, user["id"], page_id)
    if not p:
        raise NOT_FOUND  # also returned for other people's pages: their existence is never revealed
    return p


@app.get("/api/pages/{page_id}")
async def page_detail(page_id: int, request: Request, user: dict = Depends(current_user)):
    p = await _own_page(user, page_id)
    imgs = await asyncio.to_thread(db.page_images, p["id"])
    p["images"] = [{**i, "url": f"/img/{i['token']}"} for i in imgs]
    p["share_url"] = f"{public_base(request)}/s/{p['share_token']}" if p["share_token"] else None
    p["words"] = page.word_count(p["post"])
    del p["share_token"]
    return p


@app.get("/api/pages/{page_id}/preview", response_class=HTMLResponse)
async def page_preview(page_id: int, request: Request, user: dict = Depends(current_user)):
    p = await _own_page(user, page_id)
    imgs = await asyncio.to_thread(db.page_images, p["id"])
    return HTMLResponse(page.render_article(p, imgs, "preview"), headers={"Content-Security-Policy": PAGE_CSP})


class ShareBody(BaseModel):
    enabled: bool


@app.post("/api/pages/{page_id}/share")
async def page_share(page_id: int, body: ShareBody, request: Request, user: dict = Depends(current_user)):
    await _own_page(user, page_id)
    token = await asyncio.to_thread(db.set_share, user["id"], page_id, body.enabled)
    return {"share_url": f"{public_base(request)}/s/{token}" if token else None}


@app.delete("/api/pages/{page_id}")
async def page_delete(page_id: int, user: dict = Depends(current_user)):
    if not await asyncio.to_thread(db.delete_page, user["id"], page_id):
        raise NOT_FOUND
    return {"ok": True}


@app.get("/api/pages/{page_id}/export")
async def page_export(page_id: int, format: str = "html", user: dict = Depends(current_user)):
    p = await _own_page(user, page_id)
    imgs = await asyncio.to_thread(db.page_images, p["id"])
    slug = re.sub(r"[^a-z0-9-]", "", p["slug"]) or "page"
    if format == "json":
        data = {k: p[k] for k in ("topic", "title", "meta_description", "primary_keyword", "secondary_keywords", "post", "plan", "research", "checks", "score", "score_before", "created_at")}
        return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{slug}.json"'})
    if format == "md":
        return Response(page.to_markdown(p), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}.md"'})
    html = page.render_article(p, imgs, "export")
    blobs = {}
    for i in imgs:
        got = await asyncio.to_thread(db.image_bytes, i["token"])
        if got:
            blobs[i["idx"] + 1] = got[1]
    if format == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html", html)
            for n, b in blobs.items():
                z.writestr(f"images/{n}.webp", b)
        return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'})
    for n, b in blobs.items():  # single self-contained file: images inlined
        html = html.replace(f"images/{n}.webp", "data:image/webp;base64," + base64.b64encode(b).decode())
    return Response(html, media_type="text/html; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}.html"'})


# ---- public share links and images (unguessable tokens) ------------------------------------------------------
@app.get("/s/{token}", response_class=HTMLResponse)
async def shared_page(token: str, request: Request):
    p = await asyncio.to_thread(db.get_page_by_share, token)
    if not p:
        return HTMLResponse("<!doctype html><meta charset=utf-8><title>Not found</title><p style='font:18px system-ui;padding:40px'>This link is no longer shared.</p>", status_code=404)
    imgs = await asyncio.to_thread(db.page_images, p["id"])
    return HTMLResponse(page.render_article(p, imgs, "share", public_base(request)), headers={"Content-Security-Policy": PAGE_CSP})


@app.get("/img/{token}")
async def image(token: str):
    got = await asyncio.to_thread(db.image_bytes, token)
    if not got:
        return Response(status_code=404)
    return Response(got[1], media_type=got[0], headers={"Cache-Control": "public, max-age=86400, immutable", "X-Content-Type-Options": "nosniff"})


# ---- account -------------------------------------------------------------------------------------------------------
@app.get("/api/account/export")
async def account_export(user: dict = Depends(current_user)):
    rows = await asyncio.to_thread(db.list_pages, user["id"], 1000)
    full = []
    for r in rows:
        p = await asyncio.to_thread(db.get_page, user["id"], r["id"])
        if p:
            p.pop("share_token", None)
            full.append(p)
    return Response(json.dumps({"user": auth.public_user(user), "pages": full}, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="my-data.json"'})


@app.delete("/api/account")
async def account_delete(user: dict = Depends(current_user)):
    await asyncio.to_thread(db.delete_user, user["id"])
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


# ---- React build (production): served by the same app -----------------------------------------------------------------
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(NOT_FOUND.to_dict(), status_code=404)
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
