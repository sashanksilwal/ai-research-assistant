"""The ten failures that really happened during development, each tested from its description."""
import re

import httpx
import pymupdf
import pytest
from playwright.sync_api import expect

from app import citations, db, llm
from helpers import (
    HANG,
    RETRIEVAL_PAPER,
    PaperSpec,
    api_error,
    recorded_json,
    recorded_text,
    reply,
    run,
    seed_paper,
)

ARXIV_API = "export.arxiv.org"
OPENALEX = "api.openalex.org"
S2 = "api.semanticscholar.org"
EMPTY_OPENALEX = {"meta": {"count": 0}, "results": [], "group_by": []}

e2e = pytest.mark.e2e


def upload(client, data, filename="upload.pdf"):
    return client.post("/api/upload", files={"file": (filename, data, "application/pdf")})


def contrast(foreground, background):
    def luminance(rgb):
        channels = [c / 255 for c in rgb]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_failure_1_stopwords_do_not_empty_the_search(client, external):
    """arXiv's index has no stopwords, so a clause on one matches nothing."""

    def arxiv_index(request):
        clauses = re.findall(r"all:(\w+)", request.url.params["search_query"])
        unindexed = {"is", "all", "you", "the", "a", "of"}
        name = "arxiv_error.xml" if unindexed & {c.lower() for c in clauses} else "arxiv_search.xml"
        return httpx.Response(200, text=recorded_text(name))

    external.handle(ARXIV_API, arxiv_index)
    assert len(client.get("/api/search", params={"q": "attention is all you need"}).json()) == 3


def test_failure_2_nul_characters_do_not_cut_the_stored_text(client, gemini, monkeypatch):
    """A NUL mid-document must not hide the text after it from length() or the prompt."""
    real_get_text = pymupdf.Page.get_text
    monkeypatch.setattr(pymupdf.Page, "get_text", lambda page, *a, **k: "before\x00" + real_get_text(page, *a, **k))
    paper = upload(client, RETRIEVAL_PAPER.pdf()).json()
    assert paper["text_chars"] > 3000
    assert len(db.get_full_text(paper["id"])) == paper["text_chars"]
    client.post(f"/api/papers/{paper['id']}/summary")
    assert "plover" in gemini.last_prompt  # on the last page of the body
    assert "\x00" not in gemini.last_prompt


def test_failure_3_stripper_keeps_an_appendix_with_a_bare_letter_heading(client, gemini):
    paper = upload(client, RETRIEVAL_PAPER.pdf()).json()
    client.post(f"/api/papers/{paper['id']}/summary")
    sent = gemini.last_prompt
    assert "wren" in sent
    full_text = db.get_full_text(paper["id"])
    references = full_text[full_text.index("\nReferences\n") : full_text.index("\nA\n")]
    assert len(full_text) - len(sent) <= len(references)  # only the list itself goes, not 41% of the paper


def test_failure_4_models_that_never_answer_end_in_an_error(client, gemini, monkeypatch):
    monkeypatch.setattr(llm, "MODEL_TIMEOUT_S", 0.01)
    gemini.script(HANG)
    response = client.post(f"/api/papers/{seed_paper()}/summary")
    assert response.status_code == 503
    assert "did not respond in time" in response.json()["detail"]


@e2e
def test_failure_4_spinner_stops_when_models_never_answer(open_app, gemini, monkeypatch):
    monkeypatch.setattr(llm, "MODEL_TIMEOUT_S", 0.05)
    gemini.script(HANG)
    seed_paper(title="Hanging")
    page = open_app()
    page.locator('.tab[data-tab="library"]').click()
    page.locator("#library-list .card").get_by_role("button", name="Open").click()
    button = page.get_by_role("button", name="Summarize with Gemini")
    button.click()
    expect(page.locator("#detail-content")).to_contain_text("Summary failed: Gemini did not respond in time")
    expect(button).to_be_enabled()


def test_failure_5_503_and_429_fall_back_to_a_working_model(client, gemini):
    gemini.by_model = {"model-primary": api_error(503), "model-backup-1": api_error(429)}
    gemini.script(reply("Answer from the third model"))
    body = client.post(f"/api/papers/{seed_paper()}/summary").json()
    assert body["summary"] == "Answer from the third model"
    assert gemini.models_tried == ["model-primary", "model-backup-1", "model-backup-2"]


@e2e
def test_failure_6_latex_renders_once_and_never_raw(open_app):
    seed_paper(title="Arrows", summary=r"Input $\rightarrow$ output, with $\alpha$ scaled")
    page = open_app()
    page.locator('.tab[data-tab="library"]').click()
    page.locator("#library-list .card").get_by_role("button", name="Open").click()
    markdown = page.locator(".markdown")
    expect(markdown).to_contain_text("→")
    text = markdown.text_content()
    assert "\\rightarrow" not in text and "$" not in text
    assert text.count("→") == 1  # hidden MathML would make this two
    assert text.count("α") == 1
    assert markdown.locator(".katex").count() == 2


