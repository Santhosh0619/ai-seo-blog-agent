"""Postgres storage (sync psycopg pool, called via asyncio.to_thread).

Every query on pages, images and runs is scoped by user_id: a user can never read another user's data.
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg_pool import ConnectionPool

from .config import settings
from .errors import DB_UNAVAILABLE, FREE_CAPACITY, FREE_LIMIT, AppError

_pool: ConnectionPool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  password_hash TEXT,
  google_sub TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pages (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  topic TEXT NOT NULL,
  title TEXT NOT NULL,
  meta_description TEXT NOT NULL,
  primary_keyword TEXT NOT NULL,
  secondary_keywords JSONB NOT NULL DEFAULT '[]',
  post JSONB NOT NULL,
  plan JSONB NOT NULL,
  research JSONB NOT NULL DEFAULT '{}',
  checks JSONB NOT NULL DEFAULT '[]',
  score INT NOT NULL,
  score_before INT,
  request JSONB NOT NULL DEFAULT '{}',
  share_token TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, slug)
);
CREATE INDEX IF NOT EXISTS pages_user_idx ON pages (user_id, id DESC);
CREATE TABLE IF NOT EXISTS images (
  token TEXT PRIMARY KEY,
  page_id BIGINT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL,
  idx INT NOT NULL,
  mime TEXT NOT NULL,
  data BYTEA NOT NULL,
  alt TEXT NOT NULL DEFAULT '',
  credit TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS images_page_idx ON images (page_id, idx);
CREATE TABLE IF NOT EXISTS runs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic TEXT NOT NULL DEFAULT '',
  own_key BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'running',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS runs_user_idx ON runs (user_id, created_at DESC);
"""


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.conninfo, min_size=1, max_size=5, open=False, timeout=8, kwargs={"autocommit": True})
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
    def fn(c):
        # Older single-site tables had no user_id: they are dropped on purpose (all old data is wiped).
        old = c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = 'pages'").fetchone()
        new = c.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'pages' AND column_name = 'user_id'").fetchone()
        if old and not new:
            c.execute("DROP TABLE IF EXISTS pages, runs CASCADE")
        c.execute(SCHEMA)
    _run(fn)


def ping() -> bool:
    try:
        _run(lambda c: c.execute("SELECT 1").fetchone())
        return True
    except AppError:
        return False


# ---- users and sessions --------------------------------------------------------------------------
def _user(r) -> dict | None:
    return {"id": r[0], "email": r[1], "name": r[2], "password_hash": r[3], "google_sub": r[4]} if r else None


_USER_COLS = "id, email, name, password_hash, google_sub"


def create_user(email: str, name: str = "", password_hash: str | None = None, google_sub: str | None = None) -> dict | None:
    """Return the new user, or None if the email is already registered."""
    def fn(c):
        r = c.execute(f"INSERT INTO users (email, name, password_hash, google_sub) VALUES (%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING RETURNING {_USER_COLS}",
                      (email, name, password_hash, google_sub)).fetchone()
        return _user(r)
    return _run(fn)


def user_by_email(email: str) -> dict | None:
    return _run(lambda c: _user(c.execute(f"SELECT {_USER_COLS} FROM users WHERE email = %s", (email,)).fetchone()))


def user_by_google(sub: str) -> dict | None:
    return _run(lambda c: _user(c.execute(f"SELECT {_USER_COLS} FROM users WHERE google_sub = %s", (sub,)).fetchone()))


def link_google(user_id: int, sub: str, name: str) -> None:
    _run(lambda c: c.execute("UPDATE users SET google_sub = %s, name = CASE WHEN name = '' THEN %s ELSE name END WHERE id = %s", (sub, name, user_id)))


def delete_user(user_id: int) -> None:
    _run(lambda c: c.execute("DELETE FROM users WHERE id = %s", (user_id,)))


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int, days: int = 30) -> str:
    token = secrets.token_urlsafe(32)
    _run(lambda c: c.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s,%s,%s)",
                             (_h(token), user_id, datetime.now(timezone.utc) + timedelta(days=days))))
    return token


