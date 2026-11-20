"""Real images for every page. Free-only chain, so a page never has a broken image:

 1. Gemini image generation with the run's key. Free keys have no image quota (checked: HTTP 429), so this only
    works for users whose own key allows it. A failure disables it for that key (6 h for quota/billing, 5 min otherwise).
 2. Pexels / Pixabay stock photos (optional free keys; Pexels has paused new keys, Pixabay still issues them)
 3. Wikimedia Commons: openly licensed photos (CC BY, CC BY-SA, CC0, public domain) with credit. No key needed.
 4. A generated abstract cover (always works)
 (Openverse was tried and dropped: Flickr and StockSnap block downloads from servers and its image proxy times out.)
"""
import asyncio
import base64
import hashlib
import io
import logging
import re
import time

import httpx
from PIL import Image, ImageDraw, ImageFilter

from .config import settings
from .llm import current_key
from .models import ImageIdea

log = logging.getLogger("seo.images")
_gemini_off: dict[str, float] = {}  # per key (hashed): time until image generation is skipped
_UA = "RankwiseBot/1.0 (blog image search; contact via site)"
_SKIP_TITLE = re.compile(r"map|logo|flag|diagram|icon|chart|screenshot|poster|coat[ _]of[ _]arms|\.svg|\.tif", re.I)
MAX_W = 1280


def _to_webp(raw: bytes) -> bytes:
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=80, method=4)
    return out.getvalue()


