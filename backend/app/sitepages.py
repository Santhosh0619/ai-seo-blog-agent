"""The product's own SEO: per-page title, description, robots and canonical for the React app, plus robots.txt and sitemap.xml.

The React build is a single index.html. We fill its placeholders on every request, so crawlers and social previews get
the right tags for each address without running JavaScript, and the absolute URLs always match the real domain.
"""
import html

from .config import PRODUCT_NAME

DESC = ("An AI agent that researches real keywords, avoids topics you already cover, writes an original article with images "
        "and scores it with 22 transparent SEO checks. Free to try.")

# path -> (title, description, robots)
PAGES: dict[str, tuple[str, str, str]] = {
    "": (f"{PRODUCT_NAME}: SEO blog pages for any topic", DESC, "index,follow"),
    "privacy": (f"Privacy | {PRODUCT_NAME}", f"How {PRODUCT_NAME} handles your data: what it stores, what it never stores and how to delete everything.", "index,follow"),
    "login": (f"Sign in | {PRODUCT_NAME}", f"Sign in to {PRODUCT_NAME} to create and manage your SEO blog pages.", "noindex,follow"),
    "signup": (f"Create an account | {PRODUCT_NAME}", f"Create a free {PRODUCT_NAME} account: 2 SEO blog pages a day, no card needed.", "noindex,follow"),
    "forgot": (f"Forgot password | {PRODUCT_NAME}", f"Forgot your {PRODUCT_NAME} password? Enter your email and we will send you a link to choose a new one.", "noindex,nofollow"),
    "reset": (f"Choose a new password | {PRODUCT_NAME}", f"Choose a new password for your {PRODUCT_NAME} account. The link from your email works once.", "noindex,nofollow"),
}
APP_DEFAULT = (PRODUCT_NAME, DESC, "noindex,nofollow")  # everything inside /app and anything unknown
INDEXED = ("", "privacy")  # the pages that belong in the sitemap


def render_index(template: str, base: str, path: str) -> str:
    key = path.strip("/")
    title, desc, robots = PAGES.get(key, APP_DEFAULT)
    canonical = f"{base}/{key}" if key else f"{base}/"
    out = (template.replace("__TITLE__", html.escape(title)).replace("__DESC__", html.escape(desc, quote=True))
           .replace("__ROBOTS__", robots).replace("__CANONICAL__", html.escape(canonical, quote=True))
           .replace("__BASE__", html.escape(base, quote=True)))
    return out


def robots_txt(base: str) -> str:
    return ("User-agent: *\nAllow: /\nDisallow: /app/\nDisallow: /api/\nDisallow: /s/\nDisallow: /img/\nDisallow: /reset\n"
            f"\nSitemap: {base}/sitemap.xml\n")


def sitemap_xml(base: str) -> str:
    urls = "".join(f"<url><loc>{html.escape(base + '/' + p if p else base + '/')}</loc></url>" for p in INDEXED)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
