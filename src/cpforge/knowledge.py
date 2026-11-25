"""Routing and the knowledge base: which surface to use, which docs matter, what to avoid."""
from __future__ import annotations

import re

from .util import KNOWLEDGE_DIR, ForgeError, load_json


def docs() -> list[dict]:
    out = []
    for p in sorted(KNOWLEDGE_DIR.glob("*.md")):
        first = next((ln.lstrip("# ").strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()), p.stem)
        out.append({"name": p.name, "title": first})
    return out


def doc(name: str) -> str:
    p = KNOWLEDGE_DIR / (name if name.endswith(".md") else name + ".md")
    if not p.is_file():
        raise ForgeError(f"no knowledge doc '{name}'", "list them with: cpforge knowledge")
    return p.read_text(encoding="utf-8")


def facts(key: str | None = None):
    data = load_json(KNOWLEDGE_DIR / "facts.json")["facts"]
    if key is None:
        return {k: {"tier": v["tier"]} for k, v in data.items()}
    hits = {k: v for k, v in data.items() if key.lower() in k.lower()}
    if not hits:
        raise ForgeError(f"no fact matching '{key}'", "list keys with: cpforge facts")
    return hits


def plan(request: str) -> dict:
    data = load_json(KNOWLEDGE_DIR / "routes.json")
    text = " " + re.sub(r"[^a-z0-9+#.' ]+", " ", request.lower()) + " "
    scored = []
    for r in data["routes"]:
        score = 0
        hits = []
        for kw in r["keywords"]:
            if f" {kw} " in text or (len(kw) > 4 and kw in text):
                score += 2 if " " in kw else 1
                hits.append(kw)
        # "words" match whole words only (plural s/es allowed): "skirt" must not hit "outskirts".
        # They name the asset outright, so they weigh like a multi-word keyword.
        for w in r.get("words", []):
            if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?:s|es)?(?![a-z0-9])", text):
                score += 2
                hits.append(w)
        if score:
            scored.append((score, r, hits))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        primary, alts = None, []
    else:
        primary = dict(scored[0][1], matched=scored[0][2])
        alts = [{"id": r["id"], "title": r["title"], "matched": h} for _, r, h in scored[1:4]]
    frameworks = sorted({f for _, r, _ in scored[:2] for f in r["frameworks"]})
    templates = []
    for _, r, _ in scored[:2]:
        for t in r["templates"]:
            if t not in templates:
                templates.append(t)
    return {
        "request": request,
        "route": primary,
        "also_relevant": alts,
        "frameworks_needed": frameworks,
        "scaffold": (f"cpforge new \"<Name>\" " + " ".join(f"--kind {t}" for t in templates)) if templates else None,
        "principle": data["principle"],
        "always": data["always"],
        "unmatched": primary is None,
        "hint": None if primary else "no route matched; read cpforge knowledge and pick a surface by the principle above",
    }
