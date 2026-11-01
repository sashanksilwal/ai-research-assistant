"""The real frontend in headless Chromium against the real backend.

marked, DOMPurify, KaTeX and vis-network are the exact builds from static/index.html, served at their CDN
URLs from tests/fixtures/vendor. open_app(offline=True) makes them fail, for the app's no-internet mode.
"""
import re

import pytest
from playwright.sync_api import expect

from app import db
from conftest import wait_for_app_idle
from helpers import api_error, atom_entry, atom_feed, make_pdf, reply, seed_paper

pytestmark = pytest.mark.e2e

ARXIV_API = "export.arxiv.org"
ARXIV_PDF = "arxiv.org"


def search(page, text):
    page.locator("#search-input").fill(text)
    page.locator("#search-form button").click()


def show_tab(page, name):
    wait_for_app_idle(page)  # the startup load would otherwise replace the cards mid-test
    page.locator(f'.tab[data-tab="{name}"]').click()
    wait_for_app_idle(page)


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
    open_app(offline=True)
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


def test_abstract_expands_and_collapses_on_click(open_app):
    seed_paper(title="Wordy", abstract="A long abstract sentence that wraps across many lines. " * 40)
    page = open_app()
    show_tab(page, "library")
    abstract = card(page, "Wordy").locator(".abstract")
    collapsed = abstract.bounding_box()["height"]
    abstract.click()
    expanded = abstract.bounding_box()["height"]
    assert expanded > collapsed
    abstract.click()
    assert abstract.bounding_box()["height"] == collapsed


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


def test_remove_failure_is_shown(open_app):
    paper_id = seed_paper(title="Already gone")
    page = open_app()
    show_tab(page, "library")
    expect(card(page, "Already gone")).to_have_count(1)
    db.delete_paper(paper_id)  # removed elsewhere, so the server answers 404
    page.once("dialog", lambda d: d.accept())
    card(page, "Already gone").get_by_role("button", name="Remove").click()
    expect(page.locator("#library-status")).to_have_text("Could not remove paper: Paper not found")


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
    page = open_app(offline=True)
    open_paper(page, "Plain")
    markdown = page.locator(".markdown")
    expect(markdown).to_have_text("<b>not bold</b> **raw**")
    expect(markdown.locator("b")).to_have_count(0)


def open_summary(open_app, summary):
    seed_paper(title="Rendered", summary=summary)
    page = open_app()
    open_paper(page, "Rendered")
    expect(page.locator(".markdown")).to_be_visible()
    return page


def test_model_markdown_is_rendered(open_app):
    page = open_summary(open_app, "## Problem\n\nThis is **important**:\n\n- first\n- second")
    expect(page.locator(".markdown h2")).to_have_text("Problem")
    expect(page.locator(".markdown strong")).to_have_text("important")
    expect(page.locator(".markdown li")).to_have_count(2)


@pytest.mark.parametrize(
    "payload",
    [
        "<script>window.pwned = 1</script>",
        '<img src="missing.png" onerror="window.pwned = 2">',
        '<svg><script>window.pwned = 3</script></svg>',
        '<a href="javascript:window.pwned = 4" id="evil">link</a>',
        '<div onmouseover="window.pwned = 5" id="evil">hover</div>',
        '<iframe srcdoc="<script>parent.pwned = 6</script>"></iframe>',
        '[click](javascript:window.pwned=7)',
    ],
)
def test_dompurify_removes_xss_from_model_output(open_app, payload):
    page = open_summary(open_app, f"Safe intro.\n\n{payload}\n\nSafe outro.")
    markdown = page.locator(".markdown")
    expect(markdown).to_contain_text("Safe intro.")
    expect(markdown).to_contain_text("Safe outro.")
    assert markdown.locator("script, iframe, [onerror], [onmouseover], a[href^='javascript']").count() == 0
    links = markdown.locator("a, #evil")
    for i in range(links.count()):
        links.nth(i).hover()
        links.nth(i).click(force=True)
    wait_for_app_idle(page)
    assert page.evaluate("window.pwned") is None


@pytest.mark.parametrize("latex", [r"$\href{javascript:window.pwned=1}{click}$", r"$\url{javascript:window.pwned=2}$"])
def test_katex_does_not_create_links_from_math(open_app, latex):
    page = open_summary(open_app, f"Before {latex} after")
    assert page.locator(".markdown a").count() == 0
    assert page.evaluate("window.pwned") is None


def test_each_formula_renders_exactly_once(open_app):
    page = open_summary(open_app, "Inline $x_0$ then display $$\\sum_i y_i$$ end")
    assert page.locator(".markdown .katex").count() == 2
    assert page.locator(".markdown .katex-display .katex").count() == 1
    assert page.locator(".markdown .katex-mathml").count() == 0
    assert page.locator(".markdown").text_content().count("∑") == 1
    expect(page.locator(".markdown")).not_to_contain_text("$")


def test_underscores_in_math_are_not_treated_as_markdown(open_app):
    page = open_summary(open_app, "Terms $a_b$ and $c_d$ stay math")
    assert page.locator(".markdown em").count() == 0
    assert page.locator(".markdown .katex").count() == 2


