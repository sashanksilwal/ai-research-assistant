"""Citation links between library papers, from Semantic Scholar and OpenAlex (both free, no key).

Semantic Scholar is the main source: arXiv papers are looked up by arXiv id in one batch request, and
its reference lists are good for ML papers. OpenAlex (matched by title) adds links for uploaded PDFs and
anything Semantic Scholar misses; for many recent arXiv papers its records have no reference list.
Reference lists are cached in the DB. An edge A -> B means paper A's references include paper B.
"""
import asyncio
import difflib
import os
import re

import httpx

from . import db

API_URL = "https://api.openalex.org/works"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"  # up to 500 ids per request
# Optional: OpenAlex gives faster service to requests that include a contact email.
CONTACT_EMAIL = os.getenv("OPENALEX_EMAIL")
MIN_TITLE_SIMILARITY = 0.9


def _normalize(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


async def _lookup(client: httpx.AsyncClient, title: str) -> tuple[str, dict | None]:
    """Return (status, work) where work has OpenAlex `id` and `referenced_works`."""
    params = {"search": title, "select": "id,title,referenced_works", "per-page": 5}
    if CONTACT_EMAIL:
        params["mailto"] = CONTACT_EMAIL
    try:
        resp = await client.get(API_URL, params=params)
        resp.raise_for_status()
    except httpx.HTTPError:
        return "error", None
    wanted = _normalize(title)
    for work in resp.json().get("results", []):
        similarity = difflib.SequenceMatcher(None, wanted, _normalize(work.get("title") or "")).ratio()
        if similarity >= MIN_TITLE_SIMILARITY:
            return "ok", work
    return "not_found", None


async def resolve_missing() -> None:
    """Look up papers not yet matched to OpenAlex (or whose last lookup errored)."""
    pending = db.papers_needing_openalex()
    if not pending:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        for paper in pending:
            status, work = await _lookup(client, paper["title"])
            refs = [r.rsplit("/", 1)[-1] for r in (work or {}).get("referenced_works", [])]
            db.set_openalex(paper["id"], status, work["id"].rsplit("/", 1)[-1] if work else None, refs)
            await asyncio.sleep(0.2)  # stay well under OpenAlex's 10 requests/second


async def resolve_missing_s2() -> None:
    """Fetch Semantic Scholar reference lists for arXiv papers not yet looked up, in one batch request."""
    pending = db.papers_needing_s2()
    if not pending:
        return
    params = {"fields": "references.externalIds,references.title"}
    body = {"ids": [f"arXiv:{p['external_id']}" for p in pending]}
    resp = None
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(4):  # keyless requests are often rejected with 429 at first; back off and retry
            try:
                resp = await client.post(S2_BATCH_URL, params=params, json=body)
            except httpx.HTTPError:
                resp = None
            if resp is not None and resp.status_code == 200:
                break
            await asyncio.sleep(5 * (attempt + 1))
    if resp is None or resp.status_code != 200:
        for paper in pending:
            db.set_s2(paper["id"], "error", [])  # retried on the next graph load
        return
    for paper, work in zip(pending, resp.json()):
        refs = [
            {"arxiv": (ref.get("externalIds") or {}).get("ArXiv"), "title": ref.get("title")}
            for ref in (work or {}).get("references") or []
        ]
        db.set_s2(paper["id"], "ok" if work else "not_found", refs)


async def build_graph() -> dict:
    await resolve_missing()
    await resolve_missing_s2()
    papers = db.papers_for_graph()
    edges = set()
    by_openalex_id = {p["openalex_id"]: p["id"] for p in papers if p["openalex_id"]}
    for p in papers:
        for ref in p["openalex_refs"]:
            if ref in by_openalex_id:
                edges.add((p["id"], by_openalex_id[ref]))
    # Semantic Scholar references: match by arXiv id, else by exact (normalized) title, which links uploads.
    by_arxiv = {p["external_id"]: p["id"] for p in papers if p["external_id"]}
    by_title = {_normalize(p["title"]): p["id"] for p in papers}
    for p in papers:
        for ref in p["s2_refs"]:
            target = by_arxiv.get(ref["arxiv"]) or by_title.get(_normalize(ref["title"] or ""))
            if target:
                edges.add((p["id"], target))
    nodes = [
        {"id": p["id"], "title": p["title"], "year": p["year"], "source": p["source"],
         "matched": p["openalex_status"] == "ok" or p["s2_status"] == "ok"}
        for p in papers
    ]
    return {"nodes": nodes, "edges": [{"from": a, "to": b} for a, b in sorted(edges) if a != b]}
