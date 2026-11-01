"""Acceptance tests for the HW1 requirements, one group per row of tests/REQUIREMENTS.md."""
import os
import re
import socket
import subprocess
import sys
import time

import httpx
import pymupdf
import pytest
from playwright.sync_api import expect

from app import metadata
from conftest import ROOT, route_everything
from helpers import (
    PROTEIN_PAPER,
    RETRIEVAL_PAPER,
    SPEECH_PAPER,
    PaperSpec,
    atom_entry,
    atom_feed,
    recorded_text,
    reply,
    seed_paper,
)

ARXIV_API = "export.arxiv.org"
ARXIV_PDF = "arxiv.org"
PAPERS = [RETRIEVAL_PAPER, PROTEIN_PAPER, SPEECH_PAPER]
BODY_MARKERS = {
    RETRIEVAL_PAPER: ["kestrel", "heron", "osprey", "plover"],
    PROTEIN_PAPER: ["lupine", "yarrow"],
    SPEECH_PAPER: ["juniper", "tamarack"],
}

e2e = pytest.mark.e2e


def upload(client, spec, filename="upload.pdf"):
    return client.post("/api/upload", files={"file": (filename, spec.pdf(), "application/pdf")})


def search(page, text):
    page.locator("#search-input").fill(text)
    page.locator("#search-form button").click()


def show_tab(page, name):
    page.locator(f'.tab[data-tab="{name}"]').click()


# ---------- R1: search ----------


@e2e
def test_r1_topic_query_renders_all_five_fields(open_app, external):
    external.respond(ARXIV_API, text=recorded_text("arxiv_search.xml"))
    page = open_app()
    search(page, "attention transformer")
    cards = page.locator("#search-results .card")
    expect(cards).to_have_count(3)
    first = cards.first
    expect(first.locator("h3")).to_have_text("Dilated Neighborhood Attention Transformer")
    expect(first.locator(".meta")).to_have_text("Ali Hassani, Humphrey Shi · 2022")
    expect(first.locator(".abstract")).to_contain_text("Transformers are quickly becoming")
    expect(first.get_by_role("link", name="View paper")).to_have_attribute("href", "https://arxiv.org/abs/2209.15001v3")


@e2e
def test_r1_link_opens_the_paper_in_a_new_tab(open_app, external):
    external.respond(ARXIV_API, text=recorded_text("arxiv_search.xml"))
    page = open_app()
    search(page, "attention")
    with page.context.expect_page() as popup:
        page.locator("#search-results .card").first.get_by_role("link", name="View paper").click()
    assert popup.value.url == "https://arxiv.org/abs/2209.15001v3"


@e2e
def test_r1_bad_query_shows_a_message(open_app, external):
    external.respond(ARXIV_API, text=recorded_text("arxiv_error.xml"))
    page = open_app()
    search(page, "badprefix:x:y")
    expect(page.locator("#search-status")).to_have_text("No results for “badprefix:x:y”. Try different keywords.")
    expect(page.locator("#search-results .card")).to_have_count(0)


# ---------- R2: saving survives a real restart ----------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerProcess:
    def __init__(self, data_dir, port):
        self.data_dir, self.port = data_dir, port
        self.url = f"http://127.0.0.1:{port}"
        self.process = None

    def start(self):
        env = {**os.environ, "DATA_DIR": str(self.data_dir)}
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "tests" / "serve_for_restart.py"), str(self.port)],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.url}/api/health", timeout=1).status_code == 200:
                    return
            except httpx.TransportError:
                time.sleep(0.05)
        raise RuntimeError("Server process did not start")

    def stop(self):
        """Kill without warning, so only what was already committed to disk can survive."""
        self.process.kill()
        self.process.wait(timeout=10)


@pytest.fixture
def server(tmp_path):
    instance = ServerProcess(tmp_path / "restart-data", free_port())
    instance.start()
    yield instance
    instance.stop()


