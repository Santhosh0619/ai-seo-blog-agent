"""Cannibalisation check: how much of a keyword is already covered by an existing page title?

Lexical on purpose: for keyword overlap it is deterministic, free (no API quota) and explainable.
overlap = (candidate words found together in the best-matching existing title) / (candidate words)
>= 0.8 conflict, 0.5-0.8 partial, < 0.5 gap.
"""
import re

_STOP = {"in", "for", "the", "a", "an", "and", "of", "to", "with", "is", "how", "what", "near", "me", "at", "on", "best", "top", "vs", "or", "your", "my", "do", "does", "are"}
_SYN = {"training": "course", "courses": "course", "classes": "course", "class": "course", "institute": "course",
        "institutes": "course", "fees": "fee", "beginners": "beginner", "marketer": "marketing"}


def tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in _STOP:
            continue
        w = _SYN.get(w, w)
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out


def check(candidates: list[dict], existing: list[dict], topic: str = "") -> list[dict]:
    index = [(e, tokens(e["title"] + " " + e["url"].rstrip("/").rsplit("/", 1)[-1].replace("-", " "))) for e in existing]
    topic_t = tokens(topic)
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
        c["on_topic"] = round(len(ct & topic_t) / len(topic_t), 2) if topic_t else 1.0
    order = {"gap": 0, "partial": 1, "conflict": 2}
    # gaps first; within a status prefer keywords close to the user's topic, then the lowest overlap
    return sorted(candidates, key=lambda c: (order[c["status"]], -c["on_topic"], c["overlap"]))
