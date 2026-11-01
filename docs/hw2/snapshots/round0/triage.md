# Round 0 triage

Oracle: HW1 requirements (R1–R5) and the README feature list, not the current code.
Audited by the supervising agent, which read `conftest.py`, `helpers.py`, `test_api.py`, `test_arxiv.py`, `test_analysis.py` and part of `test_e2e.py` and `test_llm.py` line by line; the other modules were audited from test names. **A human sample check has not been done yet.**

## Execution

347 cases: 329 passed, 18 xfailed, 0 failed. 5 random-order seeds gave identical results, so 0 flaky.
`--runxfail` confirmed all 18 fail for the stated reason (`xfail-detail.txt`).

## Label counts (cases: 347; labels below apply to test functions)

| Label | Count | Tests |
|---|---|---|
| TEST-BUG | 0 | No test had a wrong input or expected value. |
| WEAK | 13 | `test_search_incomplete_entry_is_not_a_500`, `test_save_with_a_malformed_pdf_url_is_not_a_500` (only `!= 500`); `test_corrupt_pdf_upload_is_handled` (either of two outcomes); `test_failed_upload_leaves_no_file` (assertion sits inside an `if`, so it can pass vacuously); `test_search_malformed_xml_is_a_502` (no message check); `test_search_sets_a_timeout`, `test_download_sets_a_timeout`, `test_all_clients_set_a_timeout` (`> 0` only); `test_upload_at_exactly_the_size_limit_is_accepted`, `test_search_accepts_the_longest_allowed_query`, `test_ask_accepts_the_longest_allowed_question`, `test_delete_paper_without_a_pdf`, `test_delete_tolerates_an_already_missing_file` (status code only, state not checked) |
| MIRROR | 7 | `test_system_prompt_requires_answers_from_the_paper_only` (restates a constant); `test_same_pdf_uploaded_twice_makes_two_papers` (no requirement says this); `test_paper_block_wraps_and_reports_no_truncation` (private format); `test_model_output_passes_through_the_sanitizer`, `test_math_is_rendered_but_currency_is_left_alone`, `test_graph_shows_counts_and_builds_the_network`, `test_graph_unlinked_toggle_hides_orphans` (run against hand-written stubs of DOMPurify, KaTeX and vis-network) |
| REDUNDANT | 9 | `test_delete_twice`, `test_empty_library`, `test_search_with_no_entries_returns_empty`, `test_stored_path_never_lies_outside_the_test_folder`, `test_get_paper`, `test_search_skips_the_network_when_nothing_is_searchable`, `test_summary_is_removed_with_the_paper`, `test_graph_is_not_shadowed_by_the_paper_routes`, `test_search_reports_http_status` |
| FLAKY | 0 | |
| UNSURE → decided | 2 | SSRF is outside R1–R5, but the app is deployable and unauthenticated: kept as `APP-BUG` (security). Duplicate upload behavior is unspecified: `MIRROR`. |
| OK | remainder | |

## Bugs detected (all existing; none fixed)

| ID | Severity | Behavior | Detecting test(s) |
|---|---|---|---|
| B1 | High | Upload of a corrupt file starting with `%PDF` returns 500; `metadata.fallback` reopens it unguarded | `test_corrupt_pdf_upload_is_handled` |
| B2 | Low | That failed upload leaves an orphan file in the PDF folder | `test_failed_upload_leaves_no_file` |
| B3 | High | A network failure reaching Gemini is not an `LLMError`: summary is a 500 and the documented upload fallback never runs | `test_summarize_when_gemini_is_unreachable_is_a_503`, `test_upload_falls_back_when_gemini_is_unreachable`, `test_network_failure_becomes_a_readable_error` |
| B4 | Medium | Malformed XML from arXiv returns 500, not 502 | `test_search_malformed_xml_is_a_502` |
| B5 | Medium | One incomplete arXiv entry fails the whole search | `test_search_incomplete_entry_is_not_a_500` |
| B6 | Medium | A query over 200 characters shows "Search failed: [object Object]" | `test_too_long_search_shows_a_readable_error` |
| B7 | Low | A `pdf_url` with an invalid port returns 500 (`httpx.InvalidURL`) | `test_save_with_a_malformed_pdf_url_is_not_a_500` |
| B8 | Medium (security) | `POST /api/papers` fetches a client-supplied URL from any host (SSRF) | `test_save_does_not_fetch_arbitrary_hosts` |
| B9 | Low | A paper id of 2^63 or more returns 500, not 404 | `test_huge_id_is_not_found` |
| B10 | Medium | PDF endpoint returns 500 when the stored file is gone | `test_pdf_endpoint_when_the_file_has_vanished` |
| B11 | Medium | A 200 with non-JSON from OpenAlex or Semantic Scholar crashes `/api/graph` | `test_invalid_json_from_a_citation_service_does_not_break_the_graph` (2 cases) |
| B12 | Medium | Non-Latin titles normalize to an empty string, creating false citation edges and false OpenAlex matches | `test_title_less_reference_does_not_link_to_a_non_latin_title`, `test_non_latin_title_does_not_match_an_unrelated_openalex_work` |
| B13 | Low | A whitespace-only question reaches Gemini and spends quota | `test_ask_rejects_a_blank_question` |
| B14 | Low | Cached `truncated` flag can differ from the fresh one (measured before references are stripped) | `test_cached_truncation_flag_matches_the_fresh_one` |

## Missing, despite 100% Python coverage

1. Real `marked`, `DOMPurify` and `KaTeX` never run, so the sanitizing claim is unverified.
2. Graph interaction is untested: hover focus, title search, label limit, click-to-open. Frontend coverage is 94.6%, and most of the misses are here.
3. Remove failure, abstract expand/collapse, truncation note on answers.
4. Every fake (Atom, OpenAlex, Semantic Scholar, Gemini response object) was written from the code that reads it, so nothing checks that real services look like that.
5. No traceability from R1–R5 to tests.
6. Real multi-page paper PDFs; fixtures are single-page synthetic documents.

## Mutation (backend only, 680 mutants)

Score **73.8%** (502 killed, 178 survived) despite 100% line and branch coverage. By module: db 92.3, citations 82.4, main 81.2, metadata 75.0, llm 69.8, analysis 60.0, arxiv 57.7, config 55.6, pdf 50.0. Survivors include real logic (`appendix = None`, reversed `blank != -1`, `break` → `continue` in `strip_references`). Many others are prompt text or stopword spelling.
