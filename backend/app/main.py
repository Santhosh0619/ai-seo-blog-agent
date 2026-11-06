import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, page
from .agent import run_agent
from .config import ROOT, settings, startup_report
from .errors import BUSY, MISSING_API_KEY, RUN_LIMIT, AppError


class _Redact(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in (settings.gemini_api_key, settings.db_password):
            if s and len(s) >= 8 and s in msg:
                record.msg, record.args = msg.replace(s, "[REDACTED]"), ()
        return True


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for h in logging.getLogger().handlers:
    h.addFilter(_Redact())
log = logging.getLogger("seo.api")
_lock = asyncio.Lock()  # one blog at a time (protects the free quota)


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_report()
    try:
        await asyncio.to_thread(db.init)
    except AppError:
        log.error("Database not reachable. Start it with: docker compose up -d")
    yield
    db.close()


app = FastAPI(title="Appin SEO Blog Agent", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    return JSONResponse(exc.to_dict(), status_code=exc.status)


def _sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.get("/health")
async def health():
    ok = await asyncio.to_thread(db.ping)
    return {"status": "ok" if ok and settings.key_configured else "degraded",
            "llm_configured": settings.key_configured, "db_connected": ok}


@app.get("/api/meta")
async def meta():
    return {"model": settings.llm_model, "max_runs_per_hour": settings.max_runs_per_hour}


@app.get("/api/pages")
async def pages():
    return {"pages": await asyncio.to_thread(db.list_pages)}


@app.post("/api/blog/create")
async def create_blog(request: Request):
    # fail fast with proper HTTP errors BEFORE streaming (key check first, always)
    if not settings.key_configured:
        raise MISSING_API_KEY
    if _lock.locked():
        raise BUSY
    if not await asyncio.to_thread(db.record_run_if_allowed, settings.max_runs_per_hour):
        raise RUN_LIMIT

    async def stream():
        async with _lock:
            async for ev in run_agent():
                yield _sse(ev["event"], ev["data"])

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---- generated blog pages (real server-rendered HTML) ------------------------------------------
@app.get("/blog", response_class=HTMLResponse)
async def blog_index():
    return page.build_index(await asyncio.to_thread(db.list_pages))


@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_page(slug: str, request: Request):
    html = await asyncio.to_thread(db.get_html, slug)
    if html is None:
        return HTMLResponse("<h1>Page not found</h1><p><a href='/blog'>Back to the blog</a></p>", status_code=404)
    return HTMLResponse(html.replace(page.BASE, str(request.base_url).rstrip("/")))


# ---- React build (production): served by the same app ------------------------------------------
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
