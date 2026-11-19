"""Tests: the AI and the network are replaced by fakes, so no API quota is used.

Run (Linux container, same on every machine):  docker compose --profile dev run --rm app pytest -q
"""
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app import agent, auth, db, dedupe, errors, images as images_mod, main, research, safeurl, seo
from app.config import settings
from app.llm import current_key
from app.models import BlogPost, BlogRequest

from . import fakes

PW = "correct horse battery"


@pytest.fixture()
def client(monkeypatch):
    auth._hits.clear()  # the signup/login rate limit would otherwise trip over the many test accounts
    monkeypatch.setattr(research, "run_research", fakes.fake_research)
    monkeypatch.setattr(images_mod, "_gemini", _none)
    monkeypatch.setattr(images_mod, "_commons", _none2)
    monkeypatch.setattr(agent, "structured", fakes.fake_llm())
    with TestClient(main.app) as c:
        yield c


async def _none(*a, **k):
    return None


async def _none2(*a, **k):
    return None


def _signup(c: TestClient, tag: str = "a") -> str:
    email = f"{tag}-{uuid.uuid4().hex[:8]}@example.test"
    r = c.post("/api/auth/signup", json={"email": email, "password": PW, "name": "Tester"})
    assert r.status_code == 200, r.text
    return email


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def _create(c: TestClient, topic: str = "cricket bat for beginners", site: str = "", headers: dict | None = None):
    return c.post("/api/blog/create", json={"topic": topic, "site_url": site, "country": "in", "language": "en", "notes": "A cricket bat is made of willow."}, headers=headers or {})


def _cleanup(c: TestClient):
    c.delete("/api/account")


# ---- SEO engine -------------------------------------------------------------------------------------------------------
def _ctx(plan):
    return seo.Ctx(primary=plan.primary_keyword, secondary=plan.secondary_keywords, facts_text="A cricket bat is made of willow.", link_pool=5, sources_provided=True)


def test_good_page_scores_high_and_weak_page_low():
    plan = fakes.make_plan("cricket bat for beginners", ["how to choose a cricket bat", "cricket bat weight guide"])
    checks, score, groups = seo.check(fakes.good_post(plan), _ctx(plan))
    failed = [c["id"] for c in checks if c["applicable"] and not c["passed"]]
    assert score >= 85, failed
    assert set(groups) == {"onpage", "content", "trust", "tech"}
    weak_checks, weak_score, _ = seo.check(fakes.weak_post(plan), _ctx(plan))
    assert weak_score < 70 and weak_score < score
    assert any(c["id"] == "faq" and not c["passed"] for c in weak_checks)
    assert all(c["why"] and c["fix"] for c in checks)


def test_unsourced_numbers_and_cliches_are_caught():
    plan = fakes.make_plan("cricket bat for beginners", ["how to choose a cricket bat"])
    post = fakes.good_post(plan)
    post.sections[0].paragraphs[0] += " Studies show 73% of players improve in a month. In today's fast-paced world, delve into it."
    checks = {c["id"]: c for c in seo.check(post, _ctx(plan))[0]}
    assert not checks["numbers"]["passed"] and "73%" in checks["numbers"]["detail"]
    assert not checks["cliches"]["passed"]


def test_numbers_from_user_notes_are_allowed():
    assert seo.unsourced_numbers("Weighs 1,200 grams.", "The bat weighs 1,200 grams") == []
    assert seo.unsourced_numbers("Weighs 1,200 grams.", "") == ["1,200"]


def test_not_applicable_checks_are_ignored():
    plan = fakes.make_plan("cricket bat for beginners", ["how to choose a cricket bat"])
    ctx = _ctx(plan)
    ctx.link_pool, ctx.sources_provided = 0, False
    checks = {c["id"]: c for c in seo.check(fakes.good_post(plan, links=False), ctx)[0]}
    assert not checks["links"]["applicable"] and not checks["sources"]["applicable"] and not checks["unique"]["applicable"]


def test_uniqueness_detects_a_copy():
    plan = fakes.make_plan("cricket bat for beginners", ["how to choose a cricket bat"])
    post = fakes.good_post(plan)
    ctx = _ctx(plan)
    ctx.prior_texts = [seo.body_text(post)]
    assert not {c["id"]: c for c in seo.check(post, ctx)[0]}["unique"]["passed"]


