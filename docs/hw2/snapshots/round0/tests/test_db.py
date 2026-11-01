import sqlite3

import pytest

from app import db
from helpers import LONG_TEXT, seed_paper


def test_init_db_is_idempotent_and_keeps_rows():
    paper_id = seed_paper()
    db.init_db()
    assert db.get_paper(paper_id)["title"] == "Seeded paper"


def test_init_db_upgrades_an_old_database(storage):
    storage.db_path.unlink()
    with sqlite3.connect(storage.db_path) as conn:
        conn.executescript(db.SCHEMA)
        conn.execute("INSERT INTO papers (source, title) VALUES ('upload', 'Old row')")
    db.init_db()
    with db.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(papers)")}
    assert set(db.ADDED_COLUMNS) <= columns
    assert db.list_papers()[0]["title"] == "Old row"


def test_insert_and_read_round_trip():
    paper_id = seed_paper(title="Ünïcode 论文", authors=["Émile", "李雷"], year=None, pdf_path="/x.pdf")
    paper = db.get_paper(paper_id)
    assert paper["title"] == "Ünïcode 论文"
    assert paper["authors"] == ["Émile", "李雷"]
    assert paper["year"] is None
    assert paper["created_at"]


def test_public_view_hides_server_side_fields():
    paper = db.get_paper(seed_paper(pdf_path="/secret/path.pdf"))
    assert "full_text" not in paper
    assert "pdf_path" not in paper
    assert paper["text_chars"] == len(LONG_TEXT)


def test_pdf_url_is_set_only_when_a_pdf_is_stored():
    with_pdf = seed_paper(pdf_path="/x.pdf")
    assert db.get_paper(with_pdf)["pdf_url"] == f"/api/papers/{with_pdf}/pdf"
    assert db.get_paper(seed_paper())["pdf_url"] is None


def test_list_is_newest_first():
    first, second = seed_paper(), seed_paper()
    assert [p["id"] for p in db.list_papers()] == [second, first]


def test_lookups_of_missing_rows():
    assert db.get_paper(999) is None
    assert db.get_pdf_path(999) is None
    assert db.get_full_text(999) is None
    assert db.get_by_external_id("nope") is None
    assert db.delete_paper(999) == (False, None)


def test_get_by_external_id():
    paper_id = seed_paper(source="arxiv", external_id="2401.1")
    assert db.get_by_external_id("2401.1")["id"] == paper_id


def test_external_id_is_unique_but_uploads_may_share_null():
    seed_paper(source="arxiv", external_id="2401.1")
    with pytest.raises(sqlite3.IntegrityError):
        seed_paper(source="arxiv", external_id="2401.1")
    seed_paper()
    seed_paper()


@pytest.mark.parametrize("fields", [{"source": "web"}, {"text_status": "pending"}])
def test_check_constraints_reject_unknown_values(fields):
    with pytest.raises(sqlite3.IntegrityError):
        seed_paper(**fields)


def test_values_are_bound_not_interpolated():
    title = "x'); DROP TABLE papers; --"
    paper_id = seed_paper(title=title)
    assert db.get_paper(paper_id)["title"] == title
    assert len(db.list_papers()) == 1


def test_set_summary():
    paper_id = seed_paper()
    db.set_summary(paper_id, "Summary")
    assert db.get_paper(paper_id)["summary"] == "Summary"


def test_delete_returns_the_stored_path():
    paper_id = seed_paper(pdf_path="/x.pdf")
    assert db.delete_paper(paper_id) == (True, "/x.pdf")
    assert db.get_paper(paper_id) is None


def test_openalex_queue_holds_new_and_errored_papers():
    new, errored, ok, not_found = seed_paper(), seed_paper(), seed_paper(), seed_paper()
    db.set_openalex(errored, "error", None, [])
    db.set_openalex(ok, "ok", "W1", [])
    db.set_openalex(not_found, "not_found", None, [])
    assert {p["id"] for p in db.papers_needing_openalex()} == {new, errored}


def test_s2_queue_holds_only_arxiv_papers_that_are_new_or_errored():
    new = seed_paper(source="arxiv", external_id="1")
    errored = seed_paper(source="arxiv", external_id="2")
    ok = seed_paper(source="arxiv", external_id="3")
    seed_paper()  # an upload has no arXiv id
    db.set_s2(errored, "error", [])
    db.set_s2(ok, "ok", [])
    assert {p["id"] for p in db.papers_needing_s2()} == {new, errored}


def test_graph_rows_decode_reference_lists():
    paper_id, untouched = seed_paper(), seed_paper()
    db.set_openalex(paper_id, "ok", "W1", ["W2"])
    db.set_s2(paper_id, "ok", [{"arxiv": "1", "title": "T"}])
    rows = {row["id"]: row for row in db.papers_for_graph()}
    assert rows[paper_id]["openalex_refs"] == ["W2"]
    assert rows[paper_id]["s2_refs"] == [{"arxiv": "1", "title": "T"}]
    assert rows[untouched]["openalex_refs"] == []
    assert rows[untouched]["s2_refs"] == []
