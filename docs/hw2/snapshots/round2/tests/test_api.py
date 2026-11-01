"""HTTP API, exercised through FastAPI with only the outside world faked."""
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import analysis, db, main
from helpers import LONG_TEXT, api_error, atom_entry, atom_feed, make_pdf, reply, search_result, seed_paper, word_chars

ARXIV_API = "export.arxiv.org"
ARXIV_PDF = "arxiv.org"


def upload(client, data, filename="paper.pdf"):
    return client.post("/api/upload", files={"file": (filename, data, "application/pdf")})


def stored_pdfs(storage):
    return sorted(storage.pdf_dir.iterdir())


# ---------- basics and static files ----------


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AI Research Assistant" in response.text


@pytest.mark.parametrize("path, content_type", [("/app.js", "javascript"), ("/styles.css", "text/css")])
def test_frontend_assets_are_served(client, path, content_type):
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]


@pytest.mark.parametrize("path", ["/nope.html", "/api/unknown", "/.env", "/../app/main.py"])
def test_unknown_and_private_paths_are_not_served(client, path):
    assert client.get(path).status_code == 404


def test_wrong_method_is_rejected(client):
    assert client.put("/api/papers/1", json={}).status_code == 405


def test_startup_creates_the_database(storage):
    storage.db_path.unlink()
    with TestClient(main.app) as c:
        assert c.get("/api/papers").json() == []
    assert storage.db_path.exists()


def test_library_survives_a_restart():
    paper_id = seed_paper(title="Persistent")
    with TestClient(main.app) as c:
        assert c.get(f"/api/papers/{paper_id}").json()["title"] == "Persistent"
    with TestClient(main.app) as c:
        assert c.get(f"/api/papers/{paper_id}").json()["title"] == "Persistent"


# ---------- search ----------


def test_search_returns_normalized_results(client, external):
    external.respond(ARXIV_API, text=atom_feed(atom_entry(), atom_entry(arxiv_id="2401.00002v1", title="Other")))
    response = client.get("/api/search", params={"q": "graph neural"})
    assert response.status_code == 200
    assert [p["title"] for p in response.json()] == ["A Paper", "Other"]
    assert external.requests[0].url.params["max_results"] == "10"


def test_search_with_no_matches(client, external):
    external.respond(ARXIV_API, text=atom_feed())
    assert client.get("/api/search", params={"q": "zzz"}).json() == []


@pytest.mark.parametrize("q", ["???", "   "])
def test_search_with_nothing_searchable_returns_empty(client, external, q):
    assert client.get("/api/search", params={"q": q}).json() == []
    assert external.requests == []


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "x" * 201}])
def test_search_validates_q(client, params):
    assert client.get("/api/search", params=params).status_code == 422


def test_search_accepts_the_longest_allowed_query(client, external):
    external.respond(ARXIV_API, text=atom_feed())
    assert client.get("/api/search", params={"q": "x" * 200}).status_code == 200
    assert external.requests[0].url.params["search_query"] == "all:" + "x" * 200


def test_search_upstream_status_is_a_502(client, external):
    external.respond(ARXIV_API, status=503)
    response = client.get("/api/search", params={"q": "x"})
    assert response.status_code == 502
    assert "HTTP 503" in response.json()["detail"]


def test_search_network_failure_is_a_502(client, external):
    external.fail(ARXIV_API, httpx.ConnectTimeout)
    response = client.get("/api/search", params={"q": "x"})
    assert response.status_code == 502
    assert "ConnectTimeout" in response.json()["detail"]


@pytest.mark.xfail(strict=True, reason="BUG: ET.fromstring is unguarded, so a malformed arXiv reply is a 500, not a 502")
def test_search_malformed_xml_is_a_502(raw_client, external):
    external.respond(ARXIV_API, text="<html>rate limited")
    response = raw_client.get("/api/search", params={"q": "x"})
    assert response.status_code == 502
    assert "arXiv" in response.json()["detail"]


