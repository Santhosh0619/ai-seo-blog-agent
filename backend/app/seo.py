"""Deterministic on-page SEO engine (no LLM). Produces a checklist, group scores and a 0-100 score.

Groups: A On-page basics (30) · B Content quality (30) · C Trust and originality (20) · D Technical (20).
A check can be "not applicable" (for example internal links when there is nothing to link to): it is then ignored.
"""
import json
import re
from dataclasses import dataclass, field

from .models import BlogPost

GROUPS = {"onpage": ("On-page basics", 30), "content": ("Content quality", 30), "trust": ("Trust and originality", 20), "tech": ("Technical SEO", 20)}

CLICHES = [
    "in today's fast-paced world", "in today's digital age", "in the ever-evolving", "ever-evolving landscape", "delve into", "delve deeper",
    "unlock the power", "unlock the secrets", "game-changer", "game changer", "dive into", "navigate the world of", "in conclusion,",
    "it's important to note that", "it is important to note that", "look no further", "take it to the next level", "to the next level", "tapestry",
    "rapidly evolving", "plays a crucial role", "plays a vital role", "whether you're a beginner or", "at the end of the day",
]


@dataclass
class Ctx:
    primary: str
    secondary: list[str] = field(default_factory=list)
    facts_text: str = ""            # user notes + reference text: numbers are allowed only if they appear here
    prior_texts: list[str] = field(default_factory=list)   # body text of the user's earlier pages
    link_pool: int = 0              # internal URLs the writer was allowed to use
    sources_provided: bool = False
    word_min: int = 1000
    word_max: int = 2600


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


def body_text(post: BlogPost) -> str:
    return " ".join(body_paragraphs(post) + post.takeaways)


def sanitize(post: BlogPost, known_urls: set[str], source_urls: set[str]) -> BlogPost:
    """Never trust model URLs: keep only internal links and sources that we provided."""
    post.internal_links = [l for l in post.internal_links if l.url in known_urls]
    post.sources = [s for s in post.sources if s.url in source_urls]
    slug = re.sub(r"[^a-z0-9-]+", "-", post.slug.lower()).strip("-")
    post.slug = re.sub(r"-{2,}", "-", slug)[:80].strip("-") or "blog-post"
    return post


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def flesch(text: str) -> float:
    sentences = max(1, len(re.findall(r"[.!?]+(?:\s|$)", text)))
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 0.0
    syl = sum(_syllables(w) for w in words)
    return 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syl / len(words))


def shingles(text: str, n: int = 4) -> set[str]:
    w = _norm(text).split()
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def similarity(a: str, b: str) -> float:
    """Share of the new text's 4-word phrases that already appear in the older text (0 to 1)."""
    sa, sb = shingles(a), shingles(b)
    return len(sa & sb) / len(sa) if sa else 0.0


_STAT = re.compile(r"(\$\s?\d[\d,.]*|\d[\d,.]*\s?%|\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\s?(?:million|billion|lakh|crore|thousand)\b)", re.I)


def unsourced_numbers(text: str, facts: str) -> list[str]:
    allowed = re.sub(r"\s+", "", facts.lower())
    bad = []
    for m in _STAT.findall(text):
        key = re.sub(r"\s+", "", m.lower())
        if key not in allowed and m not in bad:
            bad.append(m)
    return bad


