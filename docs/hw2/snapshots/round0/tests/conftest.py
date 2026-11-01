"""Test isolation. The top of this file must run before anything imports `app`.

app.config reads the environment, loads .env and creates DATA_DIR at import time, and app.main serves
"static" relative to the working directory, so all of that is set up here first.
"""
import asyncio
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
SESSION_DATA_DIR = Path(tempfile.mkdtemp(prefix="research-assistant-tests-"))

for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENALEX_EMAIL"):
    os.environ.pop(name, None)
os.environ["DATA_DIR"] = str(SESSION_DATA_DIR)
os.environ["GEMINI_MODEL"] = "model-primary"
os.environ["GEMINI_FALLBACK_MODELS"] = "model-backup-1,model-backup-2"

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *args, **kwargs: False  # never read a real .env
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_socket  # noqa: E402
import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from playwright.sync_api import Error as PlaywrightError  # noqa: E402

from app import citations, db, llm, main  # noqa: E402
from helpers import ExternalServices, FakeGemini  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: drives the real frontend in a headless browser")


def pytest_unconfigure(config):
    shutil.rmtree(SESSION_DATA_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def localhost_only():
    """Second line of defence after `external`: real sockets may only reach this machine."""
    pytest_socket.socket_allow_hosts(["127.0.0.1", "::1"], allow_unix_socket=True)


@pytest.fixture(autouse=True)
def external(monkeypatch):
    """Route all httpx.AsyncClient traffic (arXiv, OpenAlex, Semantic Scholar, PDFs) to a fake."""
    services = ExternalServices()

    class FakeInternetClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            services.client_kwargs.append(dict(kwargs))
            super().__init__(**kwargs, transport=httpx.MockTransport(services))

    monkeypatch.setattr(httpx, "AsyncClient", FakeInternetClient)
    return services


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    """Give each test its own empty database and PDF folder."""
    data_dir = tmp_path / "data"
    pdf_dir = data_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    monkeypatch.setattr(db, "DB_PATH", data_dir / "app.db")
    monkeypatch.setattr(main, "PDF_DIR", pdf_dir)
    db.init_db()
    return SimpleNamespace(data_dir=data_dir, pdf_dir=pdf_dir, db_path=data_dir / "app.db")


@pytest.fixture(autouse=True)
def gemini_offline(monkeypatch):
    """By default there is no API key and the real SDK client cannot be built."""

    def refuse(*args, **kwargs):
        raise AssertionError("The real Gemini client must not be created in tests")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm.genai, "Client", refuse)


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """Record backoff delays instead of waiting them out. Scoped to app modules, not asyncio itself."""
    recorded = []

    async def fake_sleep(seconds):
        recorded.append(seconds)
        await asyncio.sleep(0)

    fake_asyncio = SimpleNamespace(sleep=fake_sleep, wait_for=asyncio.wait_for, TimeoutError=asyncio.TimeoutError)
    monkeypatch.setattr(llm, "asyncio", fake_asyncio)
    monkeypatch.setattr(citations, "asyncio", fake_asyncio)
    return recorded


@pytest.fixture
def gemini(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr(llm, "_client", fake)
    return fake


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def raw_client():
    """Like `client`, but an unhandled exception becomes the 500 a real user would get."""
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


# ---------- browser tests ----------


@pytest.fixture(scope="session")
def live_server():
    """The real app on a real localhost port, in-process so the fixtures above also apply to it."""
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Test server did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """E2E_CHROMIUM_PATH selects a Chromium already on disk when Playwright's own build is not installed."""
    path = os.environ.get("E2E_CHROMIUM_PATH")
    return {**browser_type_launch_args, "executable_path": path} if path else browser_type_launch_args


@pytest.fixture(scope="session")
def browser(launch_browser):
    """Replaces pytest-playwright's fixture to skip clearly when no browser is installed."""
    try:
        instance = launch_browser()
    except PlaywrightError as e:
        pytest.skip(f"Chromium is not available (run: playwright install chromium): {e}")
    yield instance
    instance.close()


@pytest.fixture
def open_app(page, live_server):
    """Open the app with all non-local traffic blocked, failing on any uncaught JavaScript error.

    `cdn` maps a substring of a CDN URL to JavaScript served in its place; other CDN files are aborted.
    """
    js_errors = []
    page.on("pageerror", lambda e: js_errors.append(str(e)))
    page.set_default_timeout(10_000)

    def go(cdn=None):
        def route(r):
            url = r.request.url
            if url.startswith(live_server):
                return r.continue_()
            for fragment, script in (cdn or {}).items():
                if fragment in url:
                    return r.fulfill(status=200, content_type="text/javascript", body=script)
            return r.abort()

        page.route("**/*", route)
        page.goto(live_server)
        return page

    yield go
    assert js_errors == []