@e2e
def test_r2_two_saved_papers_survive_a_server_restart_and_refresh(page, server):
    page.set_default_timeout(10_000)
    route_everything(page, server.url)
    page.goto(server.url)
    search(page, "attention")
    save_buttons = page.locator("#search-results").get_by_role("button", name="Save to library")
    expect(save_buttons).to_have_count(3)
    first_pid = server.process.pid
    for _ in range(2):
        save_buttons.first.click()
        expect(page.locator("#search-results button.small", has_text="Saving")).to_have_count(0)
    expect(page.locator("#search-results button.small", has_text="Saved")).to_have_count(2)

    server.stop()
    with pytest.raises(httpx.TransportError):
        httpx.get(f"{server.url}/api/health", timeout=1)
    server.start()
    assert server.process.pid != first_pid

    page.reload()
    show_tab(page, "library")
    expect(page.locator("#library-status")).to_have_text("2 saved papers")
    cards = page.locator("#library-list .card")
    expect(cards).to_have_count(2)
    expect(cards.first).to_contain_text("Full text ready")

    show_tab(page, "search")
    search(page, "attention")
    expect(page.locator("#search-results button.small", has_text="Saved ✓")).to_have_count(2)  # survives as saved


def test_r2_saving_again_after_a_restart_does_not_duplicate(server):
    first = httpx.get(f"{server.url}/api/search", params={"q": "attention"}, timeout=5).json()[0]
    saved = httpx.post(f"{server.url}/api/papers", json=first, timeout=10).json()
    server.stop()
    server.start()
    again = httpx.post(f"{server.url}/api/papers", json=first, timeout=10).json()
    assert again["id"] == saved["id"]
    assert len(httpx.get(f"{server.url}/api/papers", timeout=5).json()) == 1
    assert httpx.get(f"{server.url}{saved['pdf_url']}", timeout=5).content.startswith(b"%PDF")


# ---------- R3: uploads, from realistic multi-page PDFs ----------


def test_generated_papers_really_are_multi_page():
    for spec in PAPERS:
        with pymupdf.open(stream=spec.pdf(), filetype="pdf") as doc:
            assert doc.page_count >= 2
            assert "References" in "".join(page.get_text() for page in doc)


@pytest.mark.parametrize("spec", PAPERS, ids=lambda s: s.title.split()[0])
def test_r3_distinct_pdfs_yield_their_own_fields_without_gemini(client, spec):
    paper = upload(client, spec).json()
    assert paper["title"] == spec.title
    assert paper["authors"] == spec.authors
    assert paper["year"] == spec.year
    assert paper["abstract"] == spec.abstract
    assert paper["text_status"] == "ready"


def test_r3_gemini_reads_the_first_pages_of_the_upload(client, gemini):
    spec = RETRIEVAL_PAPER
    gemini.script(reply(data={"title": spec.title, "authors": spec.authors, "year": spec.year, "abstract": spec.abstract}))
    paper = upload(client, spec).json()
    assert paper["title"] == spec.title
    assert paper["metadata_warning"] is None
    prompt = " ".join(gemini.last_prompt.split())
    assert spec.title in prompt and "Ada Lovelace" in prompt and "learned index" in prompt
    assert len(gemini.last_prompt) <= metadata.HEAD_CHARS + 100
    assert gemini.calls[0].config.response_schema is metadata.PaperMetadata
    rules = gemini.calls[0].config.system_instruction.lower()
    assert all(field in rules for field in ("title", "authors", "year", "abstract"))


@pytest.mark.xfail(strict=True, reason="BUG: a wrapped reference line like 'G. E. Hinton and R. Salakhutdinov' looks like an appendix heading, so the rest of the reference list stays in the prompt")
def test_r4_wrapped_author_line_does_not_end_the_reference_list(client, gemini):
    references = [*RETRIEVAL_PAPER.references[:3], "[4] Deep belief nets, by\nG. E. Hinton and R. Salakhutdinov\nScience, 2006.", *RETRIEVAL_PAPER.references[4:]]
    spec = PaperSpec(RETRIEVAL_PAPER.title, RETRIEVAL_PAPER.authors, 2021, RETRIEVAL_PAPER.abstract, RETRIEVAL_PAPER.sections, references, RETRIEVAL_PAPER.appendix)
    paper = upload(client, spec).json()
    client.post(f"/api/papers/{paper['id']}/summary")
    assert "A study of method number 22 " not in gemini.last_prompt