def session_user(token: str) -> dict | None:
    def fn(c):
        r = c.execute("SELECT u.id, u.email, u.name, u.password_hash, u.google_sub FROM sessions s JOIN users u ON u.id = s.user_id "
                      "WHERE s.token_hash = %s AND s.expires_at > now()", (_h(token),)).fetchone()
        return _user(r)
    return _run(fn)


def delete_session(token: str) -> None:
    _run(lambda c: c.execute("DELETE FROM sessions WHERE token_hash = %s", (_h(token),)))


# ---- runs and free quota -------------------------------------------------------------------------
def free_status(user_id: int) -> dict:
    """Free runs left for this user (rolling 24h) and whether the shared free capacity is used up."""
    def fn(c):
        c.execute("UPDATE runs SET status = 'failed' WHERE status = 'running' AND created_at < now() - interval '15 minutes'")
        mine = c.execute("SELECT count(*) FROM runs WHERE user_id = %s AND own_key = false AND status IN ('running','done') "
                         "AND created_at > now() - interval '24 hours'", (user_id,)).fetchone()[0]
        glob = c.execute("SELECT count(*) FROM runs WHERE own_key = false AND status IN ('running','done') "
                         "AND created_at > now() - interval '24 hours'").fetchone()[0]
        running = c.execute("SELECT count(*) FROM runs WHERE status = 'running'").fetchone()[0]
        mine_running = c.execute("SELECT count(*) FROM runs WHERE user_id = %s AND status = 'running'", (user_id,)).fetchone()[0]
        return mine, glob, running, mine_running
    mine, glob, running, mine_running = _run(fn)
    left = max(0, settings.free_runs_per_day - mine)
    capacity_left = max(0, settings.global_free_runs_per_day - glob)
    return {"limit": settings.free_runs_per_day, "left": left, "capacity_left": capacity_left,
            "running": running, "mine_running": mine_running}


def start_run(user_id: int, topic: str, own_key: bool) -> int:
    """Reserve a run. Free runs are limited per user and in total; runs with the user's own key are not."""
    def fn(c):
        with c.transaction():
            c.execute("SELECT pg_advisory_xact_lock(7001)")
            if not own_key:
                mine = c.execute("SELECT count(*) FROM runs WHERE user_id = %s AND own_key = false AND status IN ('running','done') "
                                 "AND created_at > now() - interval '24 hours'", (user_id,)).fetchone()[0]
                if mine >= settings.free_runs_per_day:
                    raise FREE_LIMIT
                glob = c.execute("SELECT count(*) FROM runs WHERE own_key = false AND status IN ('running','done') "
                                 "AND created_at > now() - interval '24 hours'").fetchone()[0]
                if glob >= settings.global_free_runs_per_day:
                    raise FREE_CAPACITY
            return c.execute("INSERT INTO runs (user_id, topic, own_key) VALUES (%s,%s,%s) RETURNING id", (user_id, topic[:200], own_key)).fetchone()[0]
    return _run(fn)


def finish_run(run_id: int, status: str) -> None:
    _run(lambda c: c.execute("UPDATE runs SET status = %s WHERE id = %s", (status, run_id)))


# ---- pages -----------------------------------------------------------------------------------------
def unique_slug(user_id: int, slug: str) -> str:
    def fn(c):
        cand, i = slug, 2
        while c.execute("SELECT 1 FROM pages WHERE user_id = %s AND slug = %s", (user_id, cand)).fetchone():
            cand, i = f"{slug}-{i}", i + 1
        return cand
    return _run(fn)


def save_page(user_id: int, *, slug: str, topic: str, title: str, meta: str, primary: str, secondary: list[str], post: dict[str, Any],
              plan: dict[str, Any], research: dict[str, Any], checks: list, score: int, score_before: int | None, request: dict[str, Any]) -> int:
    j = json.dumps
    return _run(lambda c: c.execute(
        """INSERT INTO pages (user_id, slug, topic, title, meta_description, primary_keyword, secondary_keywords, post, plan, research, checks, score, score_before, request)
           VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb) RETURNING id""",
        (user_id, slug, topic, title, meta, primary, j(secondary), j(post), j(plan), j(research), j(checks), score, score_before, j(request))).fetchone()[0])


