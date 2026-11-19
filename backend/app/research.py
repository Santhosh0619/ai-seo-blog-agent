"""Keyword research for any topic. READ-ONLY: only GET requests.

Data labels:
  verified  = observed directly (live Google Autocomplete suggestions, the user's real sitemap, Wikipedia text)
  estimate  = added later by the AI step (intent / competition / volume bands)
"""
import asyncio
import json
import re
from urllib.parse import quote, urlparse

import httpx

from . import safeurl
from .models import BlogRequest

UA = "Mozilla/5.0 (compatible; RankwiseBot/1.0)"
SUGGEST = "https://suggestqueries.google.com/complete/search?client=firefox&hl={hl}&gl={gl}&q={q}"
_JUNK = re.compile(r"\.(jpe?g|png|gif|webp|svg|pdf|zip|css|js|xml)(\?|$)|/(wp-content|wp-json|feed|tag|category|author|cart|checkout|my-account|login)/", re.I)


def title_from_url(url: str) -> str:
    tail = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", tail)).strip()


async def _suggest(client: httpx.AsyncClient, seed: str, lang: str, country: str) -> list[str]:
    r = await client.get(SUGGEST.format(hl=lang, gl=country, q=quote(seed)), timeout=6)
    r.raise_for_status()
    data = json.loads(r.content.decode("utf-8", errors="ignore"))
    return [q for q in data[1] if isinstance(q, str)]


def build_candidates(suggestions: list[dict], limit: int = 40) -> list[dict]:
    seen, out = set(), []
    for s in suggestions:
        kw = re.sub(r"\s+", " ", s["keyword"].lower()).strip()
        if not kw or kw in seen or len(kw.split()) > 9 or len(kw) < 4:
            continue
        seen.add(kw)
        out.append({"keyword": kw, "source": s["source"], "verified": s["verified"], "seed": s["seed"]})
    return out[:limit]


async def autocomplete(client: httpx.AsyncClient, seeds: list[str], lang: str, country: str) -> tuple[list[dict], str]:
    """Live Google Autocomplete for each seed. If Google is unreachable the AI seeds are used and clearly labelled unverified."""
    results = await asyncio.gather(*[_suggest(client, s, lang, country) for s in seeds], return_exceptions=True)
    out, ok = [], 0
    for seed, res in zip(seeds, results):
        if isinstance(res, list):
            ok += 1
            out += [{"keyword": q, "seed": seed, "source": "Google Autocomplete (live)", "verified": True} for q in res]
    if ok >= 2 and len(out) >= 8:
        return build_candidates(out), "Google Autocomplete (live)"
    fallback = [{"keyword": s, "seed": s, "source": "AI-suggested (not verified)", "verified": False} for s in seeds]
    return build_candidates(out + fallback), "AI-suggested (Google Autocomplete was not reachable)"


async def fetch_sitemap(client: httpx.AsyncClient, origin: str) -> dict:
    """Read the pages of the user's own site from its sitemap. Returns items [{url,title}] and a status note."""
    host = urlparse(origin).hostname
    cand = []
    try:
        robots = await safeurl.safe_get(client, f"{origin}/robots.txt") or ""
        cand += re.findall(r"(?im)^sitemap:\s*(\S+)", robots)[:3]
    except Exception:  # noqa: BLE001
        pass
    cand += [f"{origin}/sitemap_index.xml", f"{origin}/sitemap.xml", f"{origin}/wp-sitemap.xml", f"{origin}/post-sitemap.xml", f"{origin}/page-sitemap.xml"]
    urls: list[str] = []
    seen_maps: set[str] = set()

    async def read(map_url: str, depth: int) -> None:
        if map_url in seen_maps or len(seen_maps) >= 10 or len(urls) >= 600:
            return
        seen_maps.add(map_url)
        if urlparse(map_url).hostname != host:
            return
        try:
            text = await safeurl.safe_get(client, map_url)
        except Exception:  # noqa: BLE001
            return
        if not text or "<loc>" not in text:
            return
        locs = [u.strip() for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)]
        for u in locs:
            if urlparse(u).hostname != host:
                continue
            if u.endswith(".xml") and depth < 2:
                await read(u, depth + 1)
            elif not u.endswith(".xml") and not _JUNK.search(u):
                urls.append(u)

    for m in cand:
        if len(urls) >= 20:
            break
        await read(m, 0)
    urls = [u for u in dict.fromkeys(urls) if urlparse(u).path not in ("", "/")][:600]
    if not urls:
        return {"items": [], "note": f"Could not read a sitemap for {host}. The duplicate check used only your earlier pages."}
    return {"items": [{"url": u, "title": title_from_url(u)} for u in urls], "note": f"Read {len(urls)} pages from the sitemap of {host}."}


async def wikipedia_facts(client: httpx.AsyncClient, topic: str, lang: str) -> list[dict]:
    """Free, citable reference text. Used only as allowed facts; may be unrelated, the writer ignores it then."""
    if not re.fullmatch(r"[a-z]{2}", lang):
        lang = "en"
    base = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        r = await client.get(base, params={"action": "query", "list": "search", "srsearch": topic, "srlimit": 2, "format": "json"}, timeout=6)
        r.raise_for_status()
        titles = [h["title"] for h in r.json()["query"]["search"]][:2]
        out = []
        for t in titles:
            e = await client.get(base, params={"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "exchars": 1100,
                                               "titles": t, "format": "json", "redirects": 1}, timeout=6)
            e.raise_for_status()
            page = next(iter(e.json()["query"]["pages"].values()))
            text = (page.get("extract") or "").strip()
            if text:
                out.append({"title": page.get("title", t), "url": f"https://{lang}.wikipedia.org/wiki/{quote(page.get('title', t).replace(' ', '_'))}", "extract": text})
        return out
    except Exception:  # noqa: BLE001
        return []


async def run_research(req: BlogRequest, seeds: list[str], site_origin: str) -> dict:
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as client:
        tasks = [autocomplete(client, seeds, req.language, req.country), wikipedia_facts(client, req.topic, req.language)]
        if site_origin:
            tasks.append(fetch_sitemap(client, site_origin))
        res = await asyncio.gather(*tasks)
    candidates, label = res[0]
    site = res[2] if site_origin else {"items": [], "note": "No website given: duplicates are checked against your earlier pages only."}
    return {"candidates": candidates, "keyword_source": label, "facts": res[1], "site": site}
