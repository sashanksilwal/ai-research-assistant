"""The real frontend in headless Chromium against the real backend.

CDN scripts never load: `open_app` aborts them, or serves a stub for tests that need one. Without the
stubs the app runs in its documented offline mode (plain-text summaries, graph error message).
"""
import re

import pytest
from playwright.sync_api import expect

from app import db
from helpers import api_error, atom_entry, atom_feed, make_pdf, reply, seed_paper

pytestmark = pytest.mark.e2e

ARXIV_API = "export.arxiv.org"
ARXIV_PDF = "arxiv.org"

MARKED_STUB = "window.marked = { parse: t => '<p>' + t + '</p>' };"
DOMPURIFY_STUB = "window.DOMPurify = { sanitize: h => h.replace(/<script[\\s\\S]*?<\\/script>/g, '') };"
KATEX_STUB = "window.katex = { renderToString: s => '<span class=\"katex\">' + s + '</span>' };"
VIS_STUB = """
window.visCreated = [];
window.vis = {
  DataSet: class {
    constructor(items) { this.items = new Map(items.map(i => [i.id, i])); }
    get(o) { const all = [...this.items.values()]; return o?.filter ? all.filter(o.filter) : all; }
    update(list) { list.forEach(i => this.items.set(i.id, { ...this.items.get(i.id), ...i })); }
  },
  Network: class {
    constructor(el, data) { this.data = data; window.visCreated.push(data); }
    once() {} on() {} destroy() {} fit() {}
    getConnectedNodes() { return []; } getConnectedEdges() { return []; }
  },
};
"""


def search(page, text):
    page.locator("#search-input").fill(text)
    page.locator("#search-form button").click()


def show_tab(page, name):
    page.locator(f'.tab[data-tab="{name}"]').click()


def card(page, title):
    return page.locator("#library-list .card").filter(has_text=title)


def open_paper(page, title):
    show_tab(page, "library")
    card(page, title).get_by_role("button", name="Open").click()


def upload_file(page, name, data, mime="application/pdf"):
    page.set_input_files("#upload-input", files=[{"name": name, "mimeType": mime, "buffer": data}])
    page.locator("#upload-form button").click()


# ---------- page shell ----------


def test_page_loads_on_the_search_tab(open_app):
    page = open_app()
    expect(page).to_have_title("AI Research Assistant")
    expect(page.locator("#search")).to_have_class(re.compile(r"\bactive\b"))
    expect(page.locator("#search-topics .topic-link")).to_have_count(8)


def test_tabs_switch_panels(open_app):
    page = open_app()
    show_tab(page, "library")
    expect(page.locator("#library")).to_be_visible()
    expect(page.locator("#search")).to_be_hidden()
    show_tab(page, "detail")
    expect(page.locator("#detail")).to_contain_text("Open a paper from the Library")


def test_page_works_with_all_external_scripts_blocked(open_app, page):
    blocked = []
    page.on("requestfailed", lambda r: blocked.append(r.url))
    open_app()
    expect(page.locator("#search-topics .topic-link").first).to_be_visible()
    assert blocked and all("cdn.jsdelivr.net" in url for url in blocked)


# ---------- search ----------


def test_search_shows_results(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry(title="Graph Paper"), atom_entry(arxiv_id="2401.2v1", title="Other")))
    page = open_app()
    search(page, "graphs")
    expect(page.locator("#search-status")).to_have_text("2 results for “graphs”")
    cards = page.locator("#search-results .card")
    expect(cards).to_have_count(2)
    expect(cards.first).to_contain_text("Graph Paper")
    expect(cards.first).to_contain_text("Ada Lovelace, Alan Turing · 2024")
    expect(cards.first.get_by_role("link", name="PDF")).to_have_attribute("href", "https://arxiv.org/pdf/2401.00001v2")


def test_search_with_no_results(open_app, external):
    external.respond(ARXIV_API, text=atom_feed())
    page = open_app()
    search(page, "zzz")
    expect(page.locator("#search-status")).to_have_text("No results for “zzz”. Try different keywords.")


def test_search_failure_is_shown_and_the_form_recovers(open_app, external):
    external.respond(ARXIV_API, status=503)
    page = open_app()
    search(page, "x")
    expect(page.locator("#search-status")).to_contain_text("Search failed: arXiv returned HTTP 503")
    expect(page.locator("#search-form button")).to_be_enabled()


def test_blank_search_is_not_sent(open_app, external):
    page = open_app()
    page.locator("#search-input").fill("   ")
    page.locator("#search-input").press("Enter")
    expect(page.locator("#search-status")).to_have_text("")
    assert external.requests == []


