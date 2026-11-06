"""Keyword research + site inventory. READ-ONLY: only GET requests, only to allow-listed hosts.

Data labels:
  verified  = observed directly (live Google Autocomplete, live site sitemap, or the dated snapshot
              of those same sources captured during manual browser research)
  estimate  = added later by the AI step (intent / competition / volume bands)
"""
import asyncio
import json
import re
import time
from urllib.parse import quote

import httpx

from .config import DATA_DIR, SEEDS, SITE, SITE_HOST

UA = "Mozilla/5.0 (compatible; AppinSEOAgentDemo/1.0)"
SUGGEST = "https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=in&q="
ALLOWED_HOSTS = {SITE_HOST, "suggestqueries.google.com"}
_SKIP = re.compile(r"thank-you|register|download-|digital-card|maintenance|author|course-enquiry|-dinesh|-kousalya|/fb/")
_TOPIC = re.compile(r"digital-marketing|seo|social-media|marketing|ppc|google-ads|content|influencer|branding|email")
_RELEVANT = re.compile(r"marketing|seo|ads|social media|content|analytics|ppc|affiliate|email|course|training|syllabus|career|institute", re.I)
_OTHER_CITY = re.compile(r"\b(chennai|bangalore|bengaluru|kolkata|hyderabad|mumbai|delhi|pune|kerala|kochi)\b", re.I)
_NOISE = re.compile(r"\b(hindi|udemy|pdf|free download|telugu|tamil pdf)\b", re.I)

_site_cache: dict = {"at": 0.0, "value": None}


def _check_host(url: str) -> None:
    host = url.split("/")[2] if "//" in url else ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host not allow-listed: {host}")


def _snapshot(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _title_from_slug(url: str) -> str:
    return re.sub(r"\s+", " ", url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")).strip()


async def fetch_site(client: httpx.AsyncClient) -> dict:
    """Existing site content: live Yoast sitemaps, falling back to the dated snapshot."""
    if _site_cache["value"] and time.time() - _site_cache["at"] < 3600:
        return _site_cache["value"]
    items, source = [], "snapshot"
    try:
        locs: list[str] = []
        for sm in ("post-sitemap.xml", "page-sitemap.xml"):
            url = f"{SITE}/{sm}"
            _check_host(url)
            r = await client.get(url, timeout=10)
            r.raise_for_status()
            locs += re.findall(r"<loc>(https://appincoimbatore\.com/[^<]+)</loc>", r.text)
        urls = [u for u in dict.fromkeys(locs) if _TOPIC.search(u) and not _SKIP.search(u) and u != SITE + "/"]
        if len(urls) >= 20:
            items = [{"url": u, "title": _title_from_slug(u)} for u in urls]
            source = "live sitemap"
    except Exception:  # noqa: BLE001  (offline / blocked: use the snapshot)
        items = []
    if not items:
        snap = _snapshot("site_snapshot.json")
        items, source = snap["items"], f"snapshot ({snap['fetched']})"
    value = {"items": items, "source": source}
    _site_cache.update(at=time.time(), value=value)
    return value


async def _suggest(client: httpx.AsyncClient, seed: str) -> list[str]:
    url = SUGGEST + quote(seed)
    _check_host(url)
    r = await client.get(url, timeout=6)
    r.raise_for_status()
    data = json.loads(r.content.decode("utf-8", errors="ignore"))
    return [q for q in data[1] if isinstance(q, str)]


async def autocomplete(client: httpx.AsyncClient) -> tuple[list[dict], str]:
    results = await asyncio.gather(*[_suggest(client, s) for s in SEEDS], return_exceptions=True)
    out, ok = [], 0
    for seed, res in zip(SEEDS, results):
        if isinstance(res, list):
            ok += 1
            out += [{"keyword": q, "seed": seed} for q in res]
    if ok >= 3 and out:
        return out, "Google Autocomplete (live)"
    snap = _snapshot("seed_research.json")
    return snap["suggestions"], f"Google Autocomplete (observed {snap['fetched']})"


def build_candidates(suggestions: list[dict], label: str, limit: int = 40) -> list[dict]:
    seen, cands = set(), []
    for s in suggestions:
        kw = re.sub(r"\s+", " ", s["keyword"].lower()).strip()
        if kw in seen or not _RELEVANT.search(kw) or _OTHER_CITY.search(kw) or _NOISE.search(kw):
            continue
        seen.add(kw)
        cands.append({"keyword": kw, "source": label, "verified": True, "seed": s["seed"]})
    return cands[:limit]


async def run_research() -> dict:
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as client:
        (sugg, label), site = await asyncio.gather(autocomplete(client), fetch_site(client))
    return {"candidates": build_candidates(sugg, label), "site": site, "keyword_source": label}
