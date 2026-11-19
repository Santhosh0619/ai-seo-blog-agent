"""Safe, read-only fetching of a user-supplied website (SSRF protection).

Rules: http/https only, standard ports only, the host must resolve to public IP addresses only, redirects are
re-checked at every hop, and the response size and time are limited. Only GET requests are ever made.
"""
import asyncio
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

from .errors import BAD_SITE

MAX_BYTES = 1_500_000
UA = "Mozilla/5.0 (compatible; RankwiseBot/1.0; read-only sitemap reader)"
_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def normalize_site(raw: str) -> str:
    """Return a clean origin like https://example.com, or raise BAD_SITE."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        p = urlparse(raw)
        host = (p.hostname or "").lower().rstrip(".")
        port = p.port
    except ValueError:
        raise BAD_SITE from None
    if p.scheme not in ("http", "https") or not host or p.username or p.password:
        raise BAD_SITE
    if port not in (None, 80, 443):
        raise BAD_SITE
    if not _HOST.match(host) and not _is_ip(host):
        raise BAD_SITE
    return f"{p.scheme}://{host}"


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


async def assert_public(host: str) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        raise BAD_SITE from None
    ips = {i[4][0] for i in infos}
    if not ips or not all(_public(ip) for ip in ips):
        raise BAD_SITE


async def safe_get(client: httpx.AsyncClient, url: str, max_redirects: int = 3, timeout: float = 8.0) -> str | None:
    """GET a text resource from a public host. Returns the text, or None if it is missing or too big."""
    for _ in range(max_redirects + 1):
        try:
            p = urlparse(url)
            ok = p.scheme in ("http", "https") and p.hostname and p.port in (None, 80, 443)
        except ValueError:
            ok = False
        if not ok:
            raise BAD_SITE
        await assert_public(p.hostname)
        async with client.stream("GET", url, follow_redirects=False, timeout=timeout, headers={"User-Agent": UA}) as r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code != 200:
                return None
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf += chunk
                if len(buf) > MAX_BYTES:
                    return None
            return buf.decode("utf-8", errors="ignore")
    return None
