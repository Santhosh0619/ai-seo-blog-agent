"""The one-click agent: a LangGraph state machine.

seeds(AI) -> research -> dedupe -> plan(AI) -> write(AI) -> images -> validate -> [repair(AI) -> validate] -> save
"""
import asyncio
import logging
import re
from typing import AsyncIterator, TypedDict

from langgraph.graph import END, StateGraph

from . import db, dedupe, images as images_mod, prompts, research, seo
from .errors import AppError, map_exception
from .llm import structured
from .models import BlogPost, BlogRequest, Plan, Seeds

log = logging.getLogger("seo.agent")


class State(TypedDict, total=False):
    req: BlogRequest
    user_id: int
    site_origin: str
    seeds: list
    candidates: list
    site: dict
    facts: list
    keyword_source: str
    existing: list
    prior_texts: list
    prior_titles: list
    shortlist: list
    stats: dict
    plan: Plan
    post: BlogPost
    images: list
    checks: list
    score: int
    groups: dict
    score_before: int
    repaired: bool
    result: dict


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _post_text(post: dict) -> str:
    try:
        return seo.body_text(BlogPost.model_validate(post))
    except Exception:  # noqa: BLE001
        return ""


def _failing(state: State) -> list[dict]:
    return [c for c in state["checks"] if c["applicable"] and not c["passed"]]


async def seeds_node(state: State) -> dict:
    req = state["req"]
    out = await structured(Seeds, prompts.SEEDS_SYSTEM, prompts.seeds_user(req), temperature=0.6, timeout=30)
    seeds = []
    for s in out.seeds:
        s = re.sub(r"\s+", " ", s.lower()).strip(" .?!\"'")
        if 3 <= len(s) <= 80 and s not in seeds:
            seeds.append(s)
    if req.topic.lower() not in seeds:
        seeds.insert(0, req.topic.lower())
    return {"seeds": seeds[:8]}


async def research_node(state: State) -> dict:
    res = await research.run_research(state["req"], state["seeds"], state.get("site_origin", ""))
    return {"candidates": res["candidates"], "site": res["site"], "facts": res["facts"], "keyword_source": res["keyword_source"]}


async def dedupe_node(state: State) -> dict:
    req = state["req"]
    existing = list(state["site"]["items"])
    prior = await asyncio.to_thread(db.previous_pages, state["user_id"])
    mine = [{"url": f"/app/pages/{p['id']}", "title": f"{p['title']} {p['keyword']}"} for p in prior]
    checked = dedupe.check(state["candidates"], existing + mine, req.topic)
    counts = {k: sum(1 for c in checked if c["status"] == k) for k in ("gap", "partial", "conflict")}
    return {"candidates": checked, "shortlist": checked[:20], "existing": existing,
            "prior_texts": [_post_text(p["post"]) for p in prior[:15]], "prior_titles": [p["title"] for p in prior],
            "stats": {"pages": len(existing) + len(mine), "site_pages": len(existing), "own_pages": len(mine), "counts": counts}}


async def plan_node(state: State) -> dict:
    plan = await structured(Plan, prompts.PLAN_SYSTEM, prompts.plan_user(state["req"], state["shortlist"], state["stats"], state["prior_titles"], state["facts"]), timeout=60)
    return {"plan": plan}


def _links(state: State) -> list[dict]:
    return prompts.link_candidates(state["existing"], state["plan"].primary_keyword) if state["existing"] else []


async def write_node(state: State) -> dict:
    req, plan = state["req"], state["plan"]
    links = _links(state)
    post = await structured(BlogPost, prompts.write_system(req, bool(links), bool(state["facts"])),
                            prompts.write_user(req, plan.model_dump(), state["facts"], links), temperature=0.7, timeout=100)
    return {"post": post}


async def images_node(state: State) -> dict:
    return {"images": await images_mod.make_images(state["post"].images, state["req"].topic)}


def _ctx(state: State) -> seo.Ctx:
    req, plan = state["req"], state["plan"]
    facts_text = req.notes + " " + " ".join(f["extract"] for f in state["facts"])
    return seo.Ctx(primary=plan.primary_keyword, secondary=plan.secondary_keywords, facts_text=facts_text, prior_texts=state.get("prior_texts", []),
                   link_pool=len(state["existing"]), sources_provided=bool(state["facts"]), word_min=max(800, int(req.word_target * 0.7)),
                   word_max=int(req.word_target * 1.8))


async def validate_node(state: State) -> dict:
    known = {i["url"] for i in state["existing"]}
    sources = {f["url"] for f in state["facts"]}
    post = seo.sanitize(state["post"], known, sources)
    checks, score, groups = seo.check(post, _ctx(state))
    out = {"post": post, "checks": checks, "score": score, "groups": groups}
    if not state.get("repaired"):
        out["score_before"] = score
    return out


async def repair_node(state: State) -> dict:
    req, plan = state["req"], state["plan"]
    issues = [f"{c['label']} (currently: {c['detail'] or 'failed'}). Fix: {c['fix']}" for c in _failing(state)]
    links = _links(state)
    post = await structured(BlogPost, prompts.repair_system(req, bool(links), bool(state["facts"])),
                            prompts.repair_user(req, state["post"].model_dump(), plan.model_dump(), issues, state["facts"], links), temperature=0.4, timeout=100)
    return {"post": post, "repaired": True}