@e2e
def test_failure_7_inactive_tab_labels_are_visible(open_app):
    page = open_app()
    for active in ("search", "library", "detail"):
        page.locator(f'.tab[data-tab="{active}"]').click()
        tabs = page.locator(".tab:not(.active)")
        expect(tabs).to_have_count(2)
        for index in range(tabs.count()):
            tab = tabs.nth(index)
            assert tab.inner_text().strip()
            colors = tab.evaluate(
                """element => {
                  const channels = value => value.match(/[\\d.]+/g).map(Number);
                  let node = element, background = null;
                  while (node) {
                    const color = channels(getComputedStyle(node).backgroundColor);
                    if (color.length === 3 || color[3] > 0) { background = color.slice(0, 3); break; }
                    node = node.parentElement;
                  }
                  return { text: channels(getComputedStyle(element).color).slice(0, 3), background: background ?? [255, 255, 255] };
                }"""
            )
            assert contrast(colors["text"], colors["background"]) >= 4.5, colors


def test_failure_8_line_break_hyphenation_is_removed_from_the_abstract(client):
    spec = PaperSpec(
        title="Hyphenated",
        authors=["Ada Lovelace"],
        year=2020,
        abstract="We learn a compact representa-\ntion of each document and evaluate the resulting\n"
        "retrieval quality on large collections with many queries.",
        sections=[("1 Introduction", "Introductory text about documents. " * 60)],
        references=["[1] A. Author. A paper. Venue, 2019."],
    )
    abstract = upload(client, spec.pdf()).json()["abstract"]
    assert "representation of each document" in abstract
    assert "representa-" not in abstract


@pytest.mark.xfail(strict=True, reason="BUG: only a hyphen directly before the newline is rejoined, so 'representa- \\ntion' (trailing space in the PDF line) stays broken")
def test_failure_8_hyphenation_with_a_trailing_space_is_removed(client):
    spec = PaperSpec(
        title="Hyphenated with a space",
        authors=["Ada Lovelace"],
        year=2020,
        abstract="We learn a compact representa- \ntion of each document and evaluate the resulting\n"
        "retrieval quality on large collections with many queries.",
        sections=[("1 Introduction", "Introductory text about documents. " * 60)],
        references=["[1] A. Author. A paper. Venue, 2019."],
    )
    assert "representation of each document" in upload(client, spec.pdf()).json()["abstract"]


def test_failure_9_rate_limited_s2_falls_back_to_openalex_then_recovers(client, external):
    transformer = seed_paper(source="arxiv", external_id="1706.03762", title="Attention Is All You Need")
    s2_only = seed_paper(source="arxiv", external_id="1705.04304", title="Cited per Semantic Scholar")
    openalex_only = seed_paper(source="arxiv", external_id="1111.11111", title="Cited per OpenAlex")
    db.set_openalex(transformer, "ok", "W1", ["W3"])
    db.set_openalex(s2_only, "ok", "W2", [])
    db.set_openalex(openalex_only, "ok", "W3", [])

    external.respond(S2, status=429)
    first = client.get("/api/graph").json()
    assert first["edges"] == [{"from": transformer, "to": openalex_only}]

    external.respond(S2, json=recorded_json("s2_batch.json") + [None])
    second = client.get("/api/graph").json()
    assert {(e["from"], e["to"]) for e in second["edges"]} == {(transformer, openalex_only), (transformer, s2_only)}


def test_failure_10_junk_openalex_record_is_not_matched(client, external):
    seed_paper(title="Graph Attention Networks")
    junk = {
        "id": "https://openalex.org/W1",
        "title": "[1] Nandi, S., Sarkar, R., and others. Attention based graph models. Journal of Things.",
        "referenced_works": ["https://openalex.org/W2"],
    }
    external.respond(OPENALEX, json={**EMPTY_OPENALEX, "results": [junk]})
    graph = client.get("/api/graph").json()
    row = db.papers_for_graph()[0]
    assert row["openalex_status"] == "not_found"
    assert row["openalex_id"] is None and row["openalex_refs"] == []
    assert graph["nodes"][0]["matched"] is False


def test_failure_10_real_record_is_found_behind_the_junk(external):
    seed_paper(title="Attention Is All You Need")
    junk = {"id": "https://openalex.org/W1", "title": "[1] Nandi, S. et al.", "referenced_works": []}
    results = recorded_json("openalex_search.json")["results"]
    external.respond(OPENALEX, json={**EMPTY_OPENALEX, "results": [junk, *results]})
    run(citations.build_graph())
    assert db.papers_for_graph()[0]["openalex_id"] == "W2626778328"
