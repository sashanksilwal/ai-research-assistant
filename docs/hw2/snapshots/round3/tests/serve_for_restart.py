"""Runs the app as its own process, for the R2 restart test. Usage: serve_for_restart.py PORT

The process has no fixtures, so it fakes the internet itself: arXiv answers with the recording, PDFs are
generated, and a real .env can't be read. DATA_DIR comes from the environment.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from helpers import RETRIEVAL_PAPER, recorded_text  # noqa: E402


def internet(request: httpx.Request) -> httpx.Response:
    if request.url.host == "export.arxiv.org":
        return httpx.Response(200, text=recorded_text("arxiv_search.xml"))
    if request.url.host == "arxiv.org":
        return httpx.Response(200, content=RETRIEVAL_PAPER.pdf())
    return httpx.Response(599)


class FakeInternetClient(httpx.AsyncClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, transport=httpx.MockTransport(internet))


httpx.AsyncClient = FakeInternetClient

uvicorn.run("app.main:app", host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
