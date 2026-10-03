"""arXiv API client: keyword search returning normalized paper dicts."""
import re
import xml.etree.ElementTree as ET

import httpx

API_URL = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}


class ArxivError(Exception):
    pass


def _build_query(text: str) -> str:
    # AND the words together across all fields; drop characters that are arXiv query syntax.
    words = re.sub(r"[^\w\s-]", " ", text).split()
    return " AND ".join(f"all:{w}" for w in words)


def _clean(s: str | None) -> str:
    return " ".join((s or "").split())


def _parse_entry(entry: ET.Element) -> dict:
    abs_url = entry.find("a:id", ATOM).text.replace("http://", "https://")
    versioned_id = abs_url.rsplit("/abs/", 1)[-1]
    pdf_url = next(
        (l.get("href") for l in entry.findall("a:link", ATOM) if l.get("title") == "pdf"),
        f"https://arxiv.org/pdf/{versioned_id}",
    )
    return {
        "external_id": re.sub(r"v\d+$", "", versioned_id),  # stable across versions
        "title": _clean(entry.find("a:title", ATOM).text),
        "authors": [_clean(a.find("a:name", ATOM).text) for a in entry.findall("a:author", ATOM)],
        "year": int(entry.find("a:published", ATOM).text[:4]),
        "abstract": _clean(entry.find("a:summary", ATOM).text),
        "url": abs_url,
        "pdf_url": pdf_url.replace("http://", "https://"),
    }


async def search(text: str, max_results: int = 10) -> list[dict]:
    query = _build_query(text)
    if not query:
        return []
    params = {"search_query": query, "max_results": max_results, "sortBy": "relevance"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ArxivError(f"arXiv returned HTTP {e.response.status_code}; try again in a few seconds.") from e
    except httpx.HTTPError as e:
        raise ArxivError(f"Could not reach arXiv: {e.__class__.__name__}.") from e

    entries = ET.fromstring(resp.text).findall("a:entry", ATOM)
    # arXiv reports query errors as a single entry whose id points at /api/errors.
    return [_parse_entry(e) for e in entries if "/api/errors" not in e.find("a:id", ATOM).text]
