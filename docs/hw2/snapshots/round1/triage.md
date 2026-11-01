# Round 1 triage

344 cases: 326 passed, 18 xfailed, 0 failed, 0 flaky over 5 seeds. Python line and branch coverage 100%; `static/app.js` 98.7% (was 94.6%). Mutation **74.1%** (was 73.8%; 2 more killed).

Changes: 12 tests removed (9 redundant, 3 mirror), 9 browser tests added, 13 weak tests strengthened, 4 others changed.

| Label | R0 | R1 | Note |
|---|---|---|---|
| TEST-BUG | 0 | 0 | |
| WEAK | 13 | 0 | All strengthened. The agent showed 5 strengthened xfails pass against trial fixes in a throwaway copy |
| MIRROR | 7 | 10 | 3 removed; 6 new graph tests use a stub, so they prove what the app asks vis-network to do, not that the real library does it. The agent raised this itself |
| REDUNDANT | 9 | 0 | Removing them lost no mutation kills |
| FLAKY | 0 | 0 | |

Bugs: same 14, no new ones. Two tests renamed: B5 is now `test_search_skips_an_incomplete_entry`, B7 is `test_save_with_a_malformed_pdf_url_is_saved_without_text`. Their expected outcomes are a judgement call (bad entry skipped, bad URL treated like a failed download).

**Observed, not counted as bugs:** after a failed Remove the stale card stays in the Library (no requirement covers it); opening the graph during a library load draws it twice (harmless).

**Finding:** review-driven fixes made tests clearer and more honest, but barely changed backend fault detection. Five of the 13 strengthened tests are xfails, which cannot kill a mutant while they fail. Frontend gains are not visible in the mutation score, because mutation covers only Python.

Still open: real browser libraries, fakes checked against real services, requirement traceability, multi-page PDFs.
