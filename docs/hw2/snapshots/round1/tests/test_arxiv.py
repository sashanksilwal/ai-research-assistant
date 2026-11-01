"""arXiv query building and Atom parsing, through the public search() function."""
import httpx
import pytest

from app import arxiv
from helpers import assert_bounded_timeout, atom_entry, atom_feed, run

HOST = "export.arxiv.org"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("graph neural", "all:graph AND all:neural"),
        ("what is the attention", "all:attention"),
        ("WHAT Is Attention", "all:Attention"),
        ("what is", "all:what AND all:is"),  # only stopwords: keep them rather than search nothing
        ('title:"gan" (x)', "all:title AND all:gan AND all:x"),  # query syntax is stripped
        ("self-attention", "all:self-attention"),
        ("transformer résumé", "all:transformer AND all:résumé"),
        ("???", ""),
        ("   ", ""),
    ],
)
def test_build_query(text, expected):
    assert arxiv._build_query(text) == expected


def test_search_sends_expected_parameters(external):
    external.respond(HOST, text=atom_feed())
    run(arxiv.search("graph neural", max_results=3))
    params = external.requests[0].url.params
    assert params["search_query"] == "all:graph AND all:neural"
    assert params["max_results"] == "3"
    assert params["sortBy"] == "relevance"


def test_search_normalizes_an_entry(external):
    external.respond(HOST, text=atom_feed(atom_entry()))
    assert run(arxiv.search("x")) == [
        {
            "external_id": "2401.00001",
            "title": "A Paper",
            "authors": ["Ada Lovelace", "Alan Turing"],
            "year": 2024,
            "abstract": "An abstract.",
            "url": "https://arxiv.org/abs/2401.00001v2",
            "pdf_url": "https://arxiv.org/pdf/2401.00001v2",
        }
    ]


def test_search_collapses_whitespace_in_wrapped_fields(external):
    entry = atom_entry(title="Line one\n   line two", summary="\n  Text\n\n  more  ")
    external.respond(HOST, text=atom_feed(entry))
    paper = run(arxiv.search("x"))[0]
    assert paper["title"] == "Line one line two"
    assert paper["abstract"] == "Text more"


def test_search_builds_pdf_url_when_the_link_is_absent(external):
    external.respond(HOST, text=atom_feed(atom_entry(pdf_link=False)))
    assert run(arxiv.search("x"))[0]["pdf_url"] == "https://arxiv.org/pdf/2401.00001v2"


def test_search_handles_old_style_ids(external):
    external.respond(HOST, text=atom_feed(atom_entry(arxiv_id="cs/0112017v1")))
    assert run(arxiv.search("x"))[0]["external_id"] == "cs/0112017"


def test_search_keeps_a_paper_with_no_authors(external):
    external.respond(HOST, text=atom_feed(atom_entry(authors=())))
    assert run(arxiv.search("x"))[0]["authors"] == []


def test_search_drops_arxiv_error_entries(external):
    error = "<entry><id>http://arxiv.org/api/errors#bad_query</id><title>Error</title></entry>"
    external.respond(HOST, text=atom_feed(error, atom_entry()))
    assert [p["external_id"] for p in run(arxiv.search("x"))] == ["2401.00001"]


@pytest.mark.parametrize("exc_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_search_reports_network_failure_by_type(external, exc_type):
    external.fail(HOST, exc_type)
    with pytest.raises(arxiv.ArxivError, match=f"Could not reach arXiv: {exc_type.__name__}"):
        run(arxiv.search("x"))


def test_search_sets_a_timeout(external):
    external.respond(HOST, text=atom_feed())
    run(arxiv.search("x"))
    assert_bounded_timeout(external.requests[0])