def test_currency_is_not_treated_as_math(open_app):
    page = open_summary(open_app, "It costs $5 and $10 per run")
    assert page.locator(".markdown .katex").count() == 0
    expect(page.locator(".markdown")).to_have_text("It costs $5 and $10 per run")


def test_invalid_latex_does_not_break_the_page(open_app):
    page = open_summary(open_app, r"Broken $\frac{1$ but the rest shows")
    expect(page.locator(".markdown")).to_contain_text("but the rest shows")


@pytest.mark.xfail(strict=True, reason="BUG: formulas are put back after DOMPurify runs, so math inside an HTML attribute breaks out of it and corrupts the sanitized DOM")
def test_math_inside_an_attribute_stays_inside_it(open_app):
    page = open_summary(open_app, '<a title="$a$ note" href="https://example.org/">link</a>')
    link = page.locator(".markdown a")
    expect(link).to_have_text("link", timeout=1000)
    assert link.get_attribute("href") == "https://example.org/"


@pytest.mark.xfail(strict=True, reason="BUG: the math placeholder isn't unique, so model text containing KATEXMATH99END renders as 'undefined'")
def test_text_resembling_the_math_placeholder_is_kept(open_app):
    page = open_summary(open_app, "The token KATEXMATH99END appears here")
    expect(page.locator(".markdown")).to_contain_text("KATEXMATH99END", timeout=1000)


@pytest.mark.xfail(strict=True, reason="BUG: math is extracted before Markdown runs, so $...$ inside a code span is rendered as a formula, not shown verbatim")
def test_code_span_is_shown_verbatim(open_app):
    page = open_summary(open_app, "Use `$x$` literally")
    expect(page.locator(".markdown code")).to_have_text("$x$", timeout=1000)


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
    expect(item).not_to_contain_text("300,000")  # the truncation note is for long papers only
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


def test_truncated_answer_shows_a_note(open_app, gemini):
    gemini.script(reply("Long paper answer"))
    seed_paper(title="Very long Q", full_text="x" * 300_001)
    page = open_app()
    open_paper(page, "Very long Q")
    box = page.locator(".qa-form textarea")
    box.fill("Why?")
    box.press("Enter")
    expect(page.locator(".qa-item")).to_contain_text("Long paper answer")
    expect(page.locator(".qa-item")).to_contain_text("only the first ~300,000 characters")


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
    page = open_app(offline=True)
    show_tab(page, "library")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-status")).to_contain_text("Graph library failed to load")
    expect(page.locator("#graph-toggle")).to_have_text("Hide citation graph")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-panel")).to_be_hidden()
    expect(page.locator("#graph-toggle")).to_have_text("Show citation graph")


# ---------- citation graph, on the real vis-network canvas ----------


def seed_graph(titles, links=(), **fields):
    """Seed papers and their citation links, given as (citing index, cited index)."""
    ids = [seed_paper(title=title, **fields) for title in titles]
    for index, paper_id in enumerate(ids):
        refs = [f"W{ids[cited]}" for citing, cited in links if citing == index]
        db.set_openalex(paper_id, "ok", f"W{paper_id}", refs)
    return ids


def show_graph(open_app, paper_count):
    page = open_app()
    show_tab(page, "library")
    page.locator("#graph-toggle").click()
    expect(page.locator("#graph-status")).to_contain_text(f"{paper_count} papers")
    wait_for_app_idle(page)
    expect(page.locator("#graph canvas")).to_be_visible()
    # Freeze the physics and frame every node so canvas coordinates stay valid for the mouse.
    page.evaluate("graph.network.stopSimulation(); graph.network.fit({ animation: false });")
    page.locator("#graph").scroll_into_view_if_needed()
    return page


def drawn_nodes(page):
    return {n["id"]: n for n in page.evaluate("graph.nodes.get()")}


def drawn_edges(page):
    return page.evaluate("graph.edges.get()")


def node_point(page, node_id):
    return page.evaluate(
        """id => {
          const dom = graph.network.canvasToDOM(graph.network.getPositions([id])[id]);
          const box = document.querySelector("#graph canvas").getBoundingClientRect();
          return [box.left + dom.x, box.top + dom.y];
        }""",
        node_id,
    )


def empty_point(page):
    box = page.locator("#graph canvas").bounding_box()
    return box["x"] + 3, box["y"] + 3


def hover(page, node_id):
    x, y = node_point(page, node_id)
    page.mouse.move(x - 1, y)
    page.mouse.move(x, y)
    page.wait_for_function("id => graph.hovered === id", arg=node_id)


def is_faded(node):
    return node["opacity"] < 1


def test_graph_draws_papers_and_citations(open_app):
    a, b, lonely = seed_graph(["Citing", "Cited", "Lonely"], links=[(0, 1)])
    db.set_openalex(lonely, "not_found", None, [])
    page = show_graph(open_app, 3)
    expect(page.locator("#graph-status")).to_contain_text("3 papers, 1 citation link between them")
    expect(page.locator("#graph-status")).to_contain_text("1 paper(s) without citation data")
    assert set(drawn_nodes(page)) == {a, b, lonely}
    assert [(e["from"], e["to"]) for e in drawn_edges(page)] == [(a, b)]
    assert page.evaluate("id => graph.network.getConnectedNodes(id, 'to')", a) == [b]  # A cites B
    edge = page.evaluate("id => graph.network.body.edges[id].options.arrows.to.enabled", f"{a}-{b}")
    assert edge is True  # drawn with the arrowhead at the cited paper


