"""The app against responses recorded from the real services, and the fakes against those recordings."""
import copy
import re
import xml.etree.ElementTree as ET

from google.genai import types

from app import arxiv, citations, db, llm
from app.metadata import PaperMetadata
from conftest import CDN_FILES, ROOT
from helpers import (
    VENDOR,
    atom_entry,
    atom_feed,
    recorded_json,
    recorded_text,
    run,
    seed_paper,
)

ARXIV_API = "export.arxiv.org"
OPENALEX = "api.openalex.org"
S2 = "api.semanticscholar.org"
ATOM = "{http://www.w3.org/2005/Atom}"


def entry_shape(entry):
    return {child.tag for child in entry}


def test_recorded_arxiv_search_parses_every_field(external):
    external.respond(ARXIV_API, text=recorded_text("arxiv_search.xml"))
    papers = run(arxiv.search("attention transformer"))
    assert [p["external_id"] for p in papers] == ["2209.15001", "2605.26355", "2309.01692"]
    first = papers[0]
    assert first["title"] == "Dilated Neighborhood Attention Transformer"
    assert first["authors"] == ["Ali Hassani", "Humphrey Shi"]
    assert first["year"] == 2022  # published, not the 2023 <updated> date
    assert first["url"] == "https://arxiv.org/abs/2209.15001v3"
    assert first["pdf_url"] == "https://arxiv.org/pdf/2209.15001v3"
    assert first["abstract"].startswith("Transformers are quickly becoming")
    assert "\n" not in first["abstract"]
    assert all(p["title"] != "arXiv Query" and not p["title"].startswith("arXiv Query") for p in papers)


def test_recorded_bad_query_is_an_empty_feed_not_an_error(external, client):
    external.respond(ARXIV_API, text=recorded_text("arxiv_error.xml"))
    response = client.get("/api/search", params={"q": "badprefix"})
    assert response.status_code == 200
    assert response.json() == []


def test_fake_arxiv_entry_has_the_recorded_shape():
    recorded = ET.fromstring(recorded_text("arxiv_search.xml")).find(f"{ATOM}entry")
    fake = ET.fromstring(atom_feed(atom_entry())).find(f"{ATOM}entry")
    assert entry_shape(fake) == entry_shape(recorded)
    assert [link.attrib.keys() for link in fake.findall(f"{ATOM}link")] == [
        link.attrib.keys() for link in recorded.findall(f"{ATOM}link")
    ]


def test_fake_arxiv_feed_has_the_recorded_namespaces():
    recorded = recorded_text("arxiv_search.xml")
    assert all(uri in recorded and uri in atom_feed() for uri in re.findall(r'xmlns[^=]*="([^"]+)"', atom_feed()))


def attention_library():
    """Library papers that the recorded Semantic Scholar reply cites, in its order: known id, unknown id."""
    known = seed_paper(source="arxiv", external_id="1706.03762", title="Attention Is All You Need")
    unknown = seed_paper(source="arxiv", external_id="0000.00000", title="Paper Semantic Scholar has never seen")
    for paper_id in (known, unknown):
        db.set_openalex(paper_id, "not_found", None, [])
    return known, unknown


def test_recorded_s2_batch_builds_edges_by_arxiv_id(external):
    known, unknown = attention_library()
    cited = seed_paper(source="arxiv", external_id="1705.04304", title="Title differs from the record")
    db.set_openalex(cited, "not_found", None, [])
    external.respond(S2, json=recorded_json("s2_batch.json") + [None])
    graph = run(citations.build_graph())
    assert [(e["from"], e["to"]) for e in graph["edges"]] == [(known, cited)]
    matched = {n["id"]: n["matched"] for n in graph["nodes"]}
    assert matched == {known: True, unknown: False, cited: False}


def test_recorded_s2_batch_links_uploads_by_title_when_no_arxiv_id(external):
    refs = recorded_json("s2_batch.json")[0]["references"]
    title = next(r["title"] for r in refs if not (r.get("externalIds") or {}).get("ArXiv"))
    known, _ = attention_library()
    upload = seed_paper(title=title.upper() + "!")
    db.set_openalex(upload, "not_found", None, [])
    external.respond(S2, json=recorded_json("s2_batch.json"))
    assert run(citations.build_graph())["edges"] == [{"from": known, "to": upload}]


def test_recorded_s2_references_without_external_ids_are_stored_safely(external):
    known, _ = attention_library()
    external.respond(S2, json=recorded_json("s2_batch.json"))
    run(citations.build_graph())
    stored = next(p for p in db.papers_for_graph() if p["id"] == known)["s2_refs"]
    assert len(stored) == 41
    assert stored[-1]["arxiv"] is None


def test_recorded_openalex_search_picks_the_first_close_title(external):
    paper_id = seed_paper(title="Attention Is All You Need")
    cited = seed_paper(title="Library paper already matched")
    db.set_openalex(cited, "ok", "W1632114991", [])  # first id in the recorded reference list
    external.respond(OPENALEX, json=recorded_json("openalex_search.json"))
    graph = run(citations.build_graph())
    row = next(p for p in db.papers_for_graph() if p["id"] == paper_id)
    assert row["openalex_id"] == "W2626778328"  # not W7124707810, the empty duplicate later in the reply
    assert len(row["openalex_refs"]) == 28
    assert all(ref.startswith("W") and "/" not in ref for ref in row["openalex_refs"])
    assert graph["edges"] == [{"from": paper_id, "to": cited}]


def test_recorded_openalex_does_not_match_a_longer_title(external):
    seed_paper(title="Attention Is All You Need In Speech Separation Systems And Beyond The Lab")
    results = copy.deepcopy(recorded_json("openalex_search.json"))
    results["results"] = results["results"][:1]
    external.respond(OPENALEX, json=results)
    run(citations.build_graph())
    assert db.papers_for_graph()[0]["openalex_status"] == "not_found"


def test_fake_gemini_returns_real_sdk_objects(gemini, client):
    """.text and .parsed come from the SDK: a schema reply that isn't JSON leaves .parsed unset, as in production."""
    gemini.script({"candidates": [{"content": {"role": "model", "parts": [{"text": "not json"}]}}]})
    response = run(gemini.aio.models.generate_content(model="m", contents="p", config=llm._config(None, PaperMetadata)))
    assert isinstance(response, types.GenerateContentResponse)
    assert response.text == "not json"
    assert response.parsed is None


def test_every_script_on_the_page_is_vendored():
    html = (ROOT / "static" / "index.html").read_text()
    remote = set(re.findall(r'<script src="(https://[^"]+)"', html))
    assert remote == set(CDN_FILES)
    assert all((VENDOR / name).stat().st_size > 1000 for name in CDN_FILES.values())


def test_arxiv_rate_limit_without_an_atom_body_gives_a_message(external, client):
    external.respond(ARXIV_API, status=429, text="Rate exceeded.")
    response = client.get("/api/search", params={"q": "x"})
    assert response.status_code == 502
    assert "HTTP 429" in response.json()["detail"]