async def save_node(state: State) -> dict:
    post, plan, req, uid = state["post"], state["plan"], state["req"], state["user_id"]
    words = sum(len(p.split()) for p in seo.body_paragraphs(post))
    slug = await asyncio.to_thread(db.unique_slug, uid, post.slug)
    post.slug = slug
    repaired = bool(state.get("repaired"))
    research_blob = {"seeds": state["seeds"], "keyword_source": state["keyword_source"], "stats": state["stats"],
                     "site_note": state["site"]["note"], "facts": [{"title": f["title"], "url": f["url"]} for f in state["facts"]],
                     "candidates": [{k: c[k] for k in ("keyword", "status", "overlap", "verified", "source", "closest")} for c in state["candidates"][:40]],
                     "groups": state["groups"]}
    req_blob = req.model_dump()
    page_id = await asyncio.to_thread(
        db.save_page, uid, slug=slug, topic=req.topic, title=post.seo_title, meta=post.meta_description, primary=plan.primary_keyword,
        secondary=plan.secondary_keywords, post=post.model_dump(), plan=plan.model_dump(), research=research_blob, checks=state["checks"],
        score=state["score"], score_before=state.get("score_before") if repaired else None, request=req_blob)
    imgs = []
    for im in state.get("images", []):
        alt = post.images[im["idx"]].alt if im["idx"] < len(post.images) else im["alt"]
        imgs.append({**im, "alt": alt})
    await asyncio.to_thread(db.save_images, page_id, uid, imgs)
    return {"result": {"id": page_id, "slug": slug, "title": post.seo_title, "score": state["score"], "words": words, "repaired": repaired,
                       "score_before": state.get("score_before") if repaired else None}}


def _route_after_validate(state: State) -> str:
    return "repair" if _failing(state) and not state.get("repaired") else "save"


def build_graph():
    g = StateGraph(State)
    for name, fn in [("seeds", seeds_node), ("research", research_node), ("dedupe", dedupe_node), ("plan", plan_node), ("write", write_node),
                     ("images", images_node), ("validate", validate_node), ("repair", repair_node), ("save", save_node)]:
        g.add_node(name, fn)
    g.set_entry_point("seeds")
    g.add_edge("seeds", "research"); g.add_edge("research", "dedupe"); g.add_edge("dedupe", "plan"); g.add_edge("plan", "write")
    g.add_edge("write", "images"); g.add_edge("images", "validate")
    g.add_conditional_edges("validate", _route_after_validate, {"repair": "repair", "save": "save"})
    g.add_edge("repair", "validate"); g.add_edge("save", END)
    return g.compile()


GRAPH = build_graph()
NEXT = {"seeds": "research", "research": "dedupe", "dedupe": "plan", "plan": "write", "write": "images", "images": "validate", "repair": "validate", "save": None}


def summarize(node: str, upd: dict, state: dict) -> dict:
    if node == "seeds":
        return {"seeds": upd["seeds"]}
    if node == "research":
        return {"keyword_source": upd["keyword_source"], "site_note": upd["site"]["note"], "site_pages": len(upd["site"]["items"]),
                "facts": [{"title": f["title"], "url": f["url"]} for f in upd["facts"]],
                "candidates": [{"keyword": c["keyword"], "source": c["source"], "verified": c["verified"]} for c in upd["candidates"]]}
    if node == "dedupe":
        return {**upd["stats"], "candidates": [{k: c[k] for k in ("keyword", "status", "overlap", "conflicts", "closest")} for c in upd["candidates"][:30]]}
    if node == "plan":
        p: Plan = upd["plan"]
        cand = {c["keyword"]: c for c in state["candidates"]}
        pc = cand.get(_norm(p.primary_keyword))
        return {**p.model_dump(), "primary_verified": bool(pc and pc["verified"]), "primary_status": pc["status"] if pc else "unknown",
                "secondary_verified": [bool((cand.get(_norm(k)) or {}).get("verified")) for k in p.secondary_keywords]}
    if node == "write":
        post: BlogPost = upd["post"]
        return {"title": post.seo_title, "meta": post.meta_description, "sections": len(post.sections), "faqs": len(post.faqs),
                "words": sum(len(x.split()) for x in seo.body_paragraphs(post))}
    if node == "images":
        return {"images": [{"source": i["source"], "credit": i["credit"]} for i in upd["images"]]}
    if node == "validate":
        return {"checks": upd["checks"], "score": upd["score"], "groups": upd["groups"], "repaired": bool(state.get("repaired")), "score_before": state.get("score_before")}
    if node == "repair":
        return {"note": "One targeted repair pass was applied for the failed checks."}
    return upd["result"]


async def run_agent(req: BlogRequest, user_id: int, site_origin: str = "") -> AsyncIterator[dict]:
    """Yield SSE-style events: step(running/done), done, error."""
    state: dict = {}
    current = "seeds"
    yield {"event": "step", "data": {"id": "seeds", "status": "running"}}
    try:
        async for chunk in GRAPH.astream({"req": req, "user_id": user_id, "site_origin": site_origin}, stream_mode="updates"):
            for node, upd in chunk.items():
                state.update(upd)
                yield {"event": "step", "data": {"id": node, "status": "done", "data": summarize(node, upd, state)}}
                nxt = _route_after_validate(state) if node == "validate" else NEXT[node]
                current = nxt or current
                if nxt:
                    yield {"event": "step", "data": {"id": nxt, "status": "running"}}
        yield {"event": "done", "data": state["result"]}
    except Exception as exc:  # noqa: BLE001
        err = map_exception(exc)
        log.error("run failed at %s: %s", current, err.code)
        yield {"event": "error", "data": {"code": err.code, "message": err.message, "step": current, "needs_key": err.needs_key}}