def test_sanitize_drops_unknown_links_and_sources():
    plan = fakes.make_plan("cricket bat for beginners", [])
    post = fakes.good_post(plan)
    post.internal_links[0].url = "https://evil.test/x"
    post.sources[0].url = "https://evil.test/y"
    out = seo.sanitize(post, {i["url"] for i in fakes.SITE_ITEMS}, {f["url"] for f in fakes.FACTS})
    assert len(out.internal_links) == 2 and out.sources == []


# ---- duplicate check -----------------------------------------------------------------------------------------------------
def test_dedupe_thresholds_and_subset_rule():
    existing = [{"url": "https://x.com/cricket-bat-care-tips/", "title": "cricket bat care tips"},
                {"url": "https://x.com/cricket-bat-weight-guide-2/", "title": "complete cricket bat weight guide"}]
    cands = [{"keyword": "cricket bat care tips", "verified": True}, {"keyword": "wooden handle grip types", "verified": True},
             {"keyword": "cricket bat weight guide for juniors", "verified": True}]
    out = {c["keyword"]: c for c in dedupe.check(cands, existing, "cricket bat")}
    assert out["cricket bat care tips"]["status"] == "conflict"
    assert out["wooden handle grip types"]["status"] == "gap"
    assert out["cricket bat weight guide for juniors"]["status"] in ("partial", "conflict")


# ---- safe fetching of a user's website --------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["ftp://example.com", "http://user:pw@example.com", "https://example.com:8080", "javascript:alert(1)", "not a url", "https://localhost"])
def test_bad_site_addresses_are_rejected(bad):
    with pytest.raises(errors.AppError):
        safeurl.normalize_site(bad)


def test_site_is_normalised():
    assert safeurl.normalize_site("Example.com/blog?x=1") == "https://example.com"
    assert safeurl.normalize_site("") == ""


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "[::1]"])
async def test_private_hosts_are_blocked(host):
    with pytest.raises(errors.AppError):
        await safeurl.assert_public(host.strip("[]"))


# ---- accounts ---------------------------------------------------------------------------------------------------------------------
def test_signup_login_logout(client):
    email = _signup(client)
    assert client.get("/api/auth/me").json()["user"]["email"] == email
    cookie = client.cookies.get("sid")
    assert cookie
    set_cookie = client.post("/api/auth/login", json={"email": email, "password": PW}).headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong password"}).status_code == 401
    assert client.post("/api/auth/signup", json={"email": email, "password": PW}).status_code == 409
    assert client.post("/api/auth/signup", json={"email": "bad", "password": PW}).status_code == 422
    assert client.post("/api/auth/signup", json={"email": "x@example.test", "password": "short"}).status_code == 422
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    client.post("/api/auth/login", json={"email": email, "password": PW})
    _cleanup(client)


def test_password_is_hashed_not_stored(client):
    email = _signup(client)
    user = db.user_by_email(email)
    assert PW not in user["password_hash"] and user["password_hash"].startswith("scrypt$")
    _cleanup(client)


def test_api_needs_login(client):
    for method, url in [("get", "/api/pages"), ("get", "/api/quota"), ("post", "/api/blog/create"), ("get", "/api/pages/1"), ("delete", "/api/account")]:
        assert getattr(client, method)(url).status_code in (401, 422)
    assert client.post("/api/blog/create", json={"topic": "cricket bats"}).status_code == 401


def test_foreign_origin_is_blocked(client):
    assert client.post("/api/auth/login", json={"email": "a@b.co", "password": "x" * 9}, headers={"Origin": "https://evil.test"}).status_code == 403


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"


# ---- the agent, end to end (fake AI) -------------------------------------------------------------------------------------------------
def test_end_to_end_with_website(client):
    _signup(client)
    r = _create(client, site="https://example.com")
    assert r.status_code == 200
    ev = _events(r.text)
    names = [e[1]["id"] for e in ev if e[0] == "step" and e[1]["status"] == "done"]
    assert names[:7] == ["seeds", "research", "dedupe", "plan", "write", "images", "validate"] and names[-1] == "save"
    assert ev[-1][0] == "done"
    done = ev[-1][1]
    page = client.get(f"/api/pages/{done['id']}").json()
    assert page["score"] >= 85 and len(page["checks"]) >= 20 and len(page["images"]) == 3
    assert page["research"]["seeds"] and page["plan"]["angle"]
    html = client.get(f"/api/pages/{done['id']}/preview").text
    assert "<h1>" in html and "<img" in html and "application/ld+json" in html and 'name="robots" content="noindex' in html
    for banned in ("Test environment", "prototype", "Appin", "appincoimbatore"):
        assert banned not in html
    assert client.get(page["images"][0]["url"]).headers["content-type"] == "image/webp"
    _cleanup(client)


