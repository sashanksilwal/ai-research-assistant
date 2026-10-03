"""Extract title / authors / year / abstract from an uploaded paper."""
import re
from pathlib import Path

import pymupdf
from pydantic import BaseModel

from . import llm

# Title, authors and abstract are on the first page or two.
HEAD_CHARS = 8000

SYSTEM = (
    "You extract bibliographic metadata from the beginning of a research paper. "
    "Use only what is in the text. Copy the title and abstract verbatim (fix hyphenation "
    "and line breaks only). Authors are people's names only, without affiliations, emails "
    "or footnote markers. Year is the publication or submission year if stated "
    "(e.g. in a header, footer, copyright line, conference name or arXiv stamp), else null. "
    "If there is no abstract section, use null."
)


class PaperMetadata(BaseModel):
    title: str
    authors: list[str]
    year: int | None
    abstract: str | None


async def extract(text: str, pdf_data: bytes, filename: str) -> tuple[dict, str | None]:
    """Return (metadata, warning). Falls back to heuristics if Gemini fails."""
    head = text[:HEAD_CHARS]
    try:
        meta = await llm.generate(f"<paper_start>\n{head}\n</paper_start>", system=SYSTEM, schema=PaperMetadata)
        return meta.model_dump(), None
    except llm.LLMError as e:
        return fallback(head, pdf_data, filename), f"Metadata extracted without Gemini ({e})"


def fallback(head: str, pdf_data: bytes, filename: str) -> dict:
    with pymupdf.open(stream=pdf_data, filetype="pdf") as doc:
        info = doc.metadata or {}
    title = (info.get("title") or "").strip() or Path(filename).stem.replace("_", " ")
    authors = [a.strip() for a in re.split(r"[;,]| and ", info.get("author") or "") if a.strip()]
    year = re.search(r"(19|20)\d{2}", info.get("creationDate") or "")
    head = re.sub(r"(\w)-\n(\w)", r"\1\2", head)  # rejoin words hyphenated across lines
    abstract = re.search(r"(?is)\babstract\b[\s.:—-]*(.{100,2000}?)(?:\n\s*\n|\b1\.?\s+introduction\b)", head)
    return {
        "title": title,
        "authors": authors,
        "year": int(year.group()) if year else None,
        "abstract": " ".join(abstract.group(1).split()) if abstract else None,
    }