@pytest.mark.xfail(strict=True, reason="BUG: _parse_entry assumes every field exists, so one incomplete entry fails the whole search")
def test_search_skips_an_incomplete_entry(raw_client, external):
    incomplete = "<entry><id>http://arxiv.org/abs/2401.1v1</id></entry>"
    external.respond(ARXIV_API, text=atom_feed(incomplete, atom_entry()))
    response = raw_client.get("/api/search", params={"q": "x"})
    assert response.status_code == 200
    assert [p["title"] for p in response.json()] == ["A Paper"]


# ---------- saving arXiv papers ----------


def test_save_downloads_pdf_and_extracts_text(client, external, storage):
    data = make_pdf()
    external.respond(ARXIV_PDF, content=data)
    response = client.post("/api/papers", json=search_result())
    assert response.status_code == 200
    paper = response.json()
    assert paper["source"] == "arxiv"
    assert paper["external_id"] == "2401.00001"
    assert paper["authors"] == ["A. Author", "B. Author"]
    assert paper["text_status"] == "ready"
    assert paper["text_chars"] > 500
    assert paper["text_error"] is None
    assert paper["pdf_url"] == f"/api/papers/{paper['id']}/pdf"
    assert (storage.pdf_dir / "arxiv-2401.00001.pdf").read_bytes() == data
    assert word_chars(LONG_TEXT)[:40] in word_chars(db.get_full_text(paper["id"]))


def test_saving_twice_returns_the_same_paper_without_downloading(client, external):
    external.respond(ARXIV_PDF, content=make_pdf())
    first = client.post("/api/papers", json=search_result()).json()
    second = client.post("/api/papers", json=search_result()).json()
    assert second["id"] == first["id"]
    assert len(external.requests) == 1
    assert len(client.get("/api/papers").json()) == 1


def test_save_is_safe_against_a_concurrent_save(client, external):
    def other_request_wins(request):
        seed_paper(source="arxiv", external_id="2401.00001", title="Saved by the other request")
        return httpx.Response(200, content=make_pdf())

    external.handle(ARXIV_PDF, other_request_wins)
    response = client.post("/api/papers", json=search_result())
    assert response.status_code == 200
    assert response.json()["title"] == "Saved by the other request"
    assert len(client.get("/api/papers").json()) == 1


@pytest.mark.parametrize(
    "configure, error",
    [
        (lambda e: e.respond(ARXIV_PDF, status=404), "HTTPStatusError"),
        (lambda e: e.fail(ARXIV_PDF, httpx.ReadTimeout), "ReadTimeout"),
        (lambda e: e.respond(ARXIV_PDF, text="<html>nope</html>"), "not a PDF"),
    ],
)
def test_failed_download_still_saves_the_paper_without_text(client, external, storage, configure, error):
    configure(external)
    paper = client.post("/api/papers", json=search_result()).json()
    assert paper["text_status"] == "failed"
    assert error in paper["text_error"]
    assert paper["pdf_url"] is None
    assert paper["text_chars"] is None
    assert stored_pdfs(storage) == []


def test_scanned_pdf_is_stored_but_marked_without_text(client, external, storage):
    external.respond(ARXIV_PDF, content=make_pdf(None))
    paper = client.post("/api/papers", json=search_result()).json()
    assert paper["text_status"] == "failed"
    assert "no extractable text" in paper["text_error"]
    assert client.get(paper["pdf_url"]).status_code == 200
    assert len(stored_pdfs(storage)) == 1


@pytest.mark.parametrize(
    "external_id",
    ["../../evil", "/etc/passwd", "a/b\\c", "..", "cs/0112017"],
)
def test_external_id_cannot_escape_the_pdf_folder(client, external, storage, external_id):
    external.respond(ARXIV_PDF, content=make_pdf())
    body = search_result(external_id=external_id, pdf_url="https://arxiv.org/pdf/x")
    assert client.post("/api/papers", json=body).status_code == 200
    files = stored_pdfs(storage)
    assert len(files) == 1
    assert files[0].parent == storage.pdf_dir
    assert files[0].name.startswith("arxiv-")


