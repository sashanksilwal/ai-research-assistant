# Round 2 — Requirements, real libraries and real service responses

**Agent:** same subagent, resumed, in the same scratch copy.
**Inputs given:** `requirements.md` (R1–R5, X1 and 10 real HW1 failures); real arXiv, OpenAlex and Semantic Scholar responses recorded by the supervising agent; the exact CDN builds of marked, DOMPurify, KaTeX and vis-network.
**Withheld on purpose:** mutation survivors (R3).

**Prompt, verbatim:**

> Round 2: tie the suite to the real requirements and to real outside systems, using `feedback2/`.
>
> Read `feedback2/requirements.md` (the app's intended behavior and failures that really happened). `feedback2/recorded/` holds real responses captured today from arXiv (`arxiv_search.xml`, `arxiv_error.xml`), OpenAlex and Semantic Scholar (one known id, one unknown id). `feedback2/vendor/` holds the exact library builds that `static/index.html` loads from the CDN.
>
> 1. **Contract tests for the fakes.** Move the recorded files to `tests/fixtures/recorded/` and test the app's parsing and graph logic against them. Compare your hand-written fakes with the real shapes and fix any that differ. Use real `google.genai.types` response objects where the Gemini fake returns `SimpleNamespace`, so `.text` and `.parsed` are the SDK's real behavior.
> 2. **Real browser libraries.** Move the vendored files to `tests/fixtures/vendor/` and serve them at the CDN URLs in `open_app` through `page.route`, so nothing leaves the machine. Replace stub-based tests with real-library tests wherever that is possible: DOMPurify must actually remove XSS from model output, and KaTeX must render math exactly once. Use real vis-network for what a headless browser can observe; keep a stub only for what it cannot, and say which.
> 3. **Requirement traceability.** Add `tests/REQUIREMENTS.md` mapping each R1–R5 and X1 row to named tests, one row per completion check. For any check with no real test, add one. Include a real restart for R2: stop the server process and start a new one on the same data directory. Include realistic multi-page PDFs generated in the test, with sections, references and an appendix, for R3 and R4.
> 4. **Regression tests for the 10 listed failures.** Make sure each has a test written from the failure description, not from the current code. Failure 7 needs a browser check that inactive tab text is actually visible (computed color versus background).
>
> Rules: do not change `app/` or `static/`. Keep strict xfail for app bugs. Don't read outside this directory, and make no network calls: use only the files provided. If a real library or a real response exposes a new app bug, that is the most valuable outcome, so record it with a strict xfail and a precise reason. Keep the suite well below 500 cases and drop tests the new ones make redundant. Run in the foreground as before.
>
> Report: removed, added and changed counts and reasons; differences found between your fakes and reality; which stubs remain and why; new app bugs with detecting tests; any requirement check you could not test.
