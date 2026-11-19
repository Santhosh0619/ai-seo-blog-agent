"""Deterministic fake LLM / research / images used ONLY by the automated tests (not part of the app)."""
from app.llm import current_key
from app.models import (CTA, FAQ, BlogPost, ImageIdea, InternalLink, KeywordInsight, OutlineSection, Plan, Section, Seeds, SourceRef, Subsection)

SITE = "https://example.com"
SITE_ITEMS = [{"url": f"{SITE}/{s}/", "title": s.replace("-", " ")} for s in ("beginner-guide", "equipment-care", "training-plan", "common-mistakes", "buying-advice")]
FACTS = [{"title": "Cricket bat", "url": "https://en.wikipedia.org/wiki/Cricket_bat", "extract": "A cricket bat is a specialised piece of equipment used by batters to hit the ball."}]
KEYWORDS = ["cricket bat for beginners", "how to choose a cricket bat", "cricket bat weight guide", "cricket bat care tips", "best cricket bat size",
            "cricket bat knocking in", "cricket bat grip types", "junior cricket bat guide", "cricket bat vs tennis ball bat", "cricket bat wood types"]

_FILL = [
    "Start small and practise every day.", "Keep the basics simple and clear.", "Good habits build skill over time.",
    "Watch how experienced players do it.", "Ask for feedback and fix one thing at a time.", "Short sessions work better than long ones.",
    "Write down what worked and what did not.", "Choose gear that fits your size and your budget.", "Look after your equipment and it will last.",
    "Mistakes are normal, so learn from each one.", "Compare a few options before you decide.", "Take your time and enjoy the process.",
]


def _para(i: int, extra: str = "") -> str:
    return " ".join(_FILL[(i + k) % len(_FILL)] for k in range(5)) + (" " + extra if extra else "")


def fake_candidates() -> list[dict]:
    return [{"keyword": k, "source": "Google Autocomplete (live)", "verified": True, "seed": "cricket bat"} for k in KEYWORDS]


async def fake_research(req, seeds, site_origin):
    return {"candidates": fake_candidates(), "keyword_source": "Google Autocomplete (live)", "facts": list(FACTS),
            "site": {"items": list(SITE_ITEMS) if site_origin else [], "note": "fake sitemap" if site_origin else "No website given"}}


def make_plan(primary: str, secondary: list[str]) -> Plan:
    outline = [OutlineSection(h2=h, h3s=h3) for h, h3 in [
        (f"What {primary} really means", ["Who it suits", "Common questions"]), ("How to choose well", ["Size and weight", "Budget"]),
        ("Care and maintenance", []), ("A simple weekly routine", ["First month"]), ("Mistakes to avoid", []), ("Next steps", [])]]
    insights = [KeywordInsight(keyword=k, intent="informational", relevance="high", competition="low", volume_band="medium", note="AI estimate in tests.") for k in [primary, *secondary][:8]]
    return Plan(primary_keyword=primary, secondary_keywords=secondary, reasoning="Lowest overlap with existing pages.", topic=f"{primary.title()}: a practical guide",
                angle="A calm, step by step guide for first-time buyers", slug="-".join(primary.split()[:7]), audience="Beginners", search_intent="Informational", insights=insights, outline=outline)


def good_post(plan: Plan, links: bool = True) -> BlogPost:
    p, sec = plan.primary_keyword, plan.secondary_keywords
    sections = []
    for i, o in enumerate(plan.outline):
        extra = f"This helps when you think about {p}." if i in (0, 2, 4) else ""
        if i == 1 and sec:
            extra += f" Many people also search for {sec[0]}."
        if i == 3 and len(sec) > 1:
            extra += f" Related ideas include {sec[1]}."
        if i == 2:
            extra += " Read the beginner guide and the equipment care page for more help."
        if i == 4:
            extra += " The training plan and the common mistakes page go deeper."
        subs = [Subsection(heading=h, paragraphs=[_para(i + j + 2), _para(i + j + 5)], bullets=[]) for j, h in enumerate(o.h3s)]
        sections.append(Section(heading=o.h2, paragraphs=[_para(i, extra), _para(i + 3), _para(i + 6)], bullets=[_FILL[i % 12], _FILL[(i + 1) % 12]], subsections=subs))
    intro = [f"Choosing {p} is easier when you follow a simple plan. " + _para(0), _para(4)]
    faqs = [FAQ(question=q, answer=" ".join(_FILL[(i + k) % 12] for k in range(4)) + (f" This applies to {p} too." if i == 0 else ""))
            for i, q in enumerate(["Who can start?", "Do I need much money?", "How often should I practise?", "What should I avoid?", "How do I improve?"])]
    ilinks = [InternalLink(anchor="beginner guide", url=SITE_ITEMS[0]["url"], reason="Start here"),
              InternalLink(anchor="equipment care page", url=SITE_ITEMS[1]["url"], reason="Keep gear in shape"),
              InternalLink(anchor="training plan", url=SITE_ITEMS[2]["url"], reason="A weekly routine")] if links else []
    images = [ImageIdea(description="A bat and ball on grass", alt="A wooden bat and a red ball resting on fresh green grass", placement="hero", query="cricket bat"),
              ImageIdea(description="A player practising a shot", alt="A young player practising a forward defensive shot in the nets", placement="section 2", query="cricket batting"),
              ImageIdea(description="Equipment laid out", alt="Cricket pads, gloves and a helmet laid out neatly on a bench", placement="section 4", query="cricket equipment")]
    meta = f"Learn {p} step by step. Clear advice, common mistakes and simple routines that help you start with confidence this season."
    title = f"{p.title()}: A Practical Guide"[:60]
    return BlogPost(seo_title=title, meta_description=meta, slug=plan.slug, h1=f"{p.title()}: a practical guide", intro=intro,
                    takeaways=["Start with the basics.", "Choose gear that fits you.", "Practise a little every day."], sections=sections, faqs=faqs,
                    internal_links=ilinks, images=images, sources=[SourceRef(title=FACTS[0]["title"], url=FACTS[0]["url"])],
                    cta=CTA(heading="Ready for your next step?", text="Pick one tip from this guide and try it this week.", button_text="Visit the site"),
                    secondary_keywords_used=sec[:3])


def weak_post(plan: Plan) -> BlogPost:
    """Fails many checks on purpose (short, one FAQ, no images)."""
    p = good_post(plan)
    p.sections = p.sections[:2]
    p.faqs = p.faqs[:1]
    p.images = []
    p.takeaways = []
    return p


def fake_llm(weak_first: bool = False, seen_keys: list | None = None):
    state = {"plan": None}

    async def structured(schema, system, user, temperature=0.5, timeout=None):
        if seen_keys is not None:
            seen_keys.append(current_key())
        if schema is Seeds:
            return Seeds(seeds=["cricket bat for beginners", "how to choose a cricket bat", "cricket bat weight", "best cricket bat size",
                                "cricket bat care", "cricket bat grip", "junior cricket bat", "knocking in a cricket bat"], audience_guess="beginners")
        if schema is Plan:
            lines = [l for l in user.splitlines() if l.startswith("- ") and "| status=" in l]
            kws = [l[2:].split(" | ")[0] for l in lines]
            state["plan"] = make_plan(kws[0], kws[1:6])
            return state["plan"]
        plan = state["plan"]
        has_links = "ALLOWED INTERNAL LINK URLS (data):\nnone" not in user
        if "FIXING" in system:
            return good_post(plan, has_links)
        return weak_post(plan) if weak_first else good_post(plan, has_links)
    return structured
