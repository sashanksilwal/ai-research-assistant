import httpx
import pytest

from app import pdf
from helpers import LONG_TEXT, assert_bounded_timeout, make_pdf, run, word_chars

HOST = "arxiv.org"
URL = "https://arxiv.org/pdf/1"


def test_extract_text_reads_a_real_pdf():
    assert word_chars(LONG_TEXT)[:40] in word_chars(pdf.extract_text(make_pdf()))


def test_extract_text_rejects_a_blank_pdf():
    with pytest.raises(pdf.PdfError, match="no extractable text"):
        pdf.extract_text(make_pdf(None))


def test_extract_text_rejects_text_just_under_the_minimum():
    with pytest.raises(pdf.PdfError, match="no extractable text"):
        pdf.extract_text(make_pdf("x" * 50))


@pytest.mark.parametrize("data", [b"", b"not a pdf", b"%PDF-1.7 truncated garbage"])
def test_extract_text_rejects_corrupt_files(data):
    with pytest.raises(pdf.PdfError, match="Could not read PDF"):
        pdf.extract_text(data)


def _fake_doc(monkeypatch, text):
    class Page:
        def get_text(self):
            return text

    class Doc(list):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(pdf.pymupdf, "open", lambda **kwargs: Doc([Page()]))


def test_extract_text_removes_nul_characters(monkeypatch):
    _fake_doc(monkeypatch, "a\x00b" * 300)
    assert "\x00" not in pdf.extract_text(b"ignored")


def test_minimum_length_ignores_surrounding_whitespace(monkeypatch):
    _fake_doc(monkeypatch, " " * 1000 + "x" * (pdf.MIN_TEXT_CHARS - 1))
    with pytest.raises(pdf.PdfError):
        pdf.extract_text(b"ignored")


def test_exactly_the_minimum_length_is_accepted(monkeypatch):
    _fake_doc(monkeypatch, "x" * pdf.MIN_TEXT_CHARS)
    assert len(pdf.extract_text(b"ignored")) == pdf.MIN_TEXT_CHARS


def test_download_returns_pdf_bytes(external):
    external.respond(HOST, content=b"%PDF-1.7 data")
    assert run(pdf.download(URL)) == b"%PDF-1.7 data"


def test_download_follows_redirects(external):
    external.respond("export.arxiv.org", content=b"%PDF-1.7 moved")
    external.respond(HOST, status=301, headers={"location": "https://export.arxiv.org/pdf/1"})
    assert run(pdf.download(URL)) == b"%PDF-1.7 moved"


def test_download_rejects_non_pdf_content(external):
    external.respond(HOST, text="<html>captcha</html>")
    with pytest.raises(pdf.PdfError, match="not a PDF"):
        run(pdf.download(URL))


def test_download_reports_http_error(external):
    external.respond(HOST, status=404)
    with pytest.raises(pdf.PdfError, match="HTTPStatusError"):
        run(pdf.download(URL))


def test_download_reports_timeout(external):
    external.fail(HOST, httpx.ReadTimeout)
    with pytest.raises(pdf.PdfError, match="ReadTimeout"):
        run(pdf.download(URL))


def test_download_sets_a_timeout(external):
    external.respond(HOST, content=b"%PDF")
    run(pdf.download(URL))
    assert_bounded_timeout(external.requests[0])