def test_without_website_there_are_no_internal_links(client):
    _signup(client)
    done = _events(_create(client).text)[-1][1]
    page = client.get(f"/api/pages/{done['id']}").json()
    assert page["post"]["internal_links"] == []
    assert any(c["id"] == "links" and not c["applicable"] for c in page["checks"])
    _cleanup(client)


def test_repair_runs_once_and_improves_the_score(client, monkeypatch):
    monkeypatch.setattr(agent, "structured", fakes.fake_llm(weak_first=True))
    _signup(client)
    ev = _events(_create(client, site="https://example.com").text)
    ids = [e[1]["id"] for e in ev if e[0] == "step" and e[1]["status"] == "done"]
    assert ids.count("repair") == 1 and ids.count("validate") == 2
    done = ev[-1][1]
    assert done["repaired"] and done["score_before"] < done["score"]
    _cleanup(client)


def test_second_page_uses_a_different_keyword(client):
    _signup(client)
    a = _events(_create(client).text)[-1][1]
    b = _events(_create(client).text)[-1][1]
    pa, pb = client.get(f"/api/pages/{a['id']}").json(), client.get(f"/api/pages/{b['id']}").json()
    assert pa["primary_keyword"] != pb["primary_keyword"] and a["slug"] != b["slug"]
    _cleanup(client)


# ---- privacy: users only see their own data ----------------------------------------------------------------------------------------------
def test_users_cannot_see_each_others_pages(client):
    alice = _signup(client, "alice")
    pid = _events(_create(client).text)[-1][1]["id"]
    image_url = client.get(f"/api/pages/{pid}").json()["images"][0]["url"]
    client.post("/api/auth/logout")
    with TestClient(main.app) as bob:
        _signup(bob, "bob")
        assert bob.get("/api/pages").json()["pages"] == []
        for url in (f"/api/pages/{pid}", f"/api/pages/{pid}/preview", f"/api/pages/{pid}/export?format=html"):
            assert bob.get(url).status_code == 404
        assert bob.delete(f"/api/pages/{pid}").status_code == 404
        assert bob.post(f"/api/pages/{pid}/share", json={"enabled": True}).status_code == 404
        # bob's new page is not linked to alice's keywords either
        bob_id = _events(_create(bob).text)[-1][1]["id"]
        assert bob_id != pid
        bob.delete("/api/account")
    # alice still has her page
    client.post("/api/auth/login", json={"email": alice, "password": PW})
    assert client.get(image_url).status_code == 200
    assert client.get(f"/api/pages/{pid}").status_code == 200
    _cleanup(client)


def test_share_link_on_and_off(client):
    _signup(client)
    pid = _events(_create(client).text)[-1][1]["id"]
    assert client.get(f"/api/pages/{pid}").json()["share_url"] is None
    url = client.post(f"/api/pages/{pid}/share", json={"enabled": True}).json()["share_url"]
    path = "/s/" + url.rsplit("/s/", 1)[1]
    with TestClient(main.app) as anon:
        r = anon.get(path)
        assert r.status_code == 200 and "<h1>" in r.text and "Made with" in r.text and "canonical" in r.text
    client.post(f"/api/pages/{pid}/share", json={"enabled": False})
    with TestClient(main.app) as anon:
        assert anon.get(path).status_code == 404
    _cleanup(client)


def test_exports(client):
    _signup(client)
    pid = _events(_create(client, site="https://example.com").text)[-1][1]["id"]
    html = client.get(f"/api/pages/{pid}/export?format=html")
    assert html.headers["content-disposition"].startswith("attachment") and "data:image/webp;base64," in html.text and "Test environment" not in html.text
    assert 'content="index,follow"' in html.text
    assert client.get(f"/api/pages/{pid}/export?format=zip").content[:2] == b"PK"
    assert client.get(f"/api/pages/{pid}/export?format=md").text.startswith("---")
    assert json.loads(client.get(f"/api/pages/{pid}/export?format=json").text)["checks"]
    _cleanup(client)


