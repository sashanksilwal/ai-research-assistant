"""Summaries and Q&A grounded in a paper's full text."""
import re

from . import llm

# ~75k tokens. Most papers are 20k–80k chars; the cap guards against book-length PDFs
# and the free tier's tokens-per-minute limit. Truncation is reported to the user, never silent.
MAX_TEXT_CHARS = 300_000

# The page renders Markdown but not LaTeX, so "$\\rightarrow$" would show up literally.
PLAIN_MATH = "Do not use LaTeX or $...$ math; write formulas in plain text with Unicode symbols (→, ≤, ×, subscripts as y_0)."

SUMMARY_SYSTEM = (
    "You are a research assistant helping a graduate student understand a paper. "
    "Base everything on the paper text provided, not on outside knowledge of the paper. "
    "Be specific: name the method, datasets, metrics, baselines and numbers the paper reports. "
    + PLAIN_MATH
)

SUMMARY_INSTRUCTIONS = """Summarize this paper in Markdown with these sections:

## Problem
What problem it addresses and why it matters (2–3 sentences).

## Approach
The main idea of the proposed method and what is new about it.

## Experiments
Datasets, baselines and evaluation metrics used.

## Key results
The main quantitative and qualitative findings, with numbers where the paper gives them.

## Limitations
Limitations the authors state, plus any obvious ones (label those as your observation).

Keep it under about 400 words."""

QA_SYSTEM = (
    "You answer questions about one research paper using only the paper text provided. "
    "If the paper does not contain the answer, say so plainly (e.g. \"The paper doesn't say.\") "
    "instead of guessing or using outside knowledge. Mention the section or table the answer "
    "comes from when you can. Answer concisely in Markdown. "
    + PLAIN_MATH
)


_REFERENCES_HEADING = re.compile(
    r"^[ \t]*(?:\d+\.?[ \t]*)?(?:references|bibliography|literature cited)[ \t]*$", re.IGNORECASE | re.MULTILINE
)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
_LINE = re.compile(r"^.*$", re.MULTILINE)
# Reference lists have a year every ~150 chars; a longer stretch without one means the list has ended.
_YEAR_GAP = 1500


def _is_appendix_heading(line: str) -> bool:
    """"Appendix ...", "Supplementary ...", a lone "A" / "B.2", or a short Title-Case heading like
    "A Experimental Details". Reference entries ("A new tool for measuring readability.") don't match."""
    line = line.strip()
    if re.match(r"(?i)(?:appendix|appendices|supplementary)\b", line):
        return True
    m = re.fullmatch(r"[A-H](?:\.\d+)*\.?(?:\s+(.{3,60}))?", line)
    if not m:
        return False
    title = m.group(1)
    if title is None:
        return True
    return "," not in title and not title.endswith(".") and all(w[0].isupper() or len(w) <= 3 for w in title.split())


def strip_references(text: str) -> str:
    """Drop the reference list (noise for summaries and Q&A), keeping any appendix after it.

    Only a "References" heading in the last 60% of the text counts, so a table of contents or an
    early mention never cuts the paper body. The list ends at the first appendix heading or where
    years stop appearing, whichever comes first.
    """
    heading = next((m for m in _REFERENCES_HEADING.finditer(text) if m.start() >= len(text) * 0.4), None)
    if not heading:
        return text
    refs_end = heading.end()
    for year in _YEAR.finditer(text, heading.end()):
        if year.start() - refs_end > _YEAR_GAP:
            break
        refs_end = year.end()
    # The last entry runs on a little past its year (title, venue); an appendix heading close by marks the end.
    appendix = next(
        (line for line in _LINE.finditer(text, heading.end(), min(len(text), refs_end + 600)) if _is_appendix_heading(line.group())),
        None,
    )
    if appendix:
        cut_to = appendix.start()
    else:
        blank = text.find("\n\n", refs_end, refs_end + 400)
        cut_to = blank if blank != -1 else refs_end
    return text[:heading.start()] + "[References omitted]\n" + text[cut_to:]


def _paper_block(text: str) -> tuple[str, bool]:
    text = strip_references(text)
    truncated = len(text) > MAX_TEXT_CHARS
    return f"<paper>\n{text[:MAX_TEXT_CHARS]}\n</paper>", truncated


async def summarize(text: str) -> tuple[str, bool]:
    """Return (markdown summary, truncated)."""
    paper, truncated = _paper_block(text)
    summary = await llm.generate(f"{paper}\n\n{SUMMARY_INSTRUCTIONS}", system=SUMMARY_SYSTEM)
    return summary, truncated


async def answer(text: str, question: str) -> tuple[str, bool]:
    """Return (markdown answer, truncated). The paper comes first and the question last."""
    paper, truncated = _paper_block(text)
    reply = await llm.generate(f"{paper}\n\nQuestion: {question}", system=QA_SYSTEM)
    return reply, truncated
