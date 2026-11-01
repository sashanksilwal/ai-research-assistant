import importlib
import json

import httpx
import pytest

from app import citations, db
from helpers import assert_bounded_timeout, recorded_json, run, seed_paper

OPENALEX = "api.openalex.org"
S2 = "api.semanticscholar.org"


def s2_ref(arxiv=None, title=None):
    """Shaped like tests/fixtures/recorded/s2_batch.json, where unlinked entries have null ids."""
    if arxiv:
        return {"paperId": "abc", "externalIds": {"ArXiv": arxiv, "CorpusId": 1}, "title": title}
    return {"paperId": None, "externalIds": None, "title": title}


def s2_work(*refs):
    return {"references": list(refs)}


def arxiv_paper(external_id, title=None):
    return seed_paper(source="arxiv", external_id=external_id, title=title or f"Paper {external_id}")


def openalex_finds_nothing(external):
    external.respond(OPENALEX, json={"meta": {"count": 0}, "results": [], "group_by": []})


def edges(graph):
    return [(e["from"], e["to"]) for e in graph["edges"]]


def test_empty_library_makes_no_requests(external):
    assert run(citations.build_graph()) == {"nodes": [], "edges": []}
    assert external.requests == []


def test_node_shape():
    paper_id = seed_paper(title="T", year=2020)
    db.set_openalex(paper_id, "not_found", None, [])
    assert run(citations.build_graph())["nodes"] == [
        {"id": paper_id, "title": "T", "year": 2020, "source": "upload", "matched": False}
    ]


def test_semantic_scholar_batch_request_shape(external):
    arxiv_paper("1"), arxiv_paper("2")
    openalex_finds_nothing(external)
    external.respond(S2, json=[None, None])
    run(citations.build_graph())
    request = external.hits(S2)[0]
    assert request.method == "POST"
    assert b'"arXiv:1"' in request.content and b'"arXiv:2"' in request.content
    assert len(external.hits(S2)) == 1


def test_reference_outside_the_library_is_ignored(external):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.respond(S2, json=[s2_work(s2_ref(arxiv="9", title="Unknown"))])
    assert edges(run(citations.build_graph())) == []


def test_unknown_paper_is_not_found_at_semantic_scholar(external):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.respond(S2, json=[None])
    graph = run(citations.build_graph())
    assert graph["nodes"][0]["matched"] is False
    assert db.papers_needing_s2() == []


def test_work_with_null_references_is_ok(external):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.respond(S2, json=[{"references": None}])
    assert run(citations.build_graph())["nodes"][0]["matched"] is True


def test_openalex_tolerates_a_result_without_a_title(external):
    seed_paper(title="Graph Neural Networks")
    external.respond(OPENALEX, json={"results": [{"id": "x", "title": None}]})
    assert run(citations.build_graph())["nodes"][0]["matched"] is False


def test_same_edge_from_both_sources_appears_once(external):
    a, b = arxiv_paper("1"), arxiv_paper("2")
    db.set_openalex(a, "ok", "W1", ["W2"])
    db.set_openalex(b, "ok", "W2", [])
    external.respond(S2, json=[s2_work(s2_ref(arxiv="2")), s2_work()])
    assert edges(run(citations.build_graph())) == [(a, b)]


def test_self_citation_is_dropped():
    a = seed_paper()
    db.set_openalex(a, "ok", "W1", ["W1"])
    assert edges(run(citations.build_graph())) == []


def test_mutual_citations_keep_both_directions():
    a, b = seed_paper(), seed_paper()
    db.set_openalex(a, "ok", "W1", ["W2"])
    db.set_openalex(b, "ok", "W2", ["W1"])
    assert edges(run(citations.build_graph())) == [(a, b), (b, a)]


def test_finished_lookups_are_cached(external):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.respond(S2, json=[s2_work()])
    run(citations.build_graph())
    count = len(external.requests)
    run(citations.build_graph())
    assert len(external.requests) == count


def test_openalex_error_is_retried_on_the_next_load(external):
    seed_paper(title="Paper")
    external.respond(OPENALEX, status=500)
    assert db.papers_needing_openalex() != []
    run(citations.build_graph())
    assert db.papers_for_graph()[0]["openalex_status"] == "error"
    openalex_finds_nothing(external)
    run(citations.build_graph())
    assert db.papers_for_graph()[0]["openalex_status"] == "not_found"


def test_openalex_network_failure_does_not_break_the_graph(external):
    seed_paper(title="Paper")
    external.fail(OPENALEX)
    assert len(run(citations.build_graph())["nodes"]) == 1


def test_openalex_requests_are_paced(external, sleeps):
    seed_paper(), seed_paper()
    openalex_finds_nothing(external)
    run(citations.build_graph())
    assert sleeps == [0.2, 0.2]


def test_semantic_scholar_429_backs_off_then_succeeds(external, sleeps):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.sequence(S2, [(429, {}), (429, {}), (200, {"json": [s2_work()]})])
    graph = run(citations.build_graph())
    assert len(external.hits(S2)) == 3
    assert [s for s in sleeps if s >= 1] == [5, 10]
    assert graph["nodes"][0]["matched"] is True


def test_semantic_scholar_giving_up_marks_error_for_retry(external):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.respond(S2, status=429)
    graph = run(citations.build_graph())
    assert len(external.hits(S2)) == 4
    assert graph["edges"] == []
    assert db.papers_for_graph()[0]["s2_status"] == "error"
    assert len(db.papers_needing_s2()) == 1


def test_semantic_scholar_network_failure_is_retried_then_marked_error(external):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.fail(S2)
    run(citations.build_graph())
    assert len(external.hits(S2)) == 4
    assert db.papers_for_graph()[0]["s2_status"] == "error"