def cover(seed: str, w: int = 1280, h: int = 720) -> bytes:
    """Deterministic abstract gradient cover from a seed phrase."""
    d = hashlib.sha256(seed.encode()).digest()
    hue = lambda i: (d[i], d[i + 1], d[i + 2])
    base = Image.new("RGB", (w, h), tuple(40 + c // 4 for c in hue(0)))
    layer = Image.new("RGB", (w, h))
    dr = ImageDraw.Draw(layer)
    dr.rectangle((0, 0, w, h), fill=tuple(30 + c // 3 for c in hue(3)))
    for k in range(5):
        cx, cy = d[6 + k] / 255 * w, d[11 + k] / 255 * h
        r = int(h * (0.35 + d[16 + k] / 255 * 0.45))
        col = tuple(min(255, 80 + c) for c in hue(20 + k))
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    layer = layer.filter(ImageFilter.GaussianBlur(110))
    im = Image.blend(base, layer, 0.92)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=82)
    return out.getvalue()


async def _gemini(client: httpx.AsyncClient, topic: str, idea: ImageIdea) -> bytes | None:
    key = current_key()
    kid = hashlib.sha256(key.encode()).hexdigest()[:12]
    if not (settings.images_enabled and key) or time.time() < _gemini_off.get(kid, 0):
        return None
    prompt = (f"A clean, modern editorial illustration for a blog article about {topic}. {idea.description}. "
              "Wide 16:9 composition. No text, no logos, no watermarks, no real people's faces.")
    try:
        r = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{settings.image_model}:generateContent",
                              headers={"x-goog-api-key": key}, timeout=50,
                              json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"]}})
        if r.status_code != 200:
            log.info("Gemini image generation unavailable (HTTP %s); using the next source", r.status_code)
            _gemini_off[kid] = time.time() + (6 * 3600 if r.status_code in (400, 403, 429) else 300)
            return None
        for part in r.json()["candidates"][0]["content"]["parts"]:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return await asyncio.to_thread(_to_webp, base64.b64decode(inline["data"]))
    except Exception:  # noqa: BLE001
        log.info("Gemini image generation failed; using the next source")
        _gemini_off[kid] = time.time() + 300
    return None


async def _pexels(client: httpx.AsyncClient, idea: ImageIdea, topic: str) -> tuple[bytes, str] | None:
    if not settings.pexels_api_key:
        return None
    try:
        r = await client.get("https://api.pexels.com/v1/search", headers={"Authorization": settings.pexels_api_key}, timeout=8,
                             params={"query": (idea.query or topic)[:80], "per_page": 3, "orientation": "landscape"})
        r.raise_for_status()
        photos = r.json().get("photos") or []
        if not photos:
            return None
        ph = photos[0]
        img = await client.get(ph["src"]["large"], timeout=12)
        img.raise_for_status()
        return await asyncio.to_thread(_to_webp, img.content), f"Photo by {ph.get('photographer', 'a photographer')} on Pexels"
    except Exception:  # noqa: BLE001
        return None


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


async def _commons(client: httpx.AsyncClient, idea: ImageIdea, topic: str) -> tuple[bytes, str] | None:
    """Openly licensed photo from Wikimedia Commons. Tries the image's own query, then the topic, then its first two words."""
    seen: list[str] = []
    for q in (idea.query, topic, " ".join(topic.split()[:2])):
        q = (q or "").strip()[:80]
        if q and q.lower() not in seen:
            seen.append(q.lower())
            found = await _commons_search(client, q)
            if found:
                return found
    return None


async def _commons_search(client: httpx.AsyncClient, query: str) -> tuple[bytes, str] | None:
    """One Wikimedia Commons search, with a proper credit line."""
    words = [w for w in re.findall(r"[a-z]{4,}", query.lower())]
    try:
        r = await client.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": _UA}, timeout=8, params={
            "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 10,
            "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280})
        r.raise_for_status()
        pages = sorted((r.json().get("query", {}).get("pages") or {}).values(), key=lambda p: p.get("index", 99))
        for pg in pages:
            info = (pg.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            lic = _plain(meta.get("LicenseShortName", {}).get("value", ""))
            title = pg.get("title", "")
            desc = _plain(meta.get("ImageDescription", {}).get("value", ""))
            if info.get("mime") != "image/jpeg" or info.get("width", 0) < 1000 or _SKIP_TITLE.search(title):
                continue
            if not re.match(r"(?i)(cc by(-sa)? [\d.]+|cc0|public domain|pd)", lic):
                continue
            if words and not any(w in (title + " " + desc).lower() for w in words):
                continue
            img = await client.get(info.get("thumburl") or info["url"], headers={"User-Agent": _UA}, timeout=15)
            img.raise_for_status()
            artist = _plain(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons contributor"
            return await asyncio.to_thread(_to_webp, img.content), f"Photo: {artist[:60]} / Wikimedia Commons ({lic})"
    except Exception:  # noqa: BLE001
        return None
    return None


async def _download(client: httpx.AsyncClient, url: str, max_bytes: int = 8_000_000) -> bytes | None:
    async with client.stream("GET", url, headers={"User-Agent": _UA}, timeout=15) as r:
        if r.status_code != 200:
            return None
        buf = bytearray()
        async for chunk in r.aiter_bytes():
            buf += chunk
            if len(buf) > max_bytes:
                return None
        return bytes(buf)


async def _pixabay(client: httpx.AsyncClient, idea: ImageIdea, topic: str) -> tuple[bytes, str] | None:
    """Optional: free Pixabay key. Images are downloaded into our own storage (their terms forbid hotlinking)."""
    if not settings.pixabay_api_key:
        return None
    try:
        r = await client.get("https://pixabay.com/api/", timeout=8, params={
            "key": settings.pixabay_api_key, "q": (idea.query or topic)[:100], "image_type": "photo", "orientation": "horizontal",
            "safesearch": "true", "per_page": 5, "min_width": 1000})
        r.raise_for_status()
        hits = r.json().get("hits") or []
        if not hits:
            return None
        h = hits[0]
        raw = await _download(client, h.get("largeImageURL") or h["webformatURL"])
        if not raw:
            return None
        return await asyncio.to_thread(_to_webp, raw), f"Image by {h.get('user', 'a contributor')} from Pixabay"
    except Exception:  # noqa: BLE001
        return None


async def make_images(ideas: list[ImageIdea], topic: str) -> list[dict]:
    """One image per idea (max 3). Returns [{idx, mime, data, alt, credit, source}]."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def one(i: int, idea: ImageIdea) -> dict:
            data = await _gemini(client, topic, idea)
            if data:
                return {"idx": i, "mime": "image/webp", "data": data, "alt": idea.alt, "credit": "AI-generated image", "source": "gemini"}
            ph = await _pexels(client, idea, topic)
            if ph:
                return {"idx": i, "mime": "image/webp", "data": ph[0], "alt": idea.alt, "credit": ph[1], "source": "pexels"}
            px = await _pixabay(client, idea, topic)
            if px:
                return {"idx": i, "mime": "image/webp", "data": px[0], "alt": idea.alt, "credit": px[1], "source": "pixabay"}
            cm = await _commons(client, idea, topic)
            if cm:
                return {"idx": i, "mime": "image/webp", "data": cm[0], "alt": idea.alt, "credit": cm[1], "source": "commons"}
            data = await asyncio.to_thread(cover, f"{topic}|{idea.description}|{i}")
            return {"idx": i, "mime": "image/webp", "data": data, "alt": idea.alt, "credit": "", "source": "cover"}
        return list(await asyncio.gather(*[one(i, im) for i, im in enumerate(ideas[:3])]))
