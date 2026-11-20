"""Tests: the AI and the network are replaced by fakes, so no API quota is used.

Run (Linux container, same on every machine):  docker compose --profile dev run --rm app pytest -q
"""
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app import agent, auth, db, dedupe, errors, images as images_mod, mailer, main, research, safeurl, seo
from app.config import settings
from app.llm import current_key
from app.models import BlogPost, BlogRequest

from . import fakes

PW = "correct horse battery"


@pytest.fixture()
def client(monkeypatch):
    auth._hits.clear()  # the signup/login rate limit would otherwise trip over the many test accounts
    monkeypatch.setattr(settings, "gemini_api_key", "AIzaSy" + "t" * 30)  # tests must not depend on a real key being in .env (CI has none)
    monkeypatch.setattr(research, "run_research", fakes.fake_research)
    monkeypatch.setattr(images_mod, "_gemini", _none)
    monkeypatch.setattr(images_mod, "_commons", _none2)
    monkeypatch.setattr(images_mod, "_pixabay", _none2)
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


def test_a_failed_repair_keeps_the_draft_instead_of_failing_the_run(client, monkeypatch):
    monkeypatch.setattr(agent, "structured", fakes.fake_llm(weak_first=True, fail_repair=True))
    _signup(client)
    ev = _events(_create(client, site="https://example.com").text)
    assert ev[-1][0] == "done", ev[-1]
    done = ev[-1][1]
    assert done["repaired"] is False and done["score_before"] is None and done["score"] < 85
    note = [e[1]["data"]["note"] for e in ev if e[0] == "step" and e[1]["id"] == "repair" and e[1]["status"] == "done"]
    assert note and "kept" in note[0]
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
    monkeypatch.setattr(images_mod, "_pixabay", _none2)
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


# ---- model fallback and the circuit breaker ------------------------------------------------------------------------------------------------------
async def test_failed_models_are_skipped_next_time_and_bad_key_stops(monkeypatch):
    from app import llm
    llm._bad.clear()
    calls: list[str] = []

    async def fake_call(model, schema, system, user, temperature, timeout, retries, final):
        calls.append(model)
        if model == "m3":
            return "ok"
        raise errors.INVALID_API_KEY if model == "bad-key" else errors.UPSTREAM_ERROR

    monkeypatch.setattr(llm, "_call", fake_call)
    monkeypatch.setattr(settings, "gemini_api_key", "AIzaSy" + "x" * 30)
    monkeypatch.setattr(settings, "llm_model", "m1")
    monkeypatch.setattr(settings, "fallback_models", ["m2", "m3"])
    assert await llm.structured(dict, "s", "u") == "ok" and calls == ["m1", "m2", "m3"]
    calls.clear()
    assert await llm.structured(dict, "s", "u") == "ok" and calls == ["m3"], "models that just failed are tried last"
    monkeypatch.setattr(settings, "llm_model", "bad-key")
    llm._bad.clear()
    with pytest.raises(errors.AppError) as e:
        await llm.structured(dict, "s", "u")
    assert e.value.code == "INVALID_API_KEY"
    llm._bad.clear()


async def test_image_sources_are_tried_in_order_and_fall_back(monkeypatch):
    from app.models import ImageIdea
    idea = ImageIdea(description="a bat", alt="a bat on grass for testing", placement="hero", query="bat")
    jpg = images_mod.cover("x")
    calls: list[str] = []

    def provider(name, result):
        async def f(*a, **k):
            calls.append(name)
            return result
        return f

    monkeypatch.setattr(images_mod, "_gemini", provider("gemini", None))
    monkeypatch.setattr(images_mod, "_pixabay", provider("pixabay", None))
    monkeypatch.setattr(images_mod, "_commons", provider("commons", (jpg, "Photo: A / Wikimedia Commons (CC BY 4.0)")))
    out = (await images_mod.make_images([idea], "cricket"))[0]
    assert calls == ["gemini", "pixabay", "commons"]
    assert out["source"] == "commons" and "Wikimedia" in out["credit"]