def test_account_deletion_removes_everything(client):
    email = _signup(client)
    pid = _events(_create(client).text)[-1][1]["id"]
    uid = db.user_by_email(email)["id"]
    assert client.delete("/api/account").status_code == 200
    assert db.user_by_email(email) is None
    assert db._run(lambda c: c.execute("SELECT count(*) FROM pages WHERE id = %s", (pid,)).fetchone()[0]) == 0
    assert db._run(lambda c: c.execute("SELECT count(*) FROM images WHERE user_id = %s", (uid,)).fetchone()[0]) == 0


# ---- free runs and the user's own Gemini key ---------------------------------------------------------------------------------------------
def test_free_runs_are_limited_per_user_but_own_key_is_not(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "AIzaSy" + "x" * 30)
    _signup(client)
    for _ in range(settings.free_runs_per_day):
        assert _events(_create(client).text)[-1][0] == "done"
    r = _create(client)
    assert r.status_code == 429 and r.json()["error"]["code"] == "FREE_LIMIT" and r.json()["error"]["needs_key"] is True
    assert client.get("/api/quota").json()["left"] == 0
    own = _create(client, headers={"X-Gemini-Key": "AIzaSy" + "own" * 12})
    assert own.status_code == 200 and _events(own.text)[-1][0] == "done"
    _cleanup(client)


def test_own_key_is_used_but_never_stored_or_logged(client, monkeypatch, caplog):
    seen: list = []
    monkeypatch.setattr(agent, "structured", fakes.fake_llm(seen_keys=seen))
    monkeypatch.setattr(settings, "gemini_api_key", "AIzaSy" + "s" * 30)
    secret = "AIzaSyOWNKEY" + "q" * 28
    _signup(client)
    caplog.handler.addFilter(main._Redact())
    with caplog.at_level(logging.DEBUG):
        r = _create(client, headers={"X-Gemini-Key": secret})
        logging.getLogger("seo.test").error("oops %s", secret)  # a leak anywhere must be redacted by the log filter
    assert _events(r.text)[-1][0] == "done"
    assert seen and set(seen) == {secret}, "the user's key must reach every AI call of the run"
    assert secret not in r.text and secret not in caplog.text and "[REDACTED]" in caplog.text
    dump = db._run(lambda c: json.dumps(c.execute("SELECT row_to_json(p) FROM pages p").fetchall(), default=str) + json.dumps(c.execute("SELECT row_to_json(r) FROM runs r").fetchall(), default=str))
    assert secret not in dump
    page_id = _events(r.text)[-1][1]["id"]
    assert secret not in client.get(f"/api/pages/{page_id}/export?format=json").text
    _cleanup(client)


def test_key_context_is_cleared_after_a_run(client):
    _signup(client)
    _create(client, headers={"X-Gemini-Key": "AIzaSy" + "k" * 34})
    assert current_key() != "AIzaSy" + "k" * 34
    _cleanup(client)


def test_malformed_own_key_is_rejected(client):
    _signup(client)
    assert _create(client, headers={"X-Gemini-Key": "short"}).status_code == 401
    _cleanup(client)


def test_invalid_topic_and_site_are_rejected(client):
    _signup(client)
    assert client.post("/api/blog/create", json={"topic": "x"}).status_code == 422
    assert _create(client, site="http://localhost").status_code == 422
    _cleanup(client)


def test_missing_shared_key_asks_for_own_key(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    _signup(client)
    r = _create(client)
    assert r.status_code == 503 and r.json()["error"]["needs_key"] is True
    _cleanup(client)


# ---- images ------------------------------------------------------------------------------------------------------------------------------------
async def test_cover_images_always_work(monkeypatch):
    from app.models import ImageIdea
    monkeypatch.setattr(images_mod, "_gemini", _none)
    monkeypatch.setattr(images_mod, "_commons", _none2)
    out = await images_mod.make_images([ImageIdea(description="a bat", alt="a bat on grass for testing", placement="hero", query="bat")] * 2, "cricket")
    assert len(out) == 2 and all(o["source"] == "cover" and o["data"][:4] == b"RIFF" for o in out)


def test_covers_differ_by_seed():
    assert images_mod.cover("a") != images_mod.cover("b")


# ---- request model ---------------------------------------------------------------------------------------------------------------------------------
def test_request_validation():
    r = BlogRequest(topic="  cricket   bats ", country="IN", language="EN", tone="weird")
    assert r.topic == "cricket bats" and r.country == "in" and r.language == "en" and r.tone == "friendly"
    with pytest.raises(Exception):
        BlogRequest(topic="ok topic", country="india")
