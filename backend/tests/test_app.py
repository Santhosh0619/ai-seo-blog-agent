"""Automated tests. They never call Gemini: the LLM function is replaced by fakes from tests/fakes.py.
The API tests need the Docker Postgres (docker compose up -d)."""
import json

import pytest
from fastapi.testclient import TestClient

from app import agent, dedupe, llm, page, seo
from app.config import settings
from app.errors import INVALID_API_KEY, RATE_LIMITED, TIMEOUT, UPSTREAM_ERROR, AppError, map_exception
from app.main import app
from app.models import BlogPost, Plan
from tests.fakes import sim_plan, sim_post

SHORTLIST = [{"keyword": "seo course in coimbatore", "status": "gap", "overlap": 0.3}] + \
            [{"keyword": f"seo course topic {i}", "status": "gap", "overlap": 0.2} for i in range(6)]


def _plan_post():
    plan = sim_plan({"shortlist": SHORTLIST})
    return plan, sim_post({"plan": plan})


def fake_llm(fail: AppError | None = None):
    state = {}

    async def structured(schema, system, user):
        if fail:
            raise fail
        if schema is Plan:
            state["plan"] = sim_plan({"shortlist": SHORTLIST})
            return state["plan"]
        return sim_post({"plan": state["plan"]})
    return structured


# ---------------- pure logic ----------------
def test_dedupe_flags_saturated_head_terms_and_finds_gaps():
    existing = [{"title": "digital marketing training in coimbatore with job placement", "url": "https://appincoimbatore.com/a/"},
                {"title": "the ultimate guide to seo in 2023", "url": "https://appincoimbatore.com/b/"}]
    res = {c["keyword"]: c for c in dedupe.check(
        [{"keyword": "digital marketing course in coimbatore"}, {"keyword": "seo course in coimbatore"}, {"keyword": "google ads course"}], existing)}
    assert res["digital marketing course in coimbatore"]["status"] == "conflict"
    assert res["seo course in coimbatore"]["status"] != "conflict"
    assert res["google ads course"]["status"] == "gap"


def test_seo_check_passes_good_post_and_flags_bad_one():
    plan, post = _plan_post()
    checks, score = seo.check(post, plan.primary_keyword, plan.secondary_keywords)
    assert score == 100, [c for c in checks if not c["passed"]]
    post.seo_title, post.faqs = "x", post.faqs[:1]
    assert seo.check(post, plan.primary_keyword, plan.secondary_keywords)[1] < score


def test_sanitize_drops_unknown_links_and_fixes_slug():
    _, post = _plan_post()
    post.internal_links[0].url = "https://evil.example/x"
    post.slug = "Bad Slug!!"
    post = seo.sanitize(post, set())
    assert all(l.url.startswith("https://appincoimbatore.com/") for l in post.internal_links) and post.slug == "bad-slug"


def test_page_html_is_escaped_and_seo_ready():
    plan, post = _plan_post()
    post.intro[0] = "<script>alert(1)</script> " + post.intro[0]
    html = page.build_html(post, plan.primary_keyword, 1200)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    for needle in ('rel="canonical"', 'name="description"', "application/ld+json", "FAQPage", "<h1>", 'role="img"'):
        assert needle in html


def test_error_mapping():
    assert map_exception(RuntimeError("400 API key not valid [API_KEY_INVALID]")).code == "INVALID_API_KEY"
    assert map_exception(RuntimeError("429 RESOURCE_EXHAUSTED")).code == "RATE_LIMITED"
    assert map_exception(TimeoutError()).code == "TIMEOUT"


# ---------------- model fallback ----------------
@pytest.mark.asyncio
async def test_llm_falls_back_to_next_model_when_first_is_overloaded(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key-not-used-00000000")
    tried = []

    async def fake_call(model, schema, system, user, retries, final):
        tried.append(model)
        if model == settings.llm_model:
            raise UPSTREAM_ERROR
        return "ok"
    monkeypatch.setattr(llm, "_call", fake_call)
    assert await llm.structured(BlogPost, "s", "u") == "ok"
    assert tried[0] == settings.llm_model and len(tried) == 2


@pytest.mark.asyncio
async def test_llm_stops_immediately_on_invalid_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key-not-used-00000000")
    tried = []

    async def fake_call(model, *a, **k):
        tried.append(model)
        raise INVALID_API_KEY
    monkeypatch.setattr(llm, "_call", fake_call)
    with pytest.raises(AppError) as e:
        await llm.structured(BlogPost, "s", "u")
    assert e.value.code == "INVALID_API_KEY" and len(tried) == 1


# ---------------- API ----------------
@pytest.fixture()
def client(monkeypatch):
    from app import db
    monkeypatch.setattr(db, "record_run_if_allowed", lambda limit: True)  # tests must not use up the hourly run budget
    with TestClient(app) as c:
        yield c


def events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return out


def test_create_blog_end_to_end_and_page_is_served(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key-not-used-00000000")
    monkeypatch.setattr(agent, "structured", fake_llm())
    ev = events(client.post("/api/blog/create").text)
    ids = [d["id"] for n, d in ev if n == "step" and d["status"] == "done"]
    assert ids[:5] == ["research", "dedupe", "plan", "write", "validate"] and ids[-1] == "save"
    assert ev[-1][0] == "done"
    url = ev[-1][1]["url"]
    r = client.get(url)
    assert r.status_code == 200 and "<h1>" in r.text and "__BASE_URL__" not in r.text
    slug = url.rsplit("/", 1)[-1]
    assert slug in [p["slug"] for p in client.get("/api/pages").json()["pages"]]
    from app import db
    db._run(lambda c: c.execute("DELETE FROM pages WHERE slug = %s", (slug,)))  # keep the dev DB free of test pages


@pytest.mark.parametrize("err, code", [(INVALID_API_KEY, "INVALID_API_KEY"), (RATE_LIMITED, "RATE_LIMITED"), (TIMEOUT, "TIMEOUT")])
def test_provider_errors_become_error_events(client, monkeypatch, err, code):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key-not-used-00000000")
    monkeypatch.setattr(agent, "structured", fake_llm(fail=err))
    ev = events(client.post("/api/blog/create").text)
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == code and ev[-1][1]["step"] == "plan"


def test_missing_key_is_a_clear_http_error_before_streaming(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    r = client.post("/api/blog/create")
    assert r.status_code == 503 and r.json()["error"]["code"] == "MISSING_API_KEY"
    assert client.get("/health").json()["llm_configured"] is False


def test_unknown_page_is_404(client):
    assert client.get("/blog/does-not-exist").status_code == 404
