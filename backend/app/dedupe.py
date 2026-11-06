"""Cannibalisation check: how much of a keyword is already covered by an existing page title?

Lexical on purpose: for keyword overlap it is deterministic, free (no API quota) and explainable.
overlap = (candidate words found together in the best-matching existing title) / (candidate words)
"""
import re

_STOP = {"in", "for", "the", "a", "an", "and", "of", "to", "with", "is", "how", "what", "near", "me", "at", "on", "best", "top"}
_SYN = {"training": "course", "courses": "course", "classes": "course", "class": "course", "institute": "course",
        "institutes": "course", "fees": "fee", "beginners": "beginner", "marketing": "marketing", "marketer": "marketing"}


def tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in _STOP:
            continue
        w = _SYN.get(w, w)
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out


def check(candidates: list[dict], existing: list[dict]) -> list[dict]:
    index = [(e, tokens(e["title"] + " " + e["url"].rstrip("/").rsplit("/", 1)[-1].replace("-", " "))) for e in existing]
    for c in candidates:
        ct = tokens(c["keyword"])
        best, best_e, hits = 0.0, [], 0
        for e, et in index:
            score = len(ct & et) / len(ct) if ct else 0.0
            # an existing page whose whole title is contained in the keyword already owns this topic
            if len(et) >= 3 and et <= ct:
                score = max(score, 0.85)
            if score >= 0.8:
                hits += 1
            if score > best:
                best, best_e = score, [e]
            elif score == best and len(best_e) < 2 and score > 0:
                best_e.append(e)
        c["overlap"] = round(best, 2)
        c["conflicts"] = hits
        c["status"] = "conflict" if best >= 0.8 else "partial" if best >= 0.5 else "gap"
        c["closest"] = [{"title": e["title"], "url": e["url"]} for e in best_e[:2]]
    order = {"gap": 0, "partial": 1, "conflict": 2}
    # gaps first; within a status prefer local-intent keywords and clearly course-related ones
    def rank(c: dict) -> tuple:
        kw = c["keyword"]
        return (order[c["status"]], 0 if "coimbatore" in kw else 1, 0 if re.search(r"course|training|institute|syllabus|fee", kw) else 1, c["overlap"])
    return sorted(candidates, key=rank)