async def test_commons_tries_the_topic_when_the_image_query_finds_nothing(monkeypatch):
    from app.models import ImageIdea
    asked: list[str] = []

    async def search(client, query):
        asked.append(query)
        return (b"img", "credit") if query == "cricket bat for beginners" else None

    monkeypatch.setattr(images_mod, "_commons_search", search)
    idea = ImageIdea(description="d", alt="alt text long enough here", placement="hero", query="odd query")
    assert await images_mod._commons(None, idea, "cricket bat for beginners") == (b"img", "credit")
    assert asked == ["odd query", "cricket bat for beginners"]


# ---- password reset by email (Gmail API faked) -----------------------------------------------------------------------------------------------
@pytest.fixture()
def mail(client, monkeypatch):
    sent: list[dict] = []
    for k in ("gmail_client_id", "gmail_client_secret", "gmail_refresh_token", "gmail_sender"):
        monkeypatch.setattr(settings, k, f"test-{k}")

    async def fake_send(to, subject, text, html):
        sent.append({"to": to, "subject": subject, "text": text, "html": html})
        return True

    monkeypatch.setattr(mailer, "send_mail", fake_send)
    return sent


def _wait_mail(sent: list, n: int = 1):
    import time
    for _ in range(60):
        if len(sent) >= n:
            return
        time.sleep(0.05)


def _token_from(mail_item: dict) -> str:
    return mail_item["text"].split("#t=")[1].split()[0]


def test_reset_flow_end_to_end(client, mail):
    email = _signup(client)
    old_cookie = client.cookies.get("sid")
    assert client.post("/api/auth/forgot", json={"email": email}).json() == {"ok": True}
    _wait_mail(mail)
    assert len(mail) == 1 and mail[0]["to"] == email and "Reset your" in mail[0]["subject"]
    link = [w for w in mail[0]["text"].split() if "#t=" in w][0]
    assert "/reset#t=" in link, "the token must be in the #fragment so it never reaches server logs"
    token = _token_from(mail[0])
    # a too-short password does not use up the token
    assert client.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code == 422
    assert client.post("/api/auth/reset", json={"token": token, "password": "A brand new pass 2026"}).status_code == 200
    # the link works once only
    assert client.post("/api/auth/reset", json={"token": token, "password": "Another pass 2026!"}).status_code == 400
    # old password is dead, new one works, old sessions are signed out
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": email, "password": PW}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "A brand new pass 2026"}).status_code == 200
    client.cookies.clear()
    client.cookies.set("sid", old_cookie)
    assert client.get("/api/auth/me").status_code == 401
    client.post("/api/auth/login", json={"email": email, "password": "A brand new pass 2026"})
    _cleanup(client)


def test_forgot_does_not_reveal_whether_an_account_exists(client, mail):
    r1 = client.post("/api/auth/forgot", json={"email": "nobody-" + uuid.uuid4().hex[:6] + "@example.test"})
    r2 = client.post("/api/auth/forgot", json={"email": "not an email"})
    assert r1.status_code == 200 and r2.status_code == 200 and r1.json() == r2.json() == {"ok": True}
    _wait_mail(mail)
    assert mail == []


def test_google_only_account_gets_a_helpful_email_and_no_token(client, mail):
    email = f"g-{uuid.uuid4().hex[:8]}@example.test"
    db.create_user(email, "G", None, "google-sub-" + uuid.uuid4().hex)
    client.post("/api/auth/forgot", json={"email": email})
    _wait_mail(mail)
    assert len(mail) == 1 and "Continue with Google" in mail[0]["text"] and "#t=" not in mail[0]["text"]
    db.delete_user(db.user_by_email(email)["id"])


def test_expired_and_unknown_tokens_are_rejected(client, mail):
    email = _signup(client)
    client.post("/api/auth/forgot", json={"email": email})
    _wait_mail(mail)
    token = _token_from(mail[0])
    db._run(lambda c: c.execute("UPDATE password_resets SET expires_at = now() - interval '1 minute'"))
    assert client.post("/api/auth/reset", json={"token": token, "password": "A brand new pass 2026"}).status_code == 400
    assert client.post("/api/auth/reset", json={"token": "x" * 40, "password": "A brand new pass 2026"}).status_code == 400
    _cleanup(client)