def test_suggested_topic_runs_a_search(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    page = open_app()
    page.get_by_role("button", name="automated program repair").click()
    expect(page.locator("#search-status")).to_have_text("1 results for “automated program repair”")
    assert "repair" in external.hits(ARXIV_API)[0].url.params["search_query"]


def test_long_author_list_is_shortened(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry(authors=[f"Author {i}" for i in range(8)])))
    page = open_app()
    search(page, "x")
    meta = page.locator("#search-results .meta")
    expect(meta).to_contain_text("Author 5, et al.")
    expect(meta).not_to_contain_text("Author 6")


@pytest.mark.xfail(strict=True, reason="BUG: a 422 detail is a list, so the input (no maxlength) produces 'Search failed: [object Object]'")
def test_too_long_search_shows_a_readable_error(open_app):
    page = open_app()
    search(page, "x" * 201)
    expect(page.locator("#search-status")).to_contain_text("Search failed")
    expect(page.locator("#search-status")).not_to_contain_text("[object Object]", timeout=500)


# ---------- saving ----------


def test_save_then_find_in_library(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry(title="Saved Paper")))
    external.respond(ARXIV_PDF, content=make_pdf())
    page = open_app()
    search(page, "x")
    button = page.locator("#search-results").get_by_role("button", name="Save to library")
    button.click()
    expect(page.locator("#search-results button.small")).to_have_text("Saved ✓")
    expect(page.locator("#search-results button.small")).to_be_disabled()
    show_tab(page, "library")
    expect(page.locator("#library-status")).to_have_text("1 saved paper")
    expect(card(page, "Saved Paper")).to_contain_text("Full text ready")
    expect(card(page, "Saved Paper")).to_contain_text("arXiv")