@pytest.mark.parametrize("missing", ["external_id", "title", "authors", "pdf_url"])
def test_save_requires_core_fields(client, missing):
    body = search_result()
    del body[missing]
    assert client.post("/api/papers", json=body).status_code == 422


@pytest.mark.parametrize("field, value", [("year", "soon"), ("authors", "just one"), ("title", None)])
def test_save_validates_field_types(client, external, field, value):
    assert client.post("/api/papers", json=search_result(**{field: value})).status_code == 422
    assert external.requests == []


def test_save_accepts_null_optional_fields(client, external):
    external.respond(ARXIV_PDF, content=make_pdf())
    body = search_result(year=None, abstract=None, url=None)
    paper = client.post("/api/papers", json=body).json()
    assert (paper["year"], paper["abstract"], paper["url"]) == (None, None, None)


def test_title_with_sql_is_stored_literally(client, external):
    external.respond(ARXIV_PDF, content=make_pdf())
    title = "x'); DROP TABLE papers; --"
    assert client.post("/api/papers", json=search_result(title=title)).json()["title"] == title
    assert len(client.get("/api/papers").json()) == 1


@pytest.mark.xfail(strict=True, reason="BUG: httpx.InvalidURL is not an httpx.HTTPError, so pdf.download lets it escape as a 500")
def test_save_with_a_malformed_pdf_url_is_saved_without_text(raw_client):
    body = search_result(pdf_url="http://arxiv.org:notaport/x.pdf")
    response = raw_client.post("/api/papers", json=body)
    assert response.status_code == 200
    paper = response.json()
    assert paper["text_status"] == "failed"
    assert "PDF download failed" in paper["text_error"]
    assert paper["pdf_url"] is None


@pytest.mark.xfail(strict=True, reason="SECURITY: pdf_url comes from the client and is fetched as-is, so the server can be aimed at any host (SSRF)")
def test_save_does_not_fetch_arbitrary_hosts(raw_client, external):
    external.respond("169.254.169.254", content=make_pdf())
    raw_client.post("/api/papers", json=search_result(pdf_url="http://169.254.169.254/latest/meta-data"))
    assert external.requests == []


# ---------- uploads ----------


def test_upload_uses_gemini_metadata(client, gemini, storage):
    gemini.script(reply(data={"title": "Real Title", "authors": ["Ada"], "year": 2021, "abstract": "Abs"}))
    data = make_pdf()
    response = upload(client, data)
    assert response.status_code == 200
    paper = response.json()
    assert paper["source"] == "upload"
    assert paper["external_id"] is None
    assert (paper["title"], paper["authors"], paper["year"], paper["abstract"]) == ("Real Title", ["Ada"], 2021, "Abs")
    assert paper["text_status"] == "ready"
    assert paper["text_error"] is None
    assert paper["metadata_warning"] is None
    assert client.get(paper["pdf_url"]).content == data
    assert len(stored_pdfs(storage)) == 1


def test_upload_falls_back_to_pdf_metadata_without_a_key(client):
    data = make_pdf(metadata={"title": "Embedded", "author": "Ada, Alan", "creationDate": "D:20190101"})
    paper = upload(client, data).json()
    assert (paper["title"], paper["authors"], paper["year"]) == ("Embedded", ["Ada", "Alan"], 2019)
    assert paper["text_status"] == "ready"
    assert "GEMINI_API_KEY" in paper["metadata_warning"]


def test_upload_falls_back_when_gemini_is_overloaded(client, gemini):
    gemini.script(api_error(503))
    paper = upload(client, make_pdf(), filename="my_great_paper.pdf").json()
    assert paper["title"] == "my great paper"
    assert "temporarily unavailable" in paper["metadata_warning"]


