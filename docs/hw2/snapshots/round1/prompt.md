# Round 1 — Review and execution feedback

**Agent:** same subagent as R0, resumed, in the same scratch copy.
**Inputs given:** `triage.md` from round0 (without its mutation section), `jscoverage.txt`, `pytest.txt`.
**Withheld on purpose:** mutation survivors (R3), requirements and HW1 bug history (R2).

**Prompt, verbatim:**

> Round 1: improve the test suite using the review feedback in `feedback/`.
>
> Work in the same scratch repository as before. Read `feedback/triage.md` (a review of your suite), `feedback/jscoverage.txt` (Chromium coverage of `static/app.js`) and `feedback/pytest.txt` (the last run).
>
> 1. Strengthen every test labelled WEAK so it checks the resulting behavior or state, not just a status code or `!= 500`. Remove any assertion that can pass vacuously.
> 2. Remove or merge the REDUNDANT tests, unless you can name the distinct behavior a test protects. If you keep one, say why.
> 3. Rewrite the MIRROR tests that do not need the stubs so they check a user-visible requirement, or delete them. Leave the four stub-based browser tests alone this round.
> 4. Add tests for the frontend paths listed as uncovered, where they are real user behavior: graph title search, label limit, hover focus, click-to-open, remove failure, abstract expand and collapse, and the truncation note on answers.
>
> Rules: do not change `app/` or `static/`. Keep strict xfail for app bugs and keep the existing bug reasons. Do not add tests only to raise counts: quality matters more than quantity, and a smaller suite is fine. Do not read outside this directory. Run the full suite with `.venv`-equivalent Python at <repo>/.venv/bin/python and E2E_CHROMIUM_PATH set as before. Run it in the foreground and avoid commands that wait on stdin.
>
> Report: tests removed, added and changed, with counts and reasons; anything in the review you disagree with; any new app bug, with the test that detects it.
