import pytest

from app import metadata
from helpers import api_error, make_pdf, reply, run


def parsed(**overrides):
    values = {"title": "T", "authors": ["A"], "year": 2020, "abstract": "Abs"}
    return metadata.PaperMetadata(**{**values, **overrides})


def test_extract_returns_gemini_metadata(gemini):
    gemini.script(reply(parsed=parsed(title="From Gemini", year=None)))
    meta, warning = run(metadata.extract("head", make_pdf(), "x.pdf"))
    assert meta == {"title": "From Gemini", "authors": ["A"], "year": None, "abstract": "Abs"}
    assert warning is None


def test_extract_sends_only_the_head_of_the_paper_with_a_schema(gemini):
    gemini.script(reply(parsed=parsed()))
    text = "x" * metadata.HEAD_CHARS + "BEYOND_THE_HEAD"
    run(metadata.extract(text, make_pdf(), "x.pdf"))
    assert "BEYOND_THE_HEAD" not in gemini.last_prompt
    assert gemini.calls[0].config.response_schema is metadata.PaperMetadata


def test_extract_falls_back_and_warns_when_gemini_fails(gemini):
    gemini.script(api_error(400, "bad request"))
    data = make_pdf(metadata={"title": "Embedded Title"})
    meta, warning = run(metadata.extract("head", data, "x.pdf"))
    assert meta["title"] == "Embedded Title"
    assert warning.startswith("Metadata extracted without Gemini")
    assert "bad request" in warning


def test_extract_falls_back_when_there_is_no_api_key():
    meta, warning = run(metadata.extract("head", make_pdf(), "my_paper.pdf"))
    assert meta["title"] == "my paper"
    assert "GEMINI_API_KEY" in warning


def test_fallback_uses_embedded_pdf_metadata():
    data = make_pdf(metadata={"title": "  Title  ", "author": "Ada Lovelace; Alan Turing", "creationDate": "D:20190304"})
    meta = metadata.fallback("", data, "ignored.pdf")
    assert meta == {"title": "Title", "authors": ["Ada Lovelace", "Alan Turing"], "year": 2019, "abstract": None}


@pytest.mark.parametrize(
    "author, expected",
    [
        ("Ada, Alan", ["Ada", "Alan"]),
        ("Ada and Alan", ["Ada", "Alan"]),
        ("Ada Anderson", ["Ada Anderson"]),  # "and" inside a name does not split
        ("", []),
    ],
)
def test_fallback_splits_authors(author, expected):
    assert metadata.fallback("", make_pdf(metadata={"author": author}), "f.pdf")["authors"] == expected


@pytest.mark.parametrize(
    "filename, title",
    [
        ("deep_learning_survey.pdf", "deep learning survey"),
        ("/some/dir/paper.pdf", "paper"),
    ],
)
def test_fallback_derives_title_from_filename(filename, title):
    assert metadata.fallback("", make_pdf(), filename)["title"] == title


ABSTRACT_BODY = "This paper studies a very specific problem in considerable detail and it reports results on many tasks."


def test_fallback_finds_abstract_ending_at_a_blank_line():
    head = f"Title\n\nAbstract\n{ABSTRACT_BODY}\n\nIntroduction starts here."
    assert metadata.fallback(head, make_pdf(), "f.pdf")["abstract"] == ABSTRACT_BODY


def test_fallback_finds_abstract_ending_at_introduction():
    head = f"ABSTRACT: {ABSTRACT_BODY} 1. Introduction"
    assert metadata.fallback(head, make_pdf(), "f.pdf")["abstract"] == ABSTRACT_BODY


def test_fallback_rejoins_words_hyphenated_across_lines():
    head = f"Abstract\nThe optimi-\nzation of {ABSTRACT_BODY}\n\nNext"
    assert "optimization" in metadata.fallback(head, make_pdf(), "f.pdf")["abstract"]


def test_fallback_ignores_an_abstract_that_is_too_short():
    assert metadata.fallback("Abstract\nToo short.\n\nBody", make_pdf(), "f.pdf")["abstract"] is None
