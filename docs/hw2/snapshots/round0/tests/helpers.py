"""Builders and fakes shared by the test modules."""
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pymupdf
from google.genai import errors

from app import db

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
    author_xml = "".join(f"<author><name>{a}</name></author>" for a in authors)
    link = f'<link title="pdf" href="http://arxiv.org/pdf/{arxiv_id}" rel="related"/>' if pdf_link else ""
    return (
        f"<entry><id>http://arxiv.org/abs/{arxiv_id}</id><title>{title}</title>"
        f"<published>{published}</published><summary>{summary}</summary>{author_xml}{link}</entry>"
    )


def atom_feed(*entries: str) -> str:
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{"".join(entries)}</feed>'


class ExternalServices:
    """Stands in for the internet: every request the app sends through httpx lands here.

    A request that no test set up raises AssertionError, so a forgotten mock cannot go out silently.
    Later routes win over earlier ones.
    """

    def __init__(self):
        self.routes = []
        self.requests: list[httpx.Request] = []
        self.client_kwargs: list[dict] = []

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


HANG = object()  # a model that accepts the request and never answers


def api_error(code: int, message: str = "simulated") -> errors.APIError:
    return errors.APIError(code, {"error": {"message": message, "status": "X"}})


def reply(text=None, parsed=None):
    return SimpleNamespace(text=text, parsed=parsed)


class FakeGemini:
    """Replaces genai.Client at the SDK boundary, so all of app/llm.py still runs.

    Each call takes the next step from `steps` (the last repeats), or from `by_model` when the model is
    listed there. A step is a reply(), an exception to raise, or HANG.
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
        return step


def word_chars(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