def test_uploads_are_not_sent_to_semantic_scholar(external):
    seed_paper(title="Upload")
    openalex_finds_nothing(external)
    run(citations.build_graph())
    assert external.hits(S2) == []


def openalex_api(works):
    """OpenAlex's request contract: `search` picks works, `select` limits their fields, and an unknown
    parameter is rejected with a 400."""

    def handler(request):
        params = request.url.params
        if set(params) - {"search", "select", "per-page", "mailto"}:
            return httpx.Response(400, json={"error": "Invalid query parameters"})
        fields = params.get("select", "").split(",")
        found = [work for work in works if work["title"] == params.get("search")]
        return httpx.Response(200, json={"meta": {}, "group_by": [], "results": [
            {k: v for k, v in work.items() if k in fields} for work in found
        ]})

    return handler


def s2_api(works_by_id):
    """The batch endpoint's contract: `ids` in the body, and references only when `fields` asks for them."""

    def handler(request):
        body = json.loads(request.content)
        if "ids" not in body:
            return httpx.Response(400, json={"error": "Unrecognized field"})
        fields = request.url.params.get("fields", "").split(",")
        keep = {name.removeprefix("references.") for name in fields if name.startswith("references.")}
        works = [works_by_id.get(i) for i in body["ids"]]
        return httpx.Response(200, json=[
            work and {"references": [{k: v for k, v in r.items() if k in keep} for r in work["references"]] if keep else None}
            for work in works
        ])

    return handler


def test_openalex_request_gets_the_fields_the_graph_needs(external):
    a, b = seed_paper(title="First Paper"), seed_paper(title="Second Paper")
    external.handle(OPENALEX, openalex_api([
        {"id": "https://openalex.org/W1", "title": "First Paper", "referenced_works": ["https://openalex.org/W2"], "abstract": "x"},
        {"id": "https://openalex.org/W2", "title": "Second Paper", "referenced_works": [], "abstract": "x"},
    ]))
    assert edges(run(citations.build_graph())) == [(a, b)]


def test_semantic_scholar_request_gets_the_fields_the_graph_needs(external):
    known = arxiv_paper("1706.03762", "Attention Is All You Need")
    by_id = arxiv_paper("1705.04304", "Title differs from the record")
    refs = recorded_json("s2_batch.json")[0]["references"]
    by_title = seed_paper(title=next(r["title"] for r in refs if not r.get("externalIds")))
    openalex_finds_nothing(external)
    external.handle(S2, s2_api({"arXiv:1706.03762": recorded_json("s2_batch.json")[0]}))
    assert set(edges(run(citations.build_graph()))) == {(known, by_id), (known, by_title)}


def test_contact_email_is_read_from_the_documented_setting(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "contact@example.invalid")
    try:
        assert importlib.reload(citations).CONTACT_EMAIL == "contact@example.invalid"
    finally:
        monkeypatch.delenv("OPENALEX_EMAIL")
        importlib.reload(citations)


def test_no_contact_email_is_sent_by_default(external):
    seed_paper(title="Upload")
    openalex_finds_nothing(external)
    run(citations.build_graph())
    assert "mailto" not in external.hits(OPENALEX)[0].url.params


def test_contact_email_is_sent_only_when_configured(external, monkeypatch):
    monkeypatch.setattr(citations, "CONTACT_EMAIL", "contact@example.invalid")
    seed_paper(title="Upload")
    openalex_finds_nothing(external)
    run(citations.build_graph())
    assert external.hits(OPENALEX)[0].url.params["mailto"] == "contact@example.invalid"


def test_all_clients_set_a_timeout(external):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.respond(S2, json=[None])
    run(citations.build_graph())
    assert {r.url.host for r in external.requests} == {OPENALEX, S2}
    for request in external.requests:
        assert_bounded_timeout(request)


def test_paper_removed_from_library_loses_its_edges():
    a, b = seed_paper(), seed_paper()
    db.set_openalex(a, "ok", "W1", ["W2"])
    db.set_openalex(b, "ok", "W2", [])
    db.delete_paper(b)
    assert edges(run(citations.build_graph())) == []


@pytest.mark.xfail(strict=True, reason="BUG: titles with no Latin letters normalize to '', which also matches references that have no title")
def test_title_less_reference_does_not_link_to_a_non_latin_title():
    citing = seed_paper(title="English title")
    chinese = seed_paper(title="深度学习综述")
    db.set_openalex(citing, "ok", None, [])
    db.set_openalex(chinese, "ok", None, [])
    db.set_s2(citing, "ok", [{"arxiv": None, "title": None}])
    assert edges(run(citations.build_graph())) == []


@pytest.mark.xfail(strict=True, reason="BUG: a non-Latin title has similarity 1.0 with any OpenAlex work whose title normalizes to ''")
def test_non_latin_title_does_not_match_an_unrelated_openalex_work(external):
    seed_paper(title="深度学习综述")
    external.respond(OPENALEX, json={"results": [{"id": "https://openalex.org/W1", "title": "機械学習"}]})
    run(citations.build_graph())
    assert db.papers_for_graph()[0]["openalex_status"] == "not_found"


@pytest.mark.xfail(strict=True, reason="BUG: resp.json() is unguarded, so a 200 with a non-JSON body crashes GET /api/graph")
@pytest.mark.parametrize("host", [OPENALEX, S2])
def test_invalid_json_from_a_citation_service_does_not_break_the_graph(external, raw_client, host):
    arxiv_paper("1")
    openalex_finds_nothing(external)
    external.respond(S2, json=[None])
    external.respond(host, text="<html>maintenance</html>")
    response = raw_client.get("/api/graph")
    assert response.status_code == 200
    assert len(response.json()["nodes"]) == 1
