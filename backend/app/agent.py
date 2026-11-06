"""The one-click agent: a LangGraph state machine.

research -> dedupe -> plan(LLM) -> write(LLM) -> validate -> [repair(LLM) -> validate] -> save
"""
import asyncio
import logging
from typing import AsyncIterator, TypedDict

from langgraph.graph import END, StateGraph

from . import db, dedupe, page, prompts, research, seo
from .config import settings
from .errors import AppError, map_exception
from .llm import structured
from .models import BlogPost, Plan

log = logging.getLogger("seo.agent")


class State(TypedDict, total=False):
    candidates: list
    site: dict
    keyword_source: str
    shortlist: list
    stats: dict
    plan: Plan
    post: BlogPost
    checks: list
    score: int
    repaired: bool
    result: dict


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


async def research_node(state: State) -> dict:
    res = await research.run_research()
    return {"candidates": res["candidates"], "site": res["site"], "keyword_source": res["keyword_source"]}


async def dedupe_node(state: State) -> dict:
    existing = list(state["site"]["items"])
    try:
        existing += await asyncio.to_thread(db.generated_index)
    except AppError:
        pass
    checked = dedupe.check(state["candidates"], existing)
    counts = {k: sum(1 for c in checked if c["status"] == k) for k in ("gap", "partial", "conflict")}
    return {"candidates": checked, "shortlist": checked[:20],
            "stats": {"site_pages": len(existing), "counts": counts}}


async def plan_node(state: State) -> dict:
    plan = await structured(Plan, prompts.PLAN_SYSTEM, prompts.plan_user(state["shortlist"], state["stats"]))
    return {"plan": plan}


async def write_node(state: State) -> dict:
    plan = state["plan"]
    links = prompts.link_candidates(state["site"]["items"], plan.primary_keyword)
    post = await structured(BlogPost, prompts.WRITE_SYSTEM, prompts.write_user(plan.model_dump(), links))
    return {"post": post}


async def validate_node(state: State) -> dict:
    known = {i["url"] for i in state["site"]["items"]}
    post = seo.sanitize(state["post"], known)
    checks, score = seo.check(post, state["plan"].primary_keyword, state["plan"].secondary_keywords)
    return {"post": post, "checks": checks, "score": score}


async def repair_node(state: State) -> dict:
    plan = state["plan"]
    issues = [f"{c['label']} (currently: {c['detail'] or 'failed'})" for c in state["checks"] if not c["passed"]]
    links = prompts.link_candidates(state["site"]["items"], plan.primary_keyword)
    post = await structured(BlogPost, prompts.REPAIR_SYSTEM, prompts.repair_user(state["post"].model_dump(), plan.model_dump(), issues, links))
    return {"post": post, "repaired": True}


async def save_node(state: State) -> dict:
    post, plan = state["post"], state["plan"]
    words = sum(len(p.split()) for p in seo.body_paragraphs(post))
    post.slug = await asyncio.to_thread(db.unique_slug, post.slug)
    html = page.build_html(post, plan.primary_keyword, words)
    await asyncio.to_thread(db.save_page, slug=post.slug, title=post.seo_title, meta=post.meta_description, primary=plan.primary_keyword,
                            secondary=plan.secondary_keywords, post=post.model_dump(), html=html, score=state["score"],)
    return {"result": {"slug": post.slug, "url": f"/blog/{post.slug}", "title": post.seo_title, "score": state["score"], "words": words}}


def _route_after_validate(state: State) -> str:
    failing = [c for c in state["checks"] if not c["passed"]]
    return "repair" if failing and not state.get("repaired") else "save"


def build_graph():
    g = StateGraph(State)
    for name, fn in [("research", research_node), ("dedupe", dedupe_node), ("plan", plan_node), ("write", write_node),
                     ("validate", validate_node), ("repair", repair_node), ("save", save_node)]:
        g.add_node(name, fn)
    g.set_entry_point("research")
    g.add_edge("research", "dedupe"); g.add_edge("dedupe", "plan"); g.add_edge("plan", "write"); g.add_edge("write", "validate")
    g.add_conditional_edges("validate", _route_after_validate, {"repair": "repair", "save": "save"})
    g.add_edge("repair", "validate"); g.add_edge("save", END)
    return g.compile()


GRAPH = build_graph()
NEXT = {"research": "dedupe", "dedupe": "plan", "plan": "write", "write": "validate", "repair": "validate", "save": None}


def summarize(node: str, upd: dict, state: dict) -> dict:
    if node == "research":
        return {"keyword_source": upd["keyword_source"], "site_source": upd["site"]["source"], "site_pages": len(upd["site"]["items"]),
                "candidates": [{"keyword": c["keyword"], "source": c["source"], "verified": c["verified"]} for c in upd["candidates"]]}
    if node == "dedupe":
        return {**upd["stats"], "candidates": [{k: c[k] for k in ("keyword", "status", "overlap", "conflicts", "closest")} for c in upd["candidates"][:30]]}
    if node == "plan":
        p: Plan = upd["plan"]
        cand = {c["keyword"]: c for c in state["candidates"]}
        pc = cand.get(_norm(p.primary_keyword))
        return {**p.model_dump(), "primary_verified": bool(pc), "primary_status": pc["status"] if pc else "unknown",
                "secondary_verified": [bool(cand.get(_norm(k))) for k in p.secondary_keywords]}
    if node == "write":
        post: BlogPost = upd["post"]
        return {"title": post.seo_title, "meta": post.meta_description, "sections": len(post.sections), "faqs": len(post.faqs),
                "words": sum(len(x.split()) for x in seo.body_paragraphs(post))}
    if node == "validate":
        return {"checks": upd["checks"], "score": upd["score"]}
    if node == "repair":
        return {"note": "One targeted repair pass was applied for the failed checks."}
    return upd["result"]


async def run_agent() -> AsyncIterator[dict]:
    """Yield SSE-style events: step(running/done), done, error."""
    state: dict = {}
    current = "research"
    yield {"event": "step", "data": {"id": "research", "status": "running"}}
    try:
        async for chunk in GRAPH.astream({}, stream_mode="updates"):
            for node, upd in chunk.items():
                state.update(upd)
                yield {"event": "step", "data": {"id": node, "status": "done", "data": summarize(node, upd, state)}}
                nxt = _route_after_validate(state) if node == "validate" else NEXT[node]
                current = nxt or current
                if nxt:
                    yield {"event": "step", "data": {"id": nxt, "status": "running"}}
        r = state["result"]
        yield {"event": "done", "data": {**r, "mode": "live"}}
    except Exception as exc:  # noqa: BLE001
        err = map_exception(exc)
        log.error("run failed at %s: %s", current, err.code)
        yield {"event": "error", "data": {"code": err.code, "message": err.message, "step": current}}