def test_upload_of_a_scanned_pdf_keeps_the_file_and_skips_gemini(client, gemini, storage):
    paper = upload(client, make_pdf(None), filename="scan.pdf").json()
    assert paper["text_status"] == "failed"
    assert "no extractable text" in paper["text_error"]
    assert paper["title"] == "scan"
    assert paper["metadata_warning"] is None
    assert gemini.calls == []
    assert len(stored_pdfs(storage)) == 1


@pytest.mark.parametrize("data", [b"", b"plain text", b"<html></html>", b" %PDF-1.7"])
def test_upload_rejects_non_pdf_content(client, storage, data):
    response = upload(client, data)
    assert response.status_code == 400
    assert response.json()["detail"] == "Please upload a PDF file."
    assert stored_pdfs(storage) == []
    assert client.get("/api/papers").json() == []


def test_upload_checks_content_not_the_filename(client, storage):
    assert upload(client, b"plain text", filename="looks-fine.pdf").status_code == 400
    assert upload(client, make_pdf(), filename="odd-name.txt").status_code == 200


def test_upload_rejects_oversized_files(client, storage, monkeypatch):
    data = make_pdf()
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", len(data) - 1)
    response = upload(client, data)
    assert response.status_code == 413
    assert stored_pdfs(storage) == []


def test_upload_at_exactly_the_size_limit_is_accepted(client, monkeypatch):
    data = make_pdf()
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", len(data))
    paper = upload(client, data).json()
    assert client.get(paper["pdf_url"]).content == data
    assert [p["id"] for p in client.get("/api/papers").json()] == [paper["id"]]


def test_upload_requires_a_file(client):
    assert client.post("/api/upload").status_code == 422


def test_upload_filename_cannot_choose_the_storage_path(client, storage):
    assert upload(client, make_pdf(), filename="../../../evil.pdf").status_code == 200
    files = stored_pdfs(storage)
    assert len(files) == 1
    assert files[0].name.startswith("upload-")
    assert not (storage.data_dir.parent / "evil.pdf").exists()


@pytest.mark.xfail(strict=True, reason="BUG: metadata.fallback reopens the unreadable PDF with no error handling, so a corrupt upload is a 500")
def test_corrupt_pdf_upload_is_handled(raw_client):
    response = upload(raw_client, b"%PDF-1.7 corrupt", filename="broken.pdf")
    assert response.status_code == 200
    paper = response.json()
    assert paper["title"] == "broken"
    assert paper["text_status"] == "failed"
    assert paper["text_error"] == "Could not read PDF"
    assert [p["id"] for p in raw_client.get("/api/papers").json()] == [paper["id"]]


@pytest.mark.xfail(strict=True, reason="BUG: the file is written before processing, so a failed upload leaves an orphan PDF behind")
def test_failed_upload_leaves_no_file(raw_client, storage):
    upload(raw_client, b"%PDF-1.7 corrupt")
    owned = {Path(db.get_pdf_path(p["id"])) for p in raw_client.get("/api/papers").json()}
    assert set(stored_pdfs(storage)) == owned  # holds for "rejected, no file" and for "kept, with a library row"


@pytest.mark.xfail(strict=True, reason="BUG: a network error reaching Gemini is not an LLMError, so the documented metadata fallback never runs")
def test_upload_falls_back_when_gemini_is_unreachable(raw_client, gemini):
    gemini.script(httpx.ConnectError("network unreachable"))
    assert upload(raw_client, make_pdf()).status_code == 200


# ---------- reading and listing ----------


def test_list_is_newest_first_and_never_exposes_full_text(client):
    first, second = seed_paper(title="First"), seed_paper(title="Second", pdf_path="/secret.pdf")
    response = client.get("/api/papers")
    assert [p["id"] for p in response.json()] == [second, first]
    assert "full_text" not in response.text
    assert "pdf_path" not in response.text
    assert LONG_TEXT not in response.text
    one = client.get(f"/api/papers/{second}")
    assert one.json()["title"] == "Second"
    assert "full_text" not in one.text
    assert "pdf_path" not in one.text