def test_forgot_is_rate_limited(client, mail):
    email = _signup(client)
    codes = [client.post("/api/auth/forgot", json={"email": email}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and 429 in codes
    _cleanup(client)


def test_reset_is_off_when_email_is_not_configured(client, monkeypatch):
    for k in ("gmail_client_id", "gmail_client_secret", "gmail_refresh_token", "gmail_sender"):
        monkeypatch.setattr(settings, k, "")
    assert client.get("/api/meta").json()["email_reset"] is False
    assert client.post("/api/auth/forgot", json={"email": "a@example.test"}).status_code == 503


def test_meta_reports_email_reset_when_configured(client, mail):
    assert client.get("/api/meta").json()["email_reset"] is True


def test_mail_message_is_well_formed():
    from app import mailer as m
    subject, text, html = m.reset_email("https://x.test/reset#t=abc")
    msg = m.build_message("a@example.test", subject, text, html)
    assert msg["To"] == "a@example.test" and msg["Subject"] == subject and "abc" in msg.get_body(("plain",)).get_content()
    import pytest as _p
    with _p.raises(Exception):
        m.build_message("a@example.test\nBcc: evil@example.test", subject, text, html)  # header injection is refused


# ---- the product's own SEO ---------------------------------------------------------------------------------------------------------------
def test_robots_and_sitemap_use_the_real_domain(client):
    r = client.get("/robots.txt", headers={"Host": "rank.example.org"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Disallow: /app/" in r.text and "Disallow: /api/" in r.text and "Disallow: /s/" in r.text
    assert "Sitemap: http://rank.example.org/sitemap.xml" in r.text
    s = client.get("/sitemap.xml", headers={"Host": "rank.example.org"})
    assert s.status_code == 200 and "xml" in s.headers["content-type"]
    import xml.etree.ElementTree as ET
    locs = [e.text for e in ET.fromstring(s.text).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert locs == ["http://rank.example.org/", "http://rank.example.org/privacy"]


def test_index_tags_are_filled_per_page():
    from app import sitepages
    tpl = ("<title>__TITLE__</title><meta name=\"description\" content=\"__DESC__\"><meta name=\"robots\" content=\"__ROBOTS__\">"
           "<link rel=\"canonical\" href=\"__CANONICAL__\"><meta property=\"og:image\" content=\"__BASE__/og.jpg\">")
    home = sitepages.render_index(tpl, "https://x.test", "/")
    assert "__" not in home and 'content="index,follow"' in home and 'href="https://x.test/"' in home and "https://x.test/og.jpg" in home
    priv = sitepages.render_index(tpl, "https://x.test", "/privacy")
    assert "Privacy" in priv and 'href="https://x.test/privacy"' in priv
    for private in ("/app/new", "/login", "/signup", "/forgot", "/reset", "/anything-else"):
        out = sitepages.render_index(tpl, "https://x.test", private)
        assert "noindex" in out and "__" not in out, private


def test_real_index_template_has_the_seo_tags():
    import pathlib
    tpl = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")
    for needle in ("__TITLE__", "__DESC__", "__ROBOTS__", "__CANONICAL__", "__BASE__/og.jpg", "application/ld+json", "twitter:card", "og:title", "<noscript>"):
        assert needle in tpl, needle
    import json, re
    from app import sitepages
    out = sitepages.render_index(tpl, "https://x.test", "/")
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', out, re.S).group(1))
    assert ld["@graph"][1]["offers"]["price"] == "0" and ld["@graph"][0]["url"] == "https://x.test/"


def test_titles_and_descriptions_are_sensible_lengths():
    from app import sitepages
    for key, (title, desc, _) in sitepages.PAGES.items():
        assert 15 <= len(title) <= 60 and 50 <= len(desc) <= 200, key
