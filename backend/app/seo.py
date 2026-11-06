"""Deterministic on-page SEO checks (no LLM). Produces a checklist + 0-100 score."""
import re

from .config import SITE
from .models import BlogPost

# Pages we link to that exist on the real site (confirmed in its sitemap); we only link, never modify.
FIXED_URLS = [f"{SITE}/digital-marketing-syllabus/", f"{SITE}/contact/", f"{SITE}/placement-training-in-coimbatore/"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def body_paragraphs(post: BlogPost) -> list[str]:
    paras = list(post.intro)
    for s in post.sections:
        paras += s.paragraphs + s.bullets
        for sub in s.subsections:
            paras += sub.paragraphs + sub.bullets
    for f in post.faqs:
        paras += [f.answer]
    return paras


def sanitize(post: BlogPost, known_urls: set[str]) -> BlogPost:
    """Drop internal links that don't exist on the real site (never trust LLM URLs)."""
    allowed = known_urls | set(FIXED_URLS)
    post.internal_links = [l for l in post.internal_links if l.url in allowed]
    slug = re.sub(r"[^a-z0-9-]+", "-", post.slug.lower()).strip("-")
    post.slug = re.sub(r"-{2,}", "-", slug) or "digital-marketing-guide"
    return post


def check(post: BlogPost, primary: str, secondary: list[str]) -> tuple[list[dict], int]:
    p = _norm(primary)
    text = _norm(" ".join(body_paragraphs(post) + [post.h1] + [s.heading for s in post.sections]))
    words = text.split()
    n = len(words)
    first100 = " ".join(words[:100])
    occ = len(re.findall(rf"\b{re.escape(p)}\b", text)) if p else 0
    density = (occ * len(p.split()) / n * 100) if n else 0.0
    sec_hit = sum(1 for k in secondary if _norm(k) and _norm(k) in text)
    body_text = " ".join(body_paragraphs(post)).lower()
    anchors_ok = sum(1 for l in post.internal_links if l.anchor.lower() in body_text)
    slug_hits = sum(1 for w in p.split() if w in post.slug.split("-"))
    h3 = sum(len(s.subsections) for s in post.sections)
    checks = [
        ("title", "SEO title is 30-60 characters and contains the primary keyword", 30 <= len(post.seo_title) <= 60 and p in _norm(post.seo_title), f"{len(post.seo_title)} chars"),
        ("meta", "Meta description is 120-160 characters and contains the primary keyword", 120 <= len(post.meta_description) <= 160 and p in _norm(post.meta_description), f"{len(post.meta_description)} chars"),
        ("slug", "URL slug is lowercase-hyphenated and uses the primary keyword words", bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", post.slug)) and slug_hits >= max(2, len(p.split()) - 1), post.slug),
        ("h1", "H1 contains the primary keyword", p in _norm(post.h1), post.h1[:60]),
        ("first100", "Primary keyword appears in the first 100 words", p in first100, ""),
        ("density", "Primary keyword density is 0.3-3%", 0.3 <= density <= 3.0, f"{density:.2f}% ({occ} uses)"),
        ("words", "Article has at least 1000 words", n >= 1000, f"{n} words"),
        ("h2", "At least 4 H2 sections", len(post.sections) >= 4, f"{len(post.sections)} H2"),
        ("h3", "At least 2 H3 subsections", h3 >= 2, f"{h3} H3"),
        ("secondary", "At least 2 secondary keywords used naturally", sec_hit >= min(2, len(secondary)), f"{sec_hit}/{len(secondary)}"),
        ("faq", "At least 4 FAQs", len(post.faqs) >= 4, f"{len(post.faqs)} FAQs"),
        ("links", "At least 3 valid internal links whose anchor text appears in the article", len(post.internal_links) >= 3 and anchors_ok >= 3, f"{len(post.internal_links)} links, {anchors_ok} anchored"),
        ("images", "At least 3 image suggestions with descriptive alt text (20+ chars)", len(post.images) >= 3 and all(len(i.alt) >= 20 for i in post.images), f"{len(post.images)} images"),
        ("cta", "Call to action for the Digital Marketing Course", bool(post.cta.text) and "digital marketing" in _norm(post.cta.heading + " " + post.cta.text), ""),
    ]
    items = [{"id": i, "label": l, "passed": bool(ok), "detail": d} for i, l, ok, d in checks]
    score = round(100 * sum(1 for c in items if c["passed"]) / len(items))
    return items, score