@e2e
def test_r3_uploads_render_in_the_same_card_as_search_results(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    page = open_app()
    search(page, "x")
    search_card = page.locator("#search-results .card").first
    expect(search_card).to_be_visible()
    shape = "e => [...e.children].map(c => c.tagName + '.' + c.className.replace(' clamped', ''))"
    expected = search_card.evaluate(shape)

    show_tab(page, "library")
    for spec in PAPERS:
        page.set_input_files(
            "#upload-input", files=[{"name": "paper.pdf", "mimeType": "application/pdf", "buffer": spec.pdf()}]
        )
        page.locator("#upload-form button").click()
        card = page.locator("#library-list .card", has_text=spec.title)
        expect(card).to_have_count(1)
        expect(card.locator("h3")).to_have_text(spec.title)
        expect(card.locator(".meta")).to_have_text(f"{', '.join(spec.authors)} · {spec.year}")
        expect(card.locator(".abstract")).to_have_text(spec.abstract)
        assert card.evaluate(shape) == expected


# ---------- R4: summaries come from the paper's content ----------


@pytest.mark.parametrize("spec", PAPERS, ids=lambda s: s.title.split()[0])
def test_r4_prompt_contains_every_section_of_the_full_text(client, gemini, spec):
    paper = upload(client, spec).json()
    assert client.post(f"/api/papers/{paper['id']}/summary").status_code == 200
    prompt = gemini.last_prompt
    for marker in BODY_MARKERS[spec]:
        assert marker in prompt
    assert spec.title in prompt


@pytest.mark.parametrize(
    "spec, appendix_marker", [(RETRIEVAL_PAPER, "wren"), (PROTEIN_PAPER, "sorrel")], ids=["bare-A", "Appendix-A"]
)
def test_r4_reference_list_is_dropped_but_the_appendix_is_kept(client, gemini, spec, appendix_marker):
    paper = upload(client, spec).json()
    client.post(f"/api/papers/{paper['id']}/summary")
    prompt = gemini.last_prompt
    assert appendix_marker in prompt
    assert "A study of method number 1 " not in prompt
    assert "A study of method number 22 " not in prompt
    assert "[References omitted]" in prompt


def test_r4_abstract_field_is_not_what_gets_summarized(client, gemini):
    paper_id = seed_paper(abstract="ABSTRACT-FIELD-ONLY", full_text="Body text of the paper. " * 40)
    client.post(f"/api/papers/{paper_id}/summary")
    assert "Body text of the paper." in gemini.last_prompt
    assert "ABSTRACT-FIELD-ONLY" not in gemini.last_prompt


@pytest.mark.parametrize("route", ["summary", "ask"])
def test_r4_paper_with_only_an_abstract_is_refused(client, gemini, route):
    paper_id = seed_paper(abstract="A perfectly good abstract.", full_text=None, text_status="failed")
    kwargs = {"json": {"question": "Why?"}} if route == "ask" else {}
    response = client.post(f"/api/papers/{paper_id}/{route}", **kwargs)
    assert response.status_code == 409
    assert gemini.calls == []
    assert client.get(f"/api/papers/{paper_id}").json()["summary"] is None


# ---------- R5: questions ----------


def test_r5_question_is_asked_of_the_selected_paper_only(client, gemini):
    selected = upload(client, RETRIEVAL_PAPER).json()
    upload(client, PROTEIN_PAPER)
    client.post(f"/api/papers/{selected['id']}/ask", json={"question": "Which bird is in section 3?"})
    prompt = gemini.last_prompt
    assert "osprey" in prompt
    assert "lupine" not in prompt
    assert prompt.endswith("Question: Which bird is in section 3?")


def test_r5_instructions_restrict_answers_to_the_paper(client, gemini):
    client.post(f"/api/papers/{seed_paper()}/ask", json={"question": "Who won the 1998 World Cup?"})
    instruction = gemini.calls[0].config.system_instruction
    assert "using only the paper text" in instruction
    assert "doesn't say" in instruction


@e2e
def test_r5_model_refusal_reaches_the_user_unchanged(open_app, gemini):
    gemini.script(reply("The paper doesn't say."))
    seed_paper(title="Off topic")
    page = open_app()
    show_tab(page, "library")
    page.locator("#library-list .card").get_by_role("button", name="Open").click()
    box = page.locator(".qa-form textarea")
    box.fill("Who won the 1998 World Cup?")
    box.press("Enter")
    expect(page.locator(".qa-item .markdown")).to_have_text("The paper doesn't say.")


# ---------- the traceability table itself ----------


def test_every_test_named_in_the_traceability_table_exists():
    table = (ROOT / "tests" / "REQUIREMENTS.md").read_text()
    named = set(re.findall(r"`(test_\w+)`", table))
    source = "".join(path.read_text() for path in (ROOT / "tests").glob("test_*.py"))
    assert named
    assert {name for name in named if f"def {name}(" not in source} == set()