def save_images(page_id: int, user_id: int, items: list[dict]) -> None:
    def fn(c):
        for it in items:
            c.execute("INSERT INTO images (token, page_id, user_id, idx, mime, data, alt, credit, source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (secrets.token_urlsafe(18), page_id, user_id, it["idx"], it["mime"], it["data"], it.get("alt", ""), it.get("credit", ""), it.get("source", "")))
    _run(fn)


_PAGE_COLS = ("id, slug, topic, title, meta_description, primary_keyword, secondary_keywords, post, plan, research, checks, score, "
              "score_before, request, share_token, created_at")


def _page(r) -> dict:
    keys = ["id", "slug", "topic", "title", "meta_description", "primary_keyword", "secondary_keywords", "post", "plan", "research", "checks",
            "score", "score_before", "request", "share_token", "created_at"]
    d = dict(zip(keys, r))
    d["created_at"] = d["created_at"].isoformat()
    return d


def get_page(user_id: int, page_id: int) -> dict | None:
    r = _run(lambda c: c.execute(f"SELECT {_PAGE_COLS} FROM pages WHERE user_id = %s AND id = %s", (user_id, page_id)).fetchone())
    return _page(r) if r else None


def get_page_by_share(token: str) -> dict | None:
    r = _run(lambda c: c.execute(f"SELECT {_PAGE_COLS} FROM pages WHERE share_token = %s", (token,)).fetchone())
    return _page(r) if r else None


def page_images(page_id: int) -> list[dict]:
    rows = _run(lambda c: c.execute("SELECT idx, token, alt, credit, source, mime FROM images WHERE page_id = %s ORDER BY idx", (page_id,)).fetchall())
    return [{"idx": r[0], "token": r[1], "alt": r[2], "credit": r[3], "source": r[4], "mime": r[5]} for r in rows]


def image_bytes(token: str) -> tuple[str, bytes] | None:
    r = _run(lambda c: c.execute("SELECT mime, data FROM images WHERE token = %s", (token,)).fetchone())
    return (r[0], bytes(r[1])) if r else None


def list_pages(user_id: int, limit: int = 100) -> list[dict]:
    rows = _run(lambda c: c.execute(
        "SELECT p.id, p.slug, p.topic, p.title, p.primary_keyword, p.score, p.score_before, p.share_token, p.created_at, "
        "(SELECT token FROM images i WHERE i.page_id = p.id ORDER BY idx LIMIT 1) FROM pages p WHERE p.user_id = %s ORDER BY p.id DESC LIMIT %s",
        (user_id, limit)).fetchall())
    return [{"id": r[0], "slug": r[1], "topic": r[2], "title": r[3], "primary_keyword": r[4], "score": r[5], "score_before": r[6],
             "shared": bool(r[7]), "created_at": r[8].isoformat(), "cover": r[9]} for r in rows]


def delete_page(user_id: int, page_id: int) -> bool:
    return _run(lambda c: c.execute("DELETE FROM pages WHERE user_id = %s AND id = %s", (user_id, page_id)).rowcount > 0)


def set_share(user_id: int, page_id: int, enabled: bool) -> str | None:
    def fn(c):
        if enabled:
            token = secrets.token_urlsafe(18)
            r = c.execute("UPDATE pages SET share_token = COALESCE(share_token, %s) WHERE user_id = %s AND id = %s RETURNING share_token", (token, user_id, page_id)).fetchone()
            return r[0] if r else None
        c.execute("UPDATE pages SET share_token = NULL WHERE user_id = %s AND id = %s", (user_id, page_id))
        return None
    return _run(fn)


def previous_pages(user_id: int, limit: int = 40) -> list[dict]:
    """The user's earlier pages: title/keyword for duplicate checks, body text for uniqueness checks."""
    rows = _run(lambda c: c.execute("SELECT id, title, primary_keyword, post FROM pages WHERE user_id = %s ORDER BY id DESC LIMIT %s", (user_id, limit)).fetchall())
    return [{"id": r[0], "title": r[1], "keyword": r[2], "post": r[3]} for r in rows]
