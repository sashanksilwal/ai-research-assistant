"""Builders and fakes shared by the test modules."""
import asyncio
import json
import re
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpx
import pymupdf
from google.genai import errors, types

from app import db

FIXTURES = Path(__file__).parent / "fixtures"
RECORDED = FIXTURES / "recorded"
VENDOR = FIXTURES / "vendor"

LONG_TEXT = "Graph neural networks improve retrieval quality on citation data. " * 20  # > MIN_TEXT_CHARS


def make_pdf(text: str | None = LONG_TEXT, metadata: dict | None = None) -> bytes:
    """A real PDF. text=None gives a blank page, like a scan with no text layer."""
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=10)
    if metadata:
        doc.set_metadata(metadata)
    data = doc.tobytes()
    doc.close()
    return data


def recorded_text(name: str) -> str:
    return (RECORDED / name).read_text()


def recorded_json(name: str):
    return json.loads(recorded_text(name))


class PaperSpec:
    """A research paper laid out over several pages, with a footer page number on each."""

    def __init__(self, title, authors, year, abstract, sections, references, appendix=(), embed_metadata=True):
        self.title, self.authors, self.year, self.abstract = title, authors, year, abstract
        self.sections, self.references, self.appendix = sections, references, appendix
        self.embed_metadata = embed_metadata

    def lines(self) -> list[str]:
        out = [self.title, ", ".join(self.authors), "", "Abstract"]
        out += self.abstract.split("\n") if "\n" in self.abstract else textwrap.wrap(self.abstract, 88)
        out.append("")
        for heading, text in self.sections:
            out += [heading] + textwrap.wrap(text, 88) + [""]
        out.append("References")
        for entry in self.references:
            out += entry.split("\n") if "\n" in entry else textwrap.wrap(entry, 88)
        out.append("")
        for heading, text in self.appendix:
            out += [heading] + textwrap.wrap(text, 88) + [""]
        return out

    def pdf(self) -> bytes:
        doc = pymupdf.open()
        lines_per_page, line_height = 52, 13
        all_lines = self.lines()
        for start in range(0, len(all_lines), lines_per_page):
            page = doc.new_page()
            for offset, line in enumerate(all_lines[start : start + lines_per_page]):
                page.insert_text((54, 60 + offset * line_height), line, fontsize=10)
            page.insert_text((300, 800), str(doc.page_count), fontsize=9)
        if self.embed_metadata:
            doc.set_metadata(
                {"title": self.title, "author": "; ".join(self.authors), "creationDate": f"D:{self.year}0304120000"}
            )
        data = doc.tobytes()
        doc.close()
        return data


def _prose(topic: str, marker: str, sentences: int = 26) -> str:
    return " ".join(
        f"In experiment {i} the {topic} pipeline behaved as predicted by the analysis in this section." for i in range(sentences)
    ) + f" {marker}"


def _refs(prefix: str, count: int = 22) -> list[str]:
    return [
        f"[{i}] {prefix} Author and Other Writer. A study of method number {i} for practical systems. "
        f"Proceedings of the Conference, pages {i}-{i + 9}, {1995 + i}."
        for i in range(1, count + 1)
    ]


# Distinct papers. Each marker sits in one place, so a prompt can be checked for that part of the paper.
RETRIEVAL_PAPER = PaperSpec(
    title="Sparse Retrieval for Citation Graphs",
    authors=["Ada Lovelace", "Alan Turing"],
    year=2021,
    abstract="We study sparse retrieval over citation graphs and show that a small learned index "
    "answers most queries while using a fraction of the memory of the dense baseline systems.",
    sections=[
        ("1 Introduction", _prose("retrieval", "Introduction marker kestrel.")),
        ("2 Method", _prose("indexing", "Method marker heron.")),
        ("3 Experiments", _prose("evaluation", "Experiments marker osprey.")),
        ("4 Conclusion", _prose("deployment", "Conclusion marker plover.")),
    ],
    references=_refs("Retrieval"),
    # The bare "A" heading of failure 3. Years run through it, as in the original paper, so only the
    # heading can tell the stripper where the reference list ended.
    appendix=[("A", " ".join(f"Replication {i} of the 2020 proof matched the bound." for i in range(40)) + " Appendix marker wren.")],
)
PROTEIN_PAPER = PaperSpec(
    title="Contrastive Learning of Protein Folds",
    authors=["Rosalind Franklin", "Linus Pauling", "Dorothy Hodgkin"],
    year=2019,
    abstract="Protein fold classification benefits from contrastive training, and we report a clear "
    "gain over supervised baselines on three public structure datasets of different sizes.",
    sections=[
        ("1. Introduction", _prose("folding", "Introduction marker lupine.")),
        ("2. Results", _prose("classification", "Results marker yarrow.")),
    ],
    references=_refs("Protein"),
    appendix=[("Appendix A: Dataset Details", _prose("dataset", "Appendix marker sorrel."))],
)
SPEECH_PAPER = PaperSpec(
    title="Quantized Speech Models on Edge Devices",
    authors=["Grace Hopper"],
    year=2023,
    abstract="Quantization lets speech recognition models run on small devices, and this paper measures "
    "the accuracy lost at each bit width on hardware that ships in consumer products today.",
    sections=[
        ("1 Introduction", _prose("speech", "Introduction marker juniper.")),
        ("2 Evaluation", _prose("quantization", "Evaluation marker tamarack.")),
    ],
    references=_refs("Speech"),
)


