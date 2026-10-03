"""Citation links between library papers, using the OpenAlex API (free, no key).

Each paper is matched to an OpenAlex work by title once; its reference list is cached in the DB.
An edge A -> B means paper A's references include paper B.
"""
import asyncio
import difflib
import os
import re

import httpx

from . import db

API_URL = "https://api.openalex.org/works"
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


async def build_graph() -> dict:
    await resolve_missing()
    papers = db.papers_for_graph()
    by_openalex_id = {p["openalex_id"]: p["id"] for p in papers if p["openalex_id"]}
    edges = [
        {"from": p["id"], "to": by_openalex_id[ref]}
        for p in papers
        for ref in p["openalex_refs"]
        if ref in by_openalex_id and by_openalex_id[ref] != p["id"]
    ]
    nodes = [
        {"id": p["id"], "title": p["title"], "year": p["year"], "source": p["source"], "matched": p["openalex_status"] == "ok"}
        for p in papers
    ]
    return {"nodes": nodes, "edges": edges}