def test_get_missing_paper(client):
    response = client.get("/api/papers/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Paper not found"


@pytest.mark.parametrize("paper_id", ["abc", "1.5"])
def test_non_integer_id_is_rejected(client, paper_id):
    assert client.get(f"/api/papers/{paper_id}").status_code == 422


@pytest.mark.parametrize("paper_id", [0, -1])
def test_out_of_range_id_is_not_found(client, paper_id):
    assert client.get(f"/api/papers/{paper_id}").status_code == 404


@pytest.mark.xfail(strict=True, reason="BUG: an id over 2^63-1 overflows SQLite's integer binding and becomes a 500")
def test_huge_id_is_not_found(raw_client):
    assert raw_client.get(f"/api/papers/{2**63}").status_code == 404


def test_pdf_endpoint_returns_the_file(client, storage):
    path = storage.pdf_dir / "x.pdf"
    path.write_bytes(b"%PDF-1.7 content")
    response = client.get(f"/api/papers/{seed_paper(pdf_path=str(path))}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.7 content"


def test_pdf_endpoint_without_a_stored_pdf(client):
    assert client.get(f"/api/papers/{seed_paper()}/pdf").status_code == 404
    assert client.get("/api/papers/999/pdf").status_code == 404


@pytest.mark.xfail(strict=True, reason="BUG: a stored path whose file is gone makes FileResponse raise, giving a 500 instead of a 404")
def test_pdf_endpoint_when_the_file_has_vanished(raw_client, storage):
    paper_id = seed_paper(pdf_path=str(storage.pdf_dir / "gone.pdf"))
    assert raw_client.get(f"/api/papers/{paper_id}/pdf").status_code == 404


# ---------- deleting ----------


def test_delete_removes_paper_and_file(client, storage):
    path = storage.pdf_dir / "x.pdf"
    path.write_bytes(b"%PDF")
    paper_id = seed_paper(pdf_path=str(path))
    response = client.delete(f"/api/papers/{paper_id}")
    assert response.status_code == 200
    assert response.json() == {"deleted": paper_id}
    assert not path.exists()
    assert client.get(f"/api/papers/{paper_id}").status_code == 404
    assert client.get(f"/api/papers/{paper_id}/pdf").status_code == 404


def test_delete_only_touches_that_paper(client):
    keep, remove = seed_paper(title="Keep"), seed_paper(title="Remove")
    client.delete(f"/api/papers/{remove}")
    assert [p["id"] for p in client.get("/api/papers").json()] == [keep]


def test_delete_missing_paper(client):
    assert client.delete("/api/papers/999").status_code == 404


def test_delete_paper_without_a_pdf(client, storage):
    bystander = storage.pdf_dir / "other-paper.pdf"
    bystander.write_bytes(b"%PDF")
    paper_id = seed_paper()
    assert client.delete(f"/api/papers/{paper_id}").json() == {"deleted": paper_id}
    assert client.get(f"/api/papers/{paper_id}").status_code == 404
    assert bystander.exists()


def test_delete_tolerates_an_already_missing_file(client, storage):
    paper_id = seed_paper(pdf_path=str(storage.pdf_dir / "gone.pdf"))
    assert client.delete(f"/api/papers/{paper_id}").json() == {"deleted": paper_id}
    assert client.get(f"/api/papers/{paper_id}").status_code == 404


@pytest.mark.parametrize("relative", ["outside.pdf", "pdfs-sibling/x.pdf"])
def test_delete_never_removes_files_outside_the_pdf_folder(client, storage, relative):
    path = storage.data_dir / relative
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"precious")
    paper_id = seed_paper(pdf_path=str(path))
    assert client.delete(f"/api/papers/{paper_id}").status_code == 200
    assert path.read_bytes() == b"precious"


def test_delete_ignores_a_traversal_path(client, storage):
    victim = storage.data_dir / "victim.txt"
    victim.write_text("precious")
    client.delete(f"/api/papers/{seed_paper(pdf_path=str(storage.pdf_dir / '..' / 'victim.txt'))}")
    assert victim.exists()


def test_deleted_arxiv_paper_can_be_saved_again(client, external):
    external.respond(ARXIV_PDF, content=make_pdf())
    paper = client.post("/api/papers", json=search_result()).json()
    client.delete(f"/api/papers/{paper['id']}")
    saved = client.post("/api/papers", json=search_result()).json()
    assert saved["text_status"] == "ready"
    assert client.get(saved["pdf_url"]).status_code == 200


# ---------- summaries ----------


def test_summarize_generates_and_stores(client, gemini):
    gemini.script(reply("## Problem\nA summary"))
    paper_id = seed_paper()
    response = client.post(f"/api/papers/{paper_id}/summary")
    assert response.status_code == 200
    assert response.json() == {"summary": "## Problem\nA summary", "cached": False, "truncated": False}
    assert client.get(f"/api/papers/{paper_id}").json()["summary"] == "## Problem\nA summary"
    assert LONG_TEXT in gemini.last_prompt


def test_summarize_uses_the_cache(client, gemini):
    paper_id = seed_paper(summary="Stored summary")
    assert client.post(f"/api/papers/{paper_id}/summary").json() == {
        "summary": "Stored summary",
        "cached": True,
        "truncated": False,
    }
    assert gemini.calls == []


def test_refresh_replaces_the_stored_summary(client, gemini):
    gemini.script(reply("New summary"))
    paper_id = seed_paper(summary="Old summary")
    body = client.post(f"/api/papers/{paper_id}/summary", params={"refresh": "true"}).json()
    assert (body["summary"], body["cached"]) == ("New summary", False)
    assert client.get(f"/api/papers/{paper_id}").json()["summary"] == "New summary"


def test_failed_refresh_keeps_the_old_summary(client, gemini):
    gemini.script(api_error(429))
    paper_id = seed_paper(summary="Old summary")
    response = client.post(f"/api/papers/{paper_id}/summary", params={"refresh": "true"})
    assert response.status_code == 503
    assert "rate limit" in response.json()["detail"]
    assert client.get(f"/api/papers/{paper_id}").json()["summary"] == "Old summary"


def test_summarize_without_a_key_is_a_503(client):
    response = client.post(f"/api/papers/{seed_paper()}/summary")
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_summarize_missing_paper(client):
    assert client.post("/api/papers/999/summary").status_code == 404


def test_summarize_refuses_text_marked_failed(client, gemini):
    assert client.post(f"/api/papers/{seed_paper(text_status='failed')}/summary").status_code == 409
    assert gemini.calls == []


def test_summarize_refuses_empty_text_marked_ready(client):
    assert client.post(f"/api/papers/{seed_paper(full_text='')}/summary").status_code == 409


def test_summarize_reports_truncation(client, gemini):
    paper_id = seed_paper(full_text="x" * (analysis.MAX_TEXT_CHARS + 1))
    assert client.post(f"/api/papers/{paper_id}/summary").json()["truncated"] is True
    assert client.post(f"/api/papers/{paper_id}/summary").json() == {
        "summary": "Fake Gemini answer",
        "cached": True,
        "truncated": True,
    }


@pytest.mark.xfail(strict=True, reason="BUG: the cached branch measures the raw text but a fresh summary measures it after stripping references")
def test_cached_truncation_flag_matches_the_fresh_one(client, gemini):
    body = "x" * (analysis.MAX_TEXT_CHARS - 100)
    refs = "\n".join(f"Ref {i} 2020" for i in range(30_000))
    paper_id = seed_paper(full_text=f"{body}\nReferences\n{refs}\n")
    fresh = client.post(f"/api/papers/{paper_id}/summary").json()
    cached = client.post(f"/api/papers/{paper_id}/summary").json()
    assert fresh["cached"] is False and cached["cached"] is True
    assert cached["truncated"] == fresh["truncated"]


@pytest.mark.xfail(strict=True, reason="BUG: a network error reaching Gemini is uncaught, so the user gets a bare 500 instead of a readable 503")
def test_summarize_when_gemini_is_unreachable_is_a_503(raw_client, gemini):
    gemini.script(httpx.ConnectError("network unreachable"))
    assert raw_client.post(f"/api/papers/{seed_paper()}/summary").status_code == 503


# ---------- questions ----------


def ask(client, paper_id, question):
    return client.post(f"/api/papers/{paper_id}/ask", json={"question": question})


def test_ask_answers_from_the_full_text(client, gemini):
    gemini.script(reply("It uses GNNs."))
    response = ask(client, seed_paper(), "What method?")
    assert response.status_code == 200
    assert response.json() == {"question": "What method?", "answer": "It uses GNNs.", "truncated": False}
    assert LONG_TEXT in gemini.last_prompt
    assert gemini.last_prompt.endswith("Question: What method?")


def test_ask_strips_the_question_before_sending(client, gemini):
    ask(client, seed_paper(), "  Why?  \n")
    assert gemini.last_prompt.endswith("Question: Why?")


def test_ask_stores_nothing(client, gemini):
    paper_id = seed_paper()
    before = client.get(f"/api/papers/{paper_id}").json()
    ask(client, paper_id, "Why?")
    assert client.get(f"/api/papers/{paper_id}").json() == before


def test_ask_reports_truncation(client, gemini):
    paper_id = seed_paper(full_text="x" * (analysis.MAX_TEXT_CHARS + 1))
    assert ask(client, paper_id, "Why?").json()["truncated"] is True


def test_ask_accepts_the_longest_allowed_question(client, gemini):
    question = "q" * 1000
    assert ask(client, seed_paper(), question).json()["question"] == question
    assert gemini.last_prompt.endswith(f"Question: {question}")


@pytest.mark.parametrize("question", ["", "q" * 1001, None, 5])
def test_ask_validates_the_question(client, gemini, question):
    assert ask(client, seed_paper(), question).status_code == 422
    assert gemini.calls == []


@pytest.mark.parametrize("kwargs", [{"json": {}}, {"content": b"not json"}])
def test_ask_rejects_a_bad_body(client, kwargs):
    assert client.post(f"/api/papers/{seed_paper()}/ask", **kwargs).status_code == 422


def test_ask_missing_paper(client):
    assert ask(client, 999, "Why?").status_code == 404


def test_ask_reports_gemini_failure_as_a_503(client, gemini):
    gemini.script(api_error(503))
    response = ask(client, seed_paper(), "Why?")
    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


@pytest.mark.xfail(strict=True, reason="BUG: min_length is checked before strip(), so a blank question reaches Gemini and spends quota")
def test_ask_rejects_a_blank_question(client, gemini):
    assert ask(client, seed_paper(), "   ").status_code == 422
    assert gemini.calls == []


# ---------- graph ----------


def test_graph_endpoint(client, external):
    paper_id = seed_paper(title="Only paper")
    external.respond("api.openalex.org", json={"results": []})
    response = client.get("/api/graph")
    assert response.status_code == 200
    body = response.json()
    assert [n["id"] for n in body["nodes"]] == [paper_id]
    assert body["edges"] == []


# ---------- end to end through the API ----------


def test_search_save_summarize_ask_remove(client, external, gemini, storage):
    external.respond(ARXIV_API, text=atom_feed(atom_entry()))
    external.respond(ARXIV_PDF, content=make_pdf())
    gemini.script(reply("The summary"), reply("The answer"))

    result = client.get("/api/search", params={"q": "paper"}).json()[0]
    paper = client.post("/api/papers", json=result).json()
    assert paper["title"] == "A Paper"
    assert client.post(f"/api/papers/{paper['id']}/summary").json()["summary"] == "The summary"
    assert ask(client, paper["id"], "Why?").json()["answer"] == "The answer"
    assert client.delete(f"/api/papers/{paper['id']}").status_code == 200
    assert client.get("/api/papers").json() == []
    assert stored_pdfs(storage) == []