def test_saved_paper_stays_marked_when_searching_again(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    external.respond(ARXIV_PDF, content=make_pdf())
    page = open_app()
    search(page, "x")
    page.get_by_role("button", name="Save to library").click()
    expect(page.locator("#search-results button.small")).to_have_text("Saved ✓")
    search(page, "x again")
    expect(page.locator("#search-status")).to_contain_text("x again")
    expect(page.locator("#search-results button.small")).to_have_text("Saved ✓")


def test_save_without_a_pdf_says_so(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    external.respond(ARXIV_PDF, status=404)
    page = open_app()
    search(page, "x")
    page.get_by_role("button", name="Save to library").click()
    button = page.locator("#search-results button.small")
    expect(button).to_have_text("Saved (no full text)")
    expect(button).to_have_attribute("title", re.compile("PDF download failed"))


def test_save_failure_allows_retry(open_app, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    external.respond(ARXIV_PDF, content=make_pdf())
    page = open_app()
    search(page, "x")
    page.route("**/api/papers", lambda r: r.fulfill(status=500, json={"detail": "boom"}), times=1)
    button = page.locator("#search-results button.small")
    button.click()
    expect(button).to_have_text("Save failed — retry")
    expect(button).to_be_enabled()
    button.click()
    expect(button).to_have_text("Saved ✓")


def test_already_saved_paper_is_marked_in_search(open_app, external):
    seed_paper(source="arxiv", external_id="2401.00001")
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    page = open_app()
    show_tab(page, "library")
    expect(page.locator("#library-status")).to_have_text("1 saved paper")
    show_tab(page, "search")
    search(page, "x")
    expect(page.locator("#search-results button.small")).to_have_text("Saved ✓")
    assert len(external.hits(ARXIV_PDF)) == 0


# ---------- library and uploads ----------


def test_empty_library_message(open_app):
    page = open_app()
    show_tab(page, "library")
    expect(page.locator("#library-status")).to_have_text("Your library is empty. Save papers from Search.")


def test_library_card_details(open_app):
    seed_paper(title="No Metadata", authors=[], year=None, abstract=None)
    page = open_app()
    show_tab(page, "library")
    expect(page.locator("#library-status")).to_have_text("1 saved paper")
    item = card(page, "No Metadata")
    expect(item).to_contain_text("Unknown authors · Year unknown")
    expect(item).to_contain_text("No abstract available.")
    expect(item).to_contain_text("Uploaded PDF")


def test_library_load_failure_is_shown(open_app):
    page = open_app()
    page.route("**/api/papers", lambda r: r.fulfill(status=500, json={"detail": "database is locked"}))
    show_tab(page, "library")
    expect(page.locator("#library-status")).to_have_text("Could not load library: database is locked")


def test_upload_pdf(open_app):
    page = open_app()
    show_tab(page, "library")
    upload_file(page, "my_paper.pdf", make_pdf(metadata={"title": "Uploaded Title"}))
    expect(page.locator("#upload-status")).to_contain_text("Added “Uploaded Title”.")
    expect(page.locator("#upload-status")).to_contain_text("Metadata extracted without Gemini")
    expect(card(page, "Uploaded Title")).to_contain_text("Full text ready")
    expect(page.locator("#upload-input")).to_have_value("")


def test_upload_of_a_non_pdf_shows_the_server_message(open_app):
    page = open_app()
    show_tab(page, "library")
    upload_file(page, "notes.txt", b"plain text", "text/plain")
    expect(page.locator("#upload-status")).to_have_text("Upload failed: Please upload a PDF file.")
    expect(page.locator("#upload-form button")).to_be_enabled()


def test_upload_of_a_scan_warns_and_disables_analysis(open_app):
    page = open_app()
    show_tab(page, "library")
    upload_file(page, "scan.pdf", make_pdf(None))
    expect(page.locator("#upload-status")).to_contain_text("no extractable text")
    expect(card(page, "scan")).to_contain_text("Full text unavailable")
    open_paper(page, "scan")
    expect(page.locator("#detail-content")).to_contain_text("full text is unavailable")
    expect(page.get_by_role("button", name="Summarize with Gemini")).to_have_count(0)


def test_titles_are_rendered_as_text_not_html(open_app):
    seed_paper(title="<img src=x onerror=\"window.pwned=1\">", abstract="<script>window.pwned=1</script>")
    page = open_app()
    show_tab(page, "library")
    expect(page.locator("#library-list .card h3")).to_contain_text("<img src=x")
    expect(page.locator("#library-list img")).to_have_count(0)
    assert page.evaluate("window.pwned") is None


# ---------- removing ----------


def test_remove_after_confirming(open_app, external):
    paper_id = seed_paper(title="Doomed")
    seed_paper(title="Survivor")
    page = open_app()
    show_tab(page, "library")
    messages = []
    page.once("dialog", lambda d: (messages.append(d.message), d.accept()))
    card(page, "Doomed").get_by_role("button", name="Remove").click()
    expect(page.locator("#library-status")).to_have_text("1 saved paper")
    expect(card(page, "Doomed")).to_have_count(0)
    assert 'Remove "Doomed"' in messages[0]
    assert db.get_paper(paper_id) is None


def test_cancelling_remove_keeps_the_paper(open_app):
    paper_id = seed_paper(title="Kept")
    page = open_app()
    show_tab(page, "library")
    page.once("dialog", lambda d: d.dismiss())
    card(page, "Kept").get_by_role("button", name="Remove").click()
    expect(card(page, "Kept")).to_have_count(1)
    assert db.get_paper(paper_id) is not None


def test_removing_the_open_paper_clears_the_paper_tab(open_app):
    seed_paper(title="Open one")
    page = open_app()
    open_paper(page, "Open one")
    expect(page.locator("#detail-content")).to_contain_text("Open one")
    show_tab(page, "library")
    page.once("dialog", lambda d: d.accept())
    card(page, "Open one").get_by_role("button", name="Remove").click()
    expect(page.locator("#library-status")).to_contain_text("empty")
    show_tab(page, "detail")
    expect(page.locator("#detail-content")).to_have_text("Open a paper from the Library to see it here.")


def test_removed_paper_can_be_saved_again_from_search(open_app, external):
    seed_paper(source="arxiv", external_id="2401.00001", title="Back again")
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    page = open_app()
    show_tab(page, "library")
    page.once("dialog", lambda d: d.accept())
    card(page, "Back again").get_by_role("button", name="Remove").click()
    expect(page.locator("#library-status")).to_contain_text("empty")
    show_tab(page, "search")
    search(page, "x")
    expect(page.locator("#search-results button.small")).to_have_text("Save to library")


# ---------- summary ----------


def test_summarize_and_regenerate(open_app, gemini):
    gemini.script(reply("First summary"), reply("Second summary"))
    seed_paper(title="To summarize")
    page = open_app()
    open_paper(page, "To summarize")
    expect(page.locator("#detail-content")).to_contain_text("No summary yet.")
    page.get_by_role("button", name="Summarize with Gemini").click()
    expect(page.locator("#detail-content")).to_contain_text("First summary")
    page.get_by_role("button", name="Regenerate summary").click()
    expect(page.locator("#detail-content")).to_contain_text("Second summary")
    expect(page.locator("#detail-content")).not_to_contain_text("First summary")


def test_stored_summary_is_shown_on_open(open_app, gemini):
    seed_paper(title="Has summary", summary="Previously stored")
    page = open_app()
    open_paper(page, "Has summary")
    expect(page.locator("#detail-content")).to_contain_text("Previously stored")
    expect(page.get_by_role("button", name="Regenerate summary")).to_be_visible()
    assert gemini.calls == []


def test_summary_failure_is_shown_and_can_be_retried(open_app, gemini):
    gemini.script(api_error(429), api_error(429), api_error(429), api_error(429), api_error(429), api_error(429), reply("Recovered"))
    seed_paper(title="Flaky")
    page = open_app()
    open_paper(page, "Flaky")
    button = page.get_by_role("button", name="Summarize with Gemini")
    button.click()
    expect(page.locator("#detail-content")).to_contain_text("Summary failed: Gemini rate limit")
    expect(button).to_be_enabled()
    button.click()
    expect(page.locator("#detail-content")).to_contain_text("Recovered")


def test_summary_without_a_key_explains_the_fix(open_app):
    seed_paper(title="No key")
    page = open_app()
    open_paper(page, "No key")
    page.get_by_role("button", name="Summarize with Gemini").click()
    expect(page.locator("#detail-content")).to_contain_text("GEMINI_API_KEY is not set")


def test_truncated_summary_shows_a_note(open_app, gemini):
    seed_paper(title="Very long", full_text="x" * 300_001)
    page = open_app()
    open_paper(page, "Very long")
    page.get_by_role("button", name="Summarize with Gemini").click()
    expect(page.locator("#detail-content")).to_contain_text("only the first ~300,000 characters")


def test_markdown_falls_back_to_plain_text_without_the_cdn(open_app):
    seed_paper(title="Plain", summary="<b>not bold</b> **raw**")
    page = open_app()
    open_paper(page, "Plain")
    markdown = page.locator(".markdown")
    expect(markdown).to_have_text("<b>not bold</b> **raw**")
    expect(markdown.locator("b")).to_have_count(0)


def test_model_output_passes_through_the_sanitizer(open_app):
    seed_paper(title="Hostile", summary="Fine<script>window.pwned=1</script>")
    page = open_app({"marked": MARKED_STUB, "purify": DOMPURIFY_STUB})
    open_paper(page, "Hostile")
    expect(page.locator(".markdown")).to_have_text("Fine")
    expect(page.locator(".markdown script")).to_have_count(0)


def test_math_is_rendered_but_currency_is_left_alone(open_app):
    seed_paper(title="Math", summary="Cost $5 and $10, loss $x_0$ and $$y$$")
    page = open_app({"marked": MARKED_STUB, "purify": DOMPURIFY_STUB, "katex": KATEX_STUB})
    open_paper(page, "Math")
    expect(page.locator(".markdown .katex")).to_have_text(["x_0", "y"])
    expect(page.locator(".markdown")).to_contain_text("Cost $5 and $10")


# ---------- questions ----------


def test_ask_with_the_button(open_app, gemini):
    gemini.script(reply("Because of graphs."))
    seed_paper(title="Q paper")
    page = open_app()
    open_paper(page, "Q paper")
    page.locator(".qa-form textarea").fill("Why?")
    page.locator(".qa-form button").click()
    item = page.locator(".qa-item")
    expect(item.locator(".question")).to_have_text("Why?")
    expect(item).to_contain_text("Because of graphs.")
    expect(page.locator(".qa-form textarea")).to_have_value("")


def test_enter_sends_and_shift_enter_adds_a_line(open_app, gemini):
    seed_paper(title="Keys")
    page = open_app()
    open_paper(page, "Keys")
    box = page.locator(".qa-form textarea")
    box.fill("line one")
    box.press("Shift+Enter")
    expect(page.locator(".qa-item")).to_have_count(0)
    assert box.input_value() == "line one\n"
    box.press("Enter")
    expect(page.locator(".qa-item")).to_have_count(1)
    expect(page.locator(".qa-item")).to_contain_text("Fake Gemini answer")


def test_example_question_chip(open_app, gemini):
    seed_paper(title="Chips")
    page = open_app()
    open_paper(page, "Chips")
    page.get_by_role("button", name="What datasets are used?").click()
    expect(page.locator(".qa-item .question")).to_have_text("What datasets are used?")
    expect(page.locator(".qa-item")).to_contain_text("Fake Gemini answer")
    assert gemini.last_prompt.endswith("Question: What datasets are used?")


def test_blank_question_is_not_sent(open_app, gemini):
    seed_paper(title="Blank")
    page = open_app()
    open_paper(page, "Blank")
    page.locator(".qa-form textarea").fill("   ")
    page.locator(".qa-form button").click()
    expect(page.locator(".qa-item")).to_have_count(0)
    assert gemini.calls == []


def test_newest_question_is_on_top(open_app, gemini):
    gemini.script(reply("A1"), reply("A2"))
    seed_paper(title="Order")
    page = open_app()
    open_paper(page, "Order")
    box = page.locator(".qa-form textarea")
    box.fill("First?")
    box.press("Enter")
    expect(page.locator(".qa-item").first).to_contain_text("A1")
    box.fill("Second?")
    box.press("Enter")
    expect(page.locator(".qa-item").first).to_contain_text("A2")
    expect(page.locator(".qa-item")).to_have_count(2)


def test_answer_failure_is_shown(open_app):
    seed_paper(title="No key Q")
    page = open_app()
    open_paper(page, "No key Q")
    box = page.locator(".qa-form textarea")
    box.fill("Why?")
    box.press("Enter")
    expect(page.locator(".qa-item")).to_contain_text("Could not answer: GEMINI_API_KEY is not set")
    expect(page.locator(".qa-form button")).to_be_enabled()


def test_opening_a_missing_paper_shows_an_error(open_app):
    page = open_app()
    page.evaluate("openPaper(99999)")
    expect(page.locator("#detail-content")).to_have_text("Could not load paper: Paper not found")


# ---------- citation graph ----------


def test_graph_explains_when_the_library_cannot_load(open_app):
    page = open_app()
    show_tab(page, "library")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-status")).to_contain_text("Graph library failed to load")
    expect(page.locator("#graph-toggle")).to_have_text("Hide citation graph")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-panel")).to_be_hidden()
    expect(page.locator("#graph-toggle")).to_have_text("Show citation graph")


def test_graph_shows_counts_and_builds_the_network(open_app):
    a, b = seed_paper(title="Citing"), seed_paper(title="Cited")
    lonely = seed_paper(title="Lonely")
    db.set_openalex(a, "ok", "W1", ["W2"])
    db.set_openalex(b, "ok", "W2", [])
    db.set_openalex(lonely, "not_found", None, [])
    page = open_app({"vis-network": VIS_STUB})
    show_tab(page, "library")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-status")).to_contain_text("3 papers, 1 citation link between them")
    expect(page.locator("#graph-status")).to_contain_text("1 paper(s) without citation data")
    graph = page.evaluate(
        "(() => { const d = window.visCreated.at(-1);"
        " return { nodes: d.nodes.get().length, edges: d.edges.get().map(e => [e.from, e.to]) }; })()"
    )
    assert graph == {"nodes": 3, "edges": [[a, b]]}


def test_graph_unlinked_toggle_hides_orphans(open_app):
    a, b = seed_paper(title="Citing"), seed_paper(title="Cited")
    lonely = seed_paper(title="Lonely")
    db.set_openalex(a, "ok", "W1", ["W2"])
    db.set_openalex(b, "ok", "W2", [])
    db.set_openalex(lonely, "not_found", None, [])
    page = open_app({"vis-network": VIS_STUB})
    show_tab(page, "library")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-status")).to_contain_text("3 papers")
    page.locator("#graph-orphans").uncheck()
    hidden = page.evaluate("window.visCreated.at(-1).nodes.get().filter(n => n.hidden).map(n => n.id)")
    assert hidden == [lonely]


def test_graph_failure_is_shown(open_app, external):
    page = open_app({"vis-network": VIS_STUB})
    page.route("**/api/graph", lambda r: r.fulfill(status=500, json={"detail": "boom"}))
    show_tab(page, "library")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-status")).to_have_text("Could not build the citation graph: boom")


# ---------- whole journey ----------


def test_full_journey(open_app, external, gemini):
    external.respond(ARXIV_API, text=atom_feed(atom_entry(title="Journey Paper")))
    external.respond(ARXIV_PDF, content=make_pdf())
    gemini.script(reply("Journey summary"), reply("Journey answer"))
    page = open_app()

    search(page, "journey")
    page.get_by_role("button", name="Save to library").click()
    expect(page.locator("#search-results button.small")).to_have_text("Saved ✓")

    open_paper(page, "Journey Paper")
    page.get_by_role("button", name="Summarize with Gemini").click()
    expect(page.locator("#detail-content")).to_contain_text("Journey summary")

    box = page.locator(".qa-form textarea")
    box.fill("What happened?")
    box.press("Enter")
    expect(page.locator(".qa-item")).to_contain_text("Journey answer")

    page.reload()
    open_paper(page, "Journey Paper")
    expect(page.locator("#detail-content")).to_contain_text("Journey summary")
    assert len(gemini.calls) == 2