def test_graph_unlinked_toggle_hides_orphans(open_app):
    a, b, lonely = seed_graph(["Citing", "Cited", "Lonely"], links=[(0, 1)])
    page = show_graph(open_app, 3)
    page.locator("#graph-orphans").uncheck()
    assert [i for i, n in drawn_nodes(page).items() if n.get("hidden")] == [lonely]
    page.locator("#graph-orphans").check()
    assert not any(n.get("hidden") for n in drawn_nodes(page).values())


def test_graph_title_search_highlights_matches_until_cleared(open_app):
    match, other = seed_graph(["Graph Neural Networks", "Vision Transformers"])
    page = show_graph(open_app, 2)
    page.locator("#graph-search").fill("  NEURAL ")
    nodes = drawn_nodes(page)
    assert not is_faded(nodes[match]) and nodes[match]["label"] == "Graph Neural Networks"
    assert is_faded(nodes[other]) and nodes[other]["label"] == ""
    page.locator("#graph-search").fill("")
    nodes = drawn_nodes(page)
    assert not is_faded(nodes[match]) and not is_faded(nodes[other])
    assert nodes[other]["label"] == "Vision Transformers"


def test_graph_label_limit_prefers_the_most_linked_and_is_remembered(open_app):
    ids = seed_graph([f"Paper {i}" for i in range(7)], links=[(i, 6) for i in range(6)])  # all cite Paper 6
    page = show_graph(open_app, 7)

    def labelled():
        return {i for i, n in drawn_nodes(page).items() if n["label"]}

    assert len(labelled()) == 5  # default: Top 5
    assert ids[6] in labelled()
    page.locator("#graph-labels").select_option("0")
    assert labelled() == set()
    page.locator("#graph-labels").select_option("all")
    assert labelled() == set(ids)

    page.locator("#graph-labels").select_option("0")
    page.reload()
    expect(page.locator("#graph-labels")).to_have_value("0")


def test_graph_long_title_is_shortened_until_hovered(open_app):
    title = "A Remarkably Long Title About Graph Neural Networks And Much More"
    paper_id = seed_graph([title], year=2021)[0]
    page = show_graph(open_app, 1)
    assert drawn_nodes(page)[paper_id]["label"] == title[:31] + "…"
    hover(page, paper_id)
    assert drawn_nodes(page)[paper_id]["label"] == f"{title} (2021)"


def test_graph_hover_focuses_a_paper_and_its_links_until_blur(open_app):
    hovered, neighbour, far_a, far_b = seed_graph(["Hovered", "Neighbour", "Far A", "Far B"], links=[(0, 1), (2, 3)])
    page = show_graph(open_app, 4)
    hover(page, hovered)

    nodes = drawn_nodes(page)
    assert not is_faded(nodes[hovered]) and not is_faded(nodes[neighbour])
    assert nodes[neighbour]["label"] == "Neighbour"
    assert is_faded(nodes[far_a]) and nodes[far_a]["label"] == ""
    assert is_faded(nodes[far_b])
    widths = {(e["from"], e["to"]): e["width"] for e in drawn_edges(page)}
    assert widths == {(hovered, neighbour): 2, (far_a, far_b): 1}

    page.mouse.move(*empty_point(page))
    page.wait_for_function("graph.hovered === null")
    assert not any(is_faded(n) for n in drawn_nodes(page).values())
    assert all(e["width"] == 1 for e in drawn_edges(page))


def test_graph_click_opens_the_paper(open_app):
    first, _ = seed_graph(["Clicked Paper", "Other Paper"])
    page = show_graph(open_app, 2)
    page.mouse.click(*node_point(page, first))
    expect(page.locator("#detail")).to_be_visible()
    expect(page.locator("#detail-content h3").first).to_have_text("Clicked Paper")


def test_graph_click_on_empty_space_stays_on_the_library(open_app):
    seed_graph(["Paper"])
    page = show_graph(open_app, 1)
    page.mouse.click(*empty_point(page))
    page.wait_for_timeout(300)  # time for a wrongly fired click handler to act
    expect(page.locator("#library")).to_be_visible()
    expect(page.locator("#detail-content")).to_contain_text("Open a paper from the Library")


def test_graph_follows_library_changes_while_open(open_app):
    keep, remove = seed_graph(["Keep", "Remove me"])
    page = show_graph(open_app, 2)
    page.once("dialog", lambda d: d.accept())
    card(page, "Remove me").get_by_role("button", name="Remove").click()
    expect(page.locator("#graph-status")).to_contain_text("1 papers")
    assert set(drawn_nodes(page)) == {keep}


def test_graph_failure_is_shown(open_app):
    page = open_app()
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