def run(coro):
    """Run a coroutine on a fresh thread.

    Playwright's sync API keeps a loop marked as running on the main thread for the rest of the
    session, so a plain asyncio.run() would fail in any test ordered after a browser test.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def seed_paper(**fields) -> int:
    """Insert a paper with usable full text; override any column."""
    values = {
        "source": "upload",
        "title": "Seeded paper",
        "authors": ["Ada Lovelace"],
        "year": 2024,
        "abstract": "An abstract.",
        "full_text": LONG_TEXT,
        "text_status": "ready",
    }
    values.update(fields)
    return db.insert_paper(**values)


def search_result(external_id="2401.00001", **overrides) -> dict:
    """A body for POST /api/papers, shaped like an item from GET /api/search."""
    return {
        "external_id": external_id,
        "title": "Attention Is All You Need",
        "authors": ["A. Author", "B. Author"],
        "year": 2024,
        "abstract": "We propose a model.",
        "url": f"https://arxiv.org/abs/{external_id}v1",
        "pdf_url": f"https://arxiv.org/pdf/{external_id}v1",
        **overrides,
    }


def atom_entry(
    arxiv_id="2401.00001v2",
    title="A Paper",
    authors=("Ada Lovelace", "Alan Turing"),
    published="2024-01-15T00:00:00Z",
    summary="An abstract.",
    pdf_link=True,
) -> str:
    """Same element order and attributes as a recorded arXiv entry (test_contract.py checks this)."""
    author_xml = "".join(f"<author><name>{a}</name></author>" for a in authors)
    pdf = f'<link href="https://arxiv.org/pdf/{arxiv_id}" rel="related" type="application/pdf" title="pdf"/>'
    return (
        f"<entry><id>http://arxiv.org/abs/{arxiv_id}</id><title>{title}</title><updated>{published}</updated>"
        f'<link href="https://arxiv.org/abs/{arxiv_id}" rel="alternate" type="text/html"/>{pdf if pdf_link else ""}'
        f'<summary>{summary}</summary><category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>'
        f'<published>{published}</published><arxiv:comment>12 pages</arxiv:comment>'
        f'<arxiv:primary_category term="cs.LG"/>{author_xml}</entry>'
    )


def atom_feed(*entries: str) -> str:
    return (
        '<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" '
        'xmlns="http://www.w3.org/2005/Atom"><id>https://arxiv.org/api/feed</id><title>arXiv Query</title>'
        f"<opensearch:totalResults>{len(entries)}</opensearch:totalResults>{''.join(entries)}</feed>"
    )


class ExternalServices:
    """Stands in for the internet: every request the app sends through httpx lands here.

    A request that no test set up raises AssertionError, so a forgotten mock cannot go out silently.
    Later routes win over earlier ones.
    """

    def __init__(self):
        self.routes = []
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for host, path, handler in reversed(self.routes):
            if request.url.host == host and (path is None or path in request.url.path):
                return handler(request)
        raise AssertionError(f"Unexpected external request: {request.method} {request.url}")

    def handle(self, host, handler, path=None):
        self.routes.append((host, path, handler))

    def respond(self, host, status=200, path=None, **response_kwargs):
        self.handle(host, lambda request: httpx.Response(status, **response_kwargs), path)

    def fail(self, host, exc_type=httpx.ConnectError):
        def handler(request):
            raise exc_type("simulated network failure", request=request)

        self.handle(host, handler)

    def sequence(self, host, steps):
        """Answer with each (status, kwargs) step in turn; the last one repeats."""
        remaining = list(steps)

        def handler(request):
            status, kwargs = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            return httpx.Response(status, **kwargs)

        self.handle(host, handler)

    def hits(self, host) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == host]


def assert_bounded_timeout(request: httpx.Request, seconds: float = 60):
    """httpx applies the client's timeout per request; None in any phase means that phase can hang forever."""
    timeout = request.extensions["timeout"]
    assert set(timeout) == {"connect", "read", "write", "pool"}
    assert all(value is not None and 0 < value <= seconds for value in timeout.values())


HANG = object()  # a model that accepts the request and never answers


def api_error(code: int, message: str = "simulated") -> errors.APIError:
    return errors.APIError(code, {"error": {"message": message, "status": "X"}})


def reply(text=None, data=None):
    """A wire-format Gemini reply. `data` is sent as JSON text, as structured output is."""
    if data is not None:
        text = json.dumps(data)
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}


def blocked_reply(reason="SAFETY"):
    """Gemini refusing to answer: a candidate with a finish reason and no content."""
    return {"candidates": [{"finishReason": reason}]}


def prompt_blocked_reply():
    return {"promptFeedback": {"blockReason": "SAFETY"}}


class FakeGemini:
    """Replaces genai.Client at the network boundary, so app/llm.py and the SDK's parsing both run.

    Each call takes the next step from `steps` (the last repeats), or from `by_model` when the model is
    listed there. A step is a wire-format reply, an exception to raise, or HANG. Replies go through the
    SDK's own GenerateContentResponse parser, so `.text` and `.parsed` behave as they do in production.
    """

    def __init__(self):
        self.calls = []
        self.steps = [reply("Fake Gemini answer")]
        self.by_model = {}
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate_content))

    def script(self, *steps):
        self.steps = list(steps)

    @property
    def models_tried(self):
        return [c.model for c in self.calls]

    @property
    def last_prompt(self):
        return self.calls[-1].contents

    async def _generate_content(self, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        if model in self.by_model:
            step = self.by_model[model]
        else:
            step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if step is HANG:
            await asyncio.Event().wait()
        if isinstance(step, Exception):
            raise step
        return types.GenerateContentResponse._from_response(
            response=step, kwargs={"config": {"response_schema": config.response_schema}}
        )


def word_chars(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
