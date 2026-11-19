"""The article page: real server-rendered HTML (no JavaScript needed), fully HTML-escaped.

Modes: "preview" (inside the app) and "share" (public share link) are noindex pages whose images load from /img/<token>;
"export" is a self-contained download (images in ./images/) meant to be hosted by the user.
"""
import json
import re
from datetime import datetime

from jinja2 import Environment
from markupsafe import Markup, escape

from .config import PRODUCT_NAME

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--text:#1a1d24;--muted:#626a79;--line:#e6e3dc;--brand:#3a4bd6;--brand2:#7a3ad6;--soft:#eef0ff;--cap:#7d8493}
@media (prefers-color-scheme:dark){:root{--bg:#0e1017;--card:#161923;--text:#e9ecf4;--muted:#a1a9bb;--line:#272c3b;--brand:#8a98ff;--brand2:#b690ff;--soft:#1c2036;--cap:#8a92a6}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:18px/1.75 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--brand);text-underline-offset:3px}
.bar{height:4px;background:linear-gradient(90deg,var(--brand),var(--brand2))}
.wrap{max-width:740px;margin:0 auto;padding:0 22px}
.top{display:flex;justify-content:space-between;align-items:center;padding:20px 0;font-size:14px;color:var(--muted)}
.top b{color:var(--text);letter-spacing:-.01em}
.kicker{display:inline-block;font-size:12.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--brand);background:var(--soft);padding:5px 11px;border-radius:99px}
h1,h2,h3{font-family:ui-serif,Georgia,Cambria,"Times New Roman",serif;letter-spacing:-.015em;line-height:1.2}
h1{font-size:clamp(2rem,5.2vw,3.05rem);margin:.45em 0 .3em;font-weight:700}
h2{font-size:1.75rem;margin:2.1em 0 .45em;scroll-margin-top:20px}h3{font-size:1.3rem;margin:1.6em 0 .3em}
.by{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14.5px;color:var(--muted);margin-bottom:26px}
.hero{margin:0 0 30px}.hero img,figure img{width:100%;height:auto;display:block;border-radius:18px;background:var(--line)}
figure{margin:32px 0}figcaption{font-size:13px;color:var(--cap);margin-top:9px;line-height:1.5}
.lead p:first-child{font-size:1.22rem;line-height:1.65;color:var(--text)}
.take{background:var(--soft);border:1px solid var(--line);border-radius:18px;padding:20px 24px;margin:26px 0}
.take b{display:block;font-family:ui-sans-serif,system-ui,sans-serif;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--brand);margin-bottom:6px}
.take ul{margin:0;padding-left:20px}.take li{margin:7px 0}
.toc{border:1px solid var(--line);border-radius:16px;background:var(--card);padding:6px 20px;margin:26px 0}
.toc summary{cursor:pointer;font-weight:700;padding:12px 0;font-size:16px}.toc ol{margin:0 0 14px;padding-left:20px;font-size:16px}.toc li{margin:5px 0}
details.faq{border:1px solid var(--line);border-radius:14px;background:var(--card);padding:4px 18px;margin:10px 0}
details.faq summary{cursor:pointer;font-weight:650;padding:13px 0;font-size:17px}details.faq p{margin:0 0 14px;color:var(--muted)}
.src li{margin:6px 0;font-size:16px}
.cta{background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;border-radius:22px;padding:30px 30px 32px;margin:44px 0}
.cta h2{margin:0 0 8px;color:#fff;font-size:1.6rem}.cta p{margin:0 0 4px;opacity:.95}
.cta a{display:inline-block;margin-top:16px;background:#fff;color:#2b2f6e;text-decoration:none;font-weight:700;padding:12px 22px;border-radius:12px}
.rel li{margin:8px 0}
footer{color:var(--muted);font-size:13.5px;text-align:center;padding:14px 0 54px}
@media(max-width:600px){body{font-size:17px}.wrap{padding:0 18px}h2{font-size:1.5rem}.cta{padding:24px 22px}}
@media print{.bar,.top,.cta a{display:none}body{background:#fff;color:#000}}
"""

TEMPLATE = """<!doctype html>
<html lang="{{ lang }}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ post.seo_title }}</title>
<meta name="description" content="{{ post.meta_description }}">
{% if canonical %}<link rel="canonical" href="{{ canonical }}">{% endif %}
<meta name="robots" content="{{ robots }}">
<meta property="og:type" content="article"><meta property="og:title" content="{{ post.seo_title }}">
<meta property="og:description" content="{{ post.meta_description }}">{% if canonical %}<meta property="og:url" content="{{ canonical }}">{% endif %}
{% if hero_abs %}<meta property="og:image" content="{{ hero_abs }}"><meta name="twitter:image" content="{{ hero_abs }}">{% endif %}
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{{ post.seo_title }}"><meta name="twitter:description" content="{{ post.meta_description }}">
<style>{{ css }}</style>
<script type="application/ld+json">{{ jsonld }}</script>
</head><body>
<div class="bar"></div>
<div class="wrap">
<div class="top"><b>{{ site_label }}</b><span>{{ date }}</span></div>
<article>
<span class="kicker">{{ primary }}</span>
<h1>{{ post.h1 }}</h1>
<div class="by">{% if author %}<span>By {{ author }}</span>{% endif %}<span>Updated {{ date }}</span><span>{{ read_min }} min read</span></div>
{% if hero %}<figure class="hero"><img src="{{ hero.src }}" alt="{{ hero.alt }}" width="1280" height="720" fetchpriority="high">{% if hero.credit %}<figcaption>{{ hero.credit }}</figcaption>{% endif %}</figure>{% endif %}
<div class="lead">{% for p in intro %}<p>{{ p }}</p>{% endfor %}</div>
{% if post.takeaways %}<aside class="take"><b>Key takeaways</b><ul>{% for t in post.takeaways %}<li>{{ t }}</li>{% endfor %}</ul></aside>{% endif %}
<details class="toc" open><summary>In this guide</summary><ol>{% for s in post.sections %}<li><a href="#s{{ loop.index }}">{{ s.heading }}</a></li>{% endfor %}<li><a href="#faq">Frequently asked questions</a></li></ol></details>
{% for s in sections %}
<h2 id="s{{ loop.index }}">{{ s.heading }}</h2>
{% for p in s.paragraphs %}<p>{{ p }}</p>{% endfor %}
{% if s.bullets %}<ul>{% for b in s.bullets %}<li>{{ b }}</li>{% endfor %}</ul>{% endif %}
{% for sub in s.subsections %}<h3>{{ sub.heading }}</h3>{% for p in sub.paragraphs %}<p>{{ p }}</p>{% endfor %}{% if sub.bullets %}<ul>{% for b in sub.bullets %}<li>{{ b }}</li>{% endfor %}</ul>{% endif %}{% endfor %}
{% set k = loop.index0 %}{% if k in inline %}{% set im = inline[k] %}<figure><img src="{{ im.src }}" alt="{{ im.alt }}" width="1280" height="720" loading="lazy">{% if im.credit %}<figcaption>{{ im.credit }}</figcaption>{% endif %}</figure>{% endif %}
{% endfor %}
<h2 id="faq">Frequently asked questions</h2>
{% for f in post.faqs %}<details class="faq"><summary>{{ f.question }}</summary><p>{{ f.answer }}</p></details>{% endfor %}
{% if post.sources %}<h2>Sources</h2><ul class="src">{% for s in post.sources %}<li><a href="{{ s.url }}" rel="noopener nofollow" target="_blank">{{ s.title }}</a></li>{% endfor %}</ul>{% endif %}
<section class="cta"><h2>{{ post.cta.heading }}</h2><p>{{ post.cta.text }}</p>{% if cta_url %}<a href="{{ cta_url }}" rel="noopener">{{ post.cta.button_text }}</a>{% endif %}</section>
{% if post.internal_links %}<h2>Related reading</h2><ul class="rel">{% for l in post.internal_links %}<li><a href="{{ l.url }}">{{ l.anchor }}</a>: {{ l.reason }}</li>{% endfor %}</ul>{% endif %}
</article>
<footer>{{ footer }}</footer>
</div>
</body></html>"""

_env = Environment(autoescape=True)


def linkify(text: str, links: list, used: set) -> Markup:
    """Escape text, then link the FIRST occurrence of each internal-link anchor (once per page)."""
    out = str(escape(text))
    for l in links:
        if l["url"] in used:
            continue
        a = str(escape(l["anchor"]))
        m = re.search(re.escape(a), out, re.I)
        if m:
            used.add(l["url"])
            out = out[:m.start()] + f'<a href="{escape(l["url"])}">{m.group(0)}</a>' + out[m.end():]
    return Markup(out)


def word_count(post: dict) -> int:
    paras = list(post["intro"])
    for s in post["sections"]:
        paras += s["paragraphs"] + s["bullets"]
        for sub in s["subsections"]:
            paras += sub["paragraphs"] + sub["bullets"]
    paras += [f["answer"] for f in post["faqs"]]
    return sum(len(p.split()) for p in paras)


def render_article(page: dict, images: list[dict], mode: str = "preview", base: str = "") -> str:
    post = page["post"]
    req = page.get("request") or {}
    used: set = set()
    links = post["internal_links"]
    intro = [linkify(p, links, used) for p in post["intro"]]
    sections = [{
        "heading": s["heading"], "bullets": s["bullets"],
        "paragraphs": [linkify(p, links, used) for p in s["paragraphs"]],
        "subsections": [{"heading": u["heading"], "bullets": u["bullets"], "paragraphs": [linkify(p, links, used) for p in u["paragraphs"]]} for u in s["subsections"]],
    } for s in post["sections"]]

    def src(im: dict) -> str:
        return f"images/{im['idx'] + 1}.webp" if mode == "export" else f"{base}/img/{im['token']}"

    pics = [{"src": src(im), "alt": im["alt"], "credit": im["credit"], "idx": im["idx"]} for im in images]
    hero = pics[0] if pics else None
    inline = {}
    for n, im in enumerate(pics[1:3]):  # place inline images after the 2nd and 4th section
        inline[min(1 + 2 * n, len(sections) - 1)] = im
    created = datetime.fromisoformat(page["created_at"]) if page.get("created_at") else datetime.utcnow()
    date = created.strftime("%d %b %Y")
    canonical = f"{base}/s/{page['share_token']}" if mode == "share" and page.get("share_token") and base else ""
    robots = "index,follow" if mode == "export" else "noindex,nofollow"
    hero_abs = f"{base}/img/{images[0]['token']}" if images and mode != "export" and base else ""
    site = (req.get("site_url") or "").strip()
    author = (req.get("author") or "").strip()
    ld = [
        {"@context": "https://schema.org", "@type": "Article", "headline": post["seo_title"], "description": post["meta_description"],
         "datePublished": created.isoformat(), "dateModified": created.isoformat(), "inLanguage": req.get("language", "en"),
         **({"image": [hero_abs]} if hero_abs else {}), **({"author": {"@type": "Person", "name": author}} if author else {}),
         **({"mainEntityOfPage": canonical} if canonical else {})},
        {"@context": "https://schema.org", "@type": "FAQPage",
         "mainEntity": [{"@type": "Question", "name": f["question"], "acceptedAnswer": {"@type": "Answer", "text": f["answer"]}} for f in post["faqs"]]},
    ]
    footer = f"Made with {PRODUCT_NAME}" if mode != "export" else f"Made with {PRODUCT_NAME}. You can remove this line."
    return _env.from_string(TEMPLATE).render(
        post=post, intro=intro, sections=sections, css=Markup(CSS), jsonld=Markup(json.dumps(ld).replace("</", "<\\/")), canonical=canonical,
        robots=robots, hero=hero, hero_abs=hero_abs, inline=inline, primary=page["primary_keyword"], date=date, author=author,
        read_min=max(1, round(word_count(post) / 220)), cta_url=site, lang=req.get("language", "en"),
        site_label=(re.sub(r"^https?://", "", site) if site else PRODUCT_NAME), footer=footer)


def to_markdown(page: dict) -> str:
    p = page["post"]
    out = [f"---\ntitle: \"{p['seo_title']}\"\ndescription: \"{p['meta_description']}\"\nslug: {p['slug']}\nkeyword: \"{page['primary_keyword']}\"\n---\n", f"# {p['h1']}\n"]
    out += [f"{x}\n" for x in p["intro"]]
    if p["takeaways"]:
        out.append("## Key takeaways\n" + "\n".join(f"- {t}" for t in p["takeaways"]) + "\n")
    for s in p["sections"]:
        out.append(f"## {s['heading']}\n")
        out += [f"{x}\n" for x in s["paragraphs"]]
        if s["bullets"]:
            out.append("\n".join(f"- {b}" for b in s["bullets"]) + "\n")
        for u in s["subsections"]:
            out.append(f"### {u['heading']}\n")
            out += [f"{x}\n" for x in u["paragraphs"]]
            if u["bullets"]:
                out.append("\n".join(f"- {b}" for b in u["bullets"]) + "\n")
    out.append("## Frequently asked questions\n")
    for f in p["faqs"]:
        out.append(f"**{f['question']}**\n\n{f['answer']}\n")
    if p["sources"]:
        out.append("## Sources\n" + "\n".join(f"- [{s['title']}]({s['url']})" for s in p["sources"]) + "\n")
    return "\n".join(out)