def json_ld_ok(post: BlogPost) -> bool:
    try:
        ld = {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": f.question, "acceptedAnswer": {"@type": "Answer", "text": f.answer}} for f in post.faqs]}
        json.loads(json.dumps(ld))
        return bool(post.faqs) and bool(post.seo_title and post.meta_description)
    except (TypeError, ValueError):
        return False


def check(post: BlogPost, ctx: Ctx) -> tuple[list[dict], int, dict]:
    p = _norm(ctx.primary)
    paras = body_paragraphs(post)
    text = _norm(" ".join(paras + [post.h1] + [s.heading for s in post.sections]))
    words = text.split()
    n = len(words)
    first100 = " ".join(_norm(" ".join(post.intro)).split()[:100])
    occ = len(re.findall(rf"\b{re.escape(p)}\b", text)) if p else 0
    density = (occ * len(p.split()) / n * 100) if n else 0.0
    sec_hit = sum(1 for k in ctx.secondary if _norm(k) and _norm(k) in text)
    plain = " ".join(paras)
    anchors_ok = sum(1 for l in post.internal_links if l.anchor.lower() in plain.lower())
    slug_hits = sum(1 for w in p.split() if w in post.slug.split("-"))
    h3 = sum(len(s.subsections) for s in post.sections)
    empty_h2 = sum(1 for s in post.sections if not (s.paragraphs or s.bullets or s.subsections))
    faq_words = [len(f.answer.split()) for f in post.faqs]
    avg_para = (sum(len(x.split()) for x in paras) / len(paras)) if paras else 0
    max_para = max((len(x.split()) for x in paras), default=0)
    fl = flesch(plain)
    cliche_hits = [c for c in CLICHES if c in plain.lower()]
    bad_nums = unsourced_numbers(plain + " " + " ".join(f.answer for f in post.faqs), ctx.facts_text)
    sims = [similarity(plain, t) for t in ctx.prior_texts if t]
    top_sim = max(sims) if sims else 0.0
    ext_ok = all(s.url.startswith("https://") for s in post.sources) and all(l.url.startswith(("http://", "https://", "/")) for l in post.internal_links)

    # (id, group, label, passed, detail, applicable, why, fix)
    rows = [
        ("title", "onpage", "SEO title is 30-60 characters and contains the primary keyword", 30 <= len(post.seo_title) <= 60 and p in _norm(post.seo_title), f"{len(post.seo_title)} characters", True,
         "The title is the blue link people see in Google. Too long gets cut off; the keyword tells Google what the page is about.", "Shorten or rewrite the title so it is 30 to 60 characters and includes the main keyword."),
        ("meta", "onpage", "Meta description is 120-160 characters and contains the primary keyword", 120 <= len(post.meta_description) <= 160 and p in _norm(post.meta_description), f"{len(post.meta_description)} characters", True,
         "It is the text under the title in search results and decides whether people click.", "Write one clear sentence of 120 to 160 characters with the keyword and a reason to click."),
        ("slug", "onpage", "URL slug is short, lowercase and uses the keyword words", bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", post.slug)) and slug_hits >= max(2, len(p.split()) - 1), post.slug, True,
         "A readable URL helps people and search engines understand the page.", "Use lowercase words joined by hyphens that include the main keyword words."),
        ("h1", "onpage", "H1 contains the primary keyword", p in _norm(post.h1), post.h1[:70], True,
         "The H1 is the page headline. Google reads it as the main topic.", "Put the primary keyword naturally in the H1."),
        ("first100", "onpage", "Primary keyword appears in the first 100 words", p in first100, "", True,
         "Saying the topic early shows readers and Google that the page answers the search.", "Mention the main keyword naturally in the first paragraph."),
        ("density", "onpage", "Primary keyword density is 0.5-2.5% (not stuffed)", 0.5 <= density <= 2.5, f"{density:.2f}% ({occ} uses)", True,
         "Too few mentions is unclear; too many looks like keyword stuffing.", "Use the keyword naturally 5 to 8 times, and use related phrases elsewhere."),
        ("structure", "onpage", "At least 4 H2 sections, none empty", len(post.sections) >= 4 and empty_h2 == 0, f"{len(post.sections)} H2, {empty_h2} empty", True,
         "Clear headings make the page easy to scan and give Google its structure.", "Add or fill H2 sections so every heading has content."),
        ("words", "content", f"Article length is {ctx.word_min}-{ctx.word_max} words", ctx.word_min <= n <= ctx.word_max, f"{n} words", True,
         "Thin pages rarely satisfy a search; very long pages lose readers.", "Add depth with examples and steps, or trim repetition."),
        ("h3", "content", "At least 2 H3 subsections", h3 >= 2, f"{h3} H3", True,
         "Subheadings break long sections into easy parts.", "Add H3 subsections inside the longest sections."),
        ("secondary", "content", "At least 2 secondary keywords used naturally", sec_hit >= min(2, len(ctx.secondary)), f"{sec_hit}/{len(ctx.secondary)} used", True,
         "Related phrases help the page match more searches.", "Work the supporting keywords into headings and sentences naturally."),
        ("faq", "content", "At least 4 FAQs with short, direct answers (15-90 words)", len(post.faqs) >= 4 and all(15 <= w <= 90 for w in faq_words), f"{len(post.faqs)} FAQs", True,
         "FAQs answer real questions and can appear directly in Google.", "Write 4 to 5 real questions with answers of 15 to 90 words."),
        ("readability", "content", "Easy to read (Flesch reading ease 45 or higher)", fl >= 45, f"score {fl:.0f}", True,
         "Simple sentences keep readers on the page.", "Use shorter sentences and everyday words."),
        ("paragraphs", "content", "Short paragraphs (average under 80 words, none over 140)", avg_para <= 80 and max_para <= 140, f"avg {avg_para:.0f}, longest {max_para} words", True,
         "Walls of text are hard to read on a phone.", "Split long paragraphs into 2 to 4 sentences."),
        ("takeaways", "content", "Key takeaways box with at least 3 points", len(post.takeaways) >= 3, f"{len(post.takeaways)} points", True,
         "A summary helps skimmers and can be reused by search features.", "Add 3 to 5 short key takeaways."),
        ("numbers", "trust", "No unsourced statistics or prices", not bad_nums, ", ".join(bad_nums[:3]) if bad_nums else "none found", True,
         "Made-up numbers hurt trust. Numbers must come from your notes or a cited source.", "Remove the numbers or move them into your notes with a source."),
        ("cliches", "trust", "Avoids stock AI phrases (at most 1)", len(cliche_hits) <= 1, ", ".join(cliche_hits[:3]) if cliche_hits else "none found", True,
         "Generic phrases make a page sound written by a machine.", "Replace stock phrases with specific, concrete wording."),
        ("unique", "trust", "Different from your earlier pages (under 15% repeated phrases)", top_sim < 0.15, f"{top_sim * 100:.0f}% repeated" if sims else "no earlier pages", bool(sims),
         "Repeating yourself competes with your own pages.", "Choose a different angle and rewrite the repeated parts."),
        ("sources", "trust", "Cites at least one real source", len(post.sources) >= 1, f"{len(post.sources)} source{'s' if len(post.sources) != 1 else ''}", ctx.sources_provided,
         "Sources show where facts come from.", "Add the provided sources to the Sources section."),
        ("images", "tech", "At least 3 images, each with descriptive alt text (20+ characters)", len(post.images) >= 3 and all(len(i.alt) >= 20 for i in post.images), f"{len(post.images)} images", True,
         "Images improve the page and alt text helps search and accessibility.", "Add 3 images with alt text that describes each picture."),
        ("links", "tech", "At least 3 valid internal links with the anchor in the text", len(post.internal_links) >= 3 and anchors_ok >= 3, f"{len(post.internal_links)} links, {anchors_ok} in text", ctx.link_pool >= 3,
         "Internal links help people and Google find related pages.", "Link 3 to 5 related pages from the allowed list, using words that appear in the text."),
        ("schema", "tech", "Article and FAQ structured data can be built", json_ld_ok(post), "", True,
         "Structured data helps Google understand the page.", "Make sure the title, meta description and FAQs are filled in."),
        ("links_safe", "tech", "All links are safe (https sources, no scripts)", ext_ok, "", True,
         "Unsafe links hurt trust and security.", "Use only https links."),
    ]
    items = [{"id": i, "group": g, "label": l, "passed": bool(ok), "detail": d, "applicable": bool(a), "why": w, "fix": f} for i, g, l, ok, d, a, w, f in rows]
    return items, *score(items)


def score(items: list[dict]) -> tuple[int, dict]:
    groups, total_w, got = {}, 0.0, 0.0
    for gid, (name, weight) in GROUPS.items():
        rel = [c for c in items if c["group"] == gid and c["applicable"]]
        frac = (sum(1 for c in rel if c["passed"]) / len(rel)) if rel else 1.0
        groups[gid] = {"name": name, "weight": weight, "score": round(frac * 100), "passed": sum(1 for c in rel if c["passed"]), "total": len(rel)}
        total_w += weight
        got += weight * frac
    return round(100 * got / total_w), groups
