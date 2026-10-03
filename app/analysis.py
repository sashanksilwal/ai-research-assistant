"""Summaries and Q&A grounded in a paper's full text."""
from . import llm

# ~75k tokens. Most papers are 20k–80k chars; the cap guards against book-length PDFs
# and the free tier's tokens-per-minute limit. Truncation is reported to the user, never silent.
MAX_TEXT_CHARS = 300_000

SUMMARY_SYSTEM = (
    "You are a research assistant helping a graduate student understand a paper. "
    "Base everything on the paper text provided, not on outside knowledge of the paper. "
    "Be specific: name the method, datasets, metrics, baselines and numbers the paper reports."
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
    "comes from when you can. Answer concisely in Markdown."
)


def _paper_block(text: str) -> tuple[str, bool]:
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
