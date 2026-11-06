"""Deterministic fake LLM outputs used ONLY by the automated tests (not part of the app)."""
from app.models import (CTA, FAQ, BlogPost, ImageIdea, InternalLink, KeywordInsight, OutlineSection, Plan, Section, Subsection)
from app.seo import FIXED_URLS

_FILL = [
    "Good digital marketing training balances theory with live practice, so every concept is tested on a real campaign or website.",
    "Start by learning how search engines, social platforms and paid ads work together, then specialise in the channel that fits your goals.",
    "Hands-on projects matter more than certificates, because employers want to see a portfolio of work that you can explain clearly.",
    "Analytics is the thread that connects every channel, so learn to read reports, set goals and judge results with simple metrics.",
    "Consistency beats intensity: a steady weekly routine of practice, review and small experiments builds skill faster than occasional bursts.",
    "Ask how often the curriculum is updated, because platforms and algorithms change quickly and old material loses value.",
    "Look for mentors who have run real campaigns and can share mistakes as well as successes, since that is where most learning happens.",
    "Local context helps too: understanding how Coimbatore businesses find customers makes your practice projects more realistic.",
]


def _para(i: int, extra: str = "") -> str:
    s = [_FILL[(i + k) % len(_FILL)] for k in range(5)]
    return " ".join(s) + (" " + extra if extra else "")


def sim_plan(ctx: dict) -> Plan:
    short = ctx["shortlist"]
    primary = short[0]["keyword"]
    secondary = [c["keyword"] for c in short[1:6]]
    insights = [KeywordInsight(keyword=c["keyword"], intent="commercial" if "course" in c["keyword"] else "informational",
                               relevance="high", competition="medium" if c["status"] != "gap" else "low",
                               volume_band="medium", note="Simulated estimate (testing fixture).") for c in short[:8]]
    outline = [OutlineSection(h2=h, h3s=h3) for h, h3 in [
        (f"What to expect from {primary}", ["Who it suits", "Skills you build"]),
        ("Core modules to look for", ["Search and content", "Paid ads and analytics"]),
        ("How to judge a training provider", []), ("A practical learning roadmap", ["First 30 days"]),
        ("Career paths after training", []), ("Next steps", [])]]
    slug = "-".join(primary.split()[:7])
    return Plan(primary_keyword=primary, secondary_keywords=secondary, topic=f"{primary.title()}: what to look for", slug=slug,
                audience="Students and career-switchers in Coimbatore", search_intent="Commercial investigation: comparing options before enrolling",
                reasoning="Simulated reasoning: this keyword has the lowest overlap with existing Appin pages.", insights=insights, outline=outline)


def sim_post(ctx: dict) -> BlogPost:
    plan: Plan = ctx["plan"]
    p, sec = plan.primary_keyword, plan.secondary_keywords
    title = (p.title() + " | Appin")[:60] if len(p) < 50 else p.title()[:60]
    meta = f"Planning {p}? See the modules, projects and questions that matter, with practical advice from Appin Technology's Coimbatore team."
    meta = (meta + " Read the guide.")[:158] if len(meta) < 120 else meta[:158]
    sections = []
    for i, o in enumerate(plan.outline):
        extra = f"If you are comparing options for {p}, use this section as a checklist." if i in (0, 2, 4) else ""
        if i == 1 and sec:
            extra += f" Many learners also search for {sec[0]}."
        if i == 3 and len(sec) > 1:
            extra += f" Related topics include {sec[1]}."
        subs = [Subsection(heading=h, paragraphs=[_para(i + j + 2)], bullets=[]) for j, h in enumerate(o.h3s)]
        sections.append(Section(heading=o.h2, paragraphs=[_para(i, extra), _para(i + 3)], bullets=[_FILL[i % 8][:80], _FILL[(i + 1) % 8][:80]], subsections=subs))
    sections[2].paragraphs.append("Review the digital marketing syllabus carefully before you decide, and contact the Appin team with any questions about placement training in Coimbatore.")
    intro = [f"Choosing {p} is a big decision, so this guide walks through what to look for. " + _para(0), _para(4)]
    faqs = [FAQ(question=q, answer=f"{_FILL[i]} {_FILL[i + 1]}" + (f" This applies to {p} too." if i == 0 else ""))
            for i, q in enumerate(["Who can join?", "Do I need a technical background?", "How should I practise?", "What projects should I build?", "How do I choose a provider?"])]
    links = [InternalLink(anchor="digital marketing syllabus", url=FIXED_URLS[0], reason="Shows the topics covered"),
             InternalLink(anchor="contact the Appin team", url=FIXED_URLS[1], reason="Lets readers ask questions"),
             InternalLink(anchor="placement training in Coimbatore", url=FIXED_URLS[2], reason="Career-support information")]
    images = [ImageIdea(description=f"Students working on a live campaign dashboard in a classroom ({p})", alt="Students analysing a digital marketing campaign dashboard together in a Coimbatore classroom", placement="After the introduction"),
              ImageIdea(description="Roadmap graphic of the learning path", alt="Step-by-step roadmap graphic showing the stages of learning digital marketing", placement="In the roadmap section"),
              ImageIdea(description="Mentor reviewing a student's portfolio", alt="Mentor reviewing a student's digital marketing portfolio on a laptop", placement="Near the end")]
    cta = CTA(heading="Start your Digital Marketing journey with Appin Technology", text="Download the Digital Marketing syllabus or enquire about the Digital Marketing course in Coimbatore with placement assistance.", button_text="Enquire about the course")
    return BlogPost(seo_title=title, meta_description=meta, slug=plan.slug, h1=plan.topic if p in plan.topic.lower() else f"{plan.topic} ({p})",
                    intro=intro, sections=sections, faqs=faqs, internal_links=links, images=images, cta=cta, secondary_keywords_used=sec[:3])
