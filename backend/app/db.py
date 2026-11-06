"""Postgres storage for generated pages (sync psycopg pool, called via asyncio.to_thread)."""
import json
from typing import Any

from psycopg_pool import ConnectionPool

from .config import settings
from .errors import DB_UNAVAILABLE, AppError

_pool: ConnectionPool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  meta_description TEXT NOT NULL,
  primary_keyword TEXT NOT NULL,
  secondary_keywords JSONB NOT NULL DEFAULT '[]',
  post JSONB NOT NULL,
  html TEXT NOT NULL,
  seo_score INT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'live',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS runs (
  id SERIAL PRIMARY KEY,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.conninfo, min_size=1, max_size=4, open=False, timeout=8, kwargs={"autocommit": True})
        _pool.open(wait=False)
    return _pool


def close() -> None:
    global _pool
    if _pool:
        _pool.close()
        _pool = None


def _run(fn):
    try:
        with pool().connection(timeout=8) as c:
            return fn(c)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DB_UNAVAILABLE from exc


def init() -> None:
    _run(lambda c: c.execute(SCHEMA))


def ping() -> bool:
    try:
        _run(lambda c: c.execute("SELECT 1").fetchone())
        return True
    except AppError:
        return False


def record_run_if_allowed(limit: int) -> bool:
    def fn(c):
        n = c.execute("SELECT count(*) FROM runs WHERE started_at > now() - interval '1 hour'").fetchone()[0]
        if n >= limit:
            return False
        c.execute("INSERT INTO runs DEFAULT VALUES")
        return True
    return _run(fn)


def unique_slug(slug: str) -> str:
    def fn(c):
        cand, i = slug, 2
        while c.execute("SELECT 1 FROM pages WHERE slug = %s", (cand,)).fetchone():
            cand, i = f"{slug}-{i}", i + 1
        return cand
    return _run(fn)


def save_page(*, slug: str, title: str, meta: str, primary: str, secondary: list[str],
              post: dict[str, Any], html: str, score: int, mode: str = "live") -> None:
    _run(lambda c: c.execute(
        """INSERT INTO pages (slug, title, meta_description, primary_keyword, secondary_keywords, post, html, seo_score, mode)
           VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)""",
        (slug, title, meta, primary, json.dumps(secondary), json.dumps(post), html, score, mode)))


def get_html(slug: str) -> str | None:
    row = _run(lambda c: c.execute("SELECT html FROM pages WHERE slug = %s", (slug,)).fetchone())
    return row[0] if row else None


def list_pages(limit: int = 50) -> list[dict]:
    rows = _run(lambda c: c.execute(
        "SELECT slug, title, meta_description, primary_keyword, seo_score, mode, created_at FROM pages ORDER BY id DESC LIMIT %s", (limit,)).fetchall())
    return [{"slug": r[0], "title": r[1], "meta_description": r[2], "primary_keyword": r[3],
             "seo_score": r[4], "mode": r[5], "created_at": r[6].isoformat()} for r in rows]


def generated_index() -> list[dict]:
    """Title + keyword of pages this agent already created (for cannibalisation checks)."""
    rows = _run(lambda c: c.execute("SELECT slug, title, primary_keyword FROM pages").fetchall())
    return [{"url": f"/blog/{r[0]}", "title": f"{r[1]} {r[2]}"} for r in rows]
