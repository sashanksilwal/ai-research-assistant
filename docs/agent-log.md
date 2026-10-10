# Coding-Agent Log (reflection evidence)

Agent: Claude Code (model: Claude Opus 5.5), terminal CLI.
Plan: [PLAN.md](PLAN.md) · Project: [README](../README.md)
Format per entry: date · milestone · what I asked · what the agent did · problems / corrections · hand-edits (rough %) · lesson.
Screenshots live in `docs/screenshots/` and are embedded below (name `YYYY-MM-DD-<topic>-N.png`).

---

## 2026-10-02 · Planning
- **Asked:** read hw1.pdf, plan with a deliverable-based WBS (requirement map, smallest architecture, dependencies/unknowns, how full paper text is obtained, milestones with completion checks).
- **Agent did:** extracted the PDF (pdftotext/pypdf missing → fell back to its built-in PDF reader), produced [PLAN.md](PLAN.md); picked arXiv specifically because every result has a PDF, so summaries can use full text (R4).
- **My decisions:** Claude API (later switched to Gemini, see M0); FastAPI + vanilla JS + SQLite; plan deployment; repo in `~/Developer`.
- **Problems / corrections:** none yet. Note: the agent flagged that its session was running from `~/.Trash/...` and asked where the repo should live.
- **Lesson:** asking for "completion checks" per task forced concrete, testable steps instead of vague TODOs.

My WBS planning prompt:
![Planning prompt](screenshots/2026-10-02-planning-prompt.png)

## 2026-10-02 · M0 Foundations
- **Asked:** "do it" (execute M0 from [PLAN.md](PLAN.md)).
- **Agent did:** git repo + Python 3.11 venv, `.gitignore`/`.env.example`/`requirements.txt`, FastAPI skeleton (3 tabs, `/api/health`, SQLite `papers` table), feasibility spike script.
- **Mid-task change:** I switched the LLM from Claude to Gemini while the agent was writing the spike. It swapped the SDK, rewrote the spike's LLM step, and recorded the change in the [PLAN.md replan log](PLAN.md#replan-log). (Evidence for Q5: changing requirements mid-task.)
- **Small agent slip:** its sed-based edit left a duplicate `import os` and used the deprecated `fitz` import (PyMuPDF printed a deprecation warning); it noticed and fixed both on the next step.
- **Spike results:** arXiv search ✓, PDF download ✓, text extraction ✓ (68,792 chars / 18 pages), Gemini ✓ (18k-token full paper).
- **Agent mistake → fix:** the agent defaulted to `gemini-2.5-flash` from its own training-era knowledge; the call failed with 503 "high demand". Instead of retrying blindly it listed the models my key can access, found newer ones (up to 3.8 Flash), and switched. Lesson: agent's model knowledge can be stale; verify against the live API. Also hit a `python-dotenv` `find_dotenv()` assertion when running from stdin; fixed by passing the path explicitly.
- **Hand-edits:** 0% so far.

Overview — 503 → list models → switch to 3.8 Flash (collapsed view):
![503 recovery overview](screenshots/2026-10-02-gemini-503-recovery.png)

The 503 error, expanded:
![503 traceback](screenshots/2026-10-02-gemini-503-error.png)

`load_dotenv()` crash → fixed with explicit path:
![dotenv error and fix](screenshots/2026-10-02-dotenv-error-fix.png)

Start of the model list:
![Model list, part 1](screenshots/2026-10-02-model-list-1.png)

_(The rest of the model list, down to `gemini-3.8-flash`, was not captured; the text above records the switch.)_

My mid-task switch to Gemini:
![Switch to Gemini](screenshots/2026-10-02-switch-to-gemini.png)

## 2026-10-02 · M1 Search ✓
- **Asked:** "yes" (start M1 from [PLAN.md](PLAN.md)).
- **Agent did:** `app/arxiv.py` (query builder that ANDs keywords and strips arXiv query syntax; Atom parsing; version-less arXiv id for de-duplication), `GET /api/search`, search page with a shared `renderPaperCard()` reused later by the library.
- **API check (T1.1) ✓:** 10 results, all 7 fields non-empty; punctuation query works; nonsense query → `[]`; empty query → 422.
- **Agent limitation:** the agent tried to verify the UI itself through the Claude-in-Chrome extension. Two Chrome browsers were connected to my account; it asked me to pick one, but the one I picked could not reach `localhost:8000` (requests never hit the server log — probably a browser on another machine). After two attempts it stopped, closed its tab, and handed the visual check back to me instead of claiming the UI worked. It also kept M1 uncommitted until the page is checked. (Q4: I still have to verify UI myself.)

Agent's summary of the failed browser check:
![Browser check failed](screenshots/2026-10-02-browser-check-failed-summary.png)

Extension asked which of two connected browsers to use:
![Multiple browsers connected](screenshots/2026-10-02-browser-check-multiple-browsers.png)

The navigation landed on Chrome's error page, so the page script failed:
![Browser error page](screenshots/2026-10-02-browser-check-error-page.png)

- **Agent bug found by me (Q3):** after M1, the inactive tab buttons ("Library", "Paper") were blank. Cause: the agent added a global `button { color: #fff }` style for the new Search button, which the tab buttons inherited → white text on white background. The agent had only syntax-checked the JS and never saw the page rendered (its browser check failed, see above), so it missed this. Fix: explicit `color` on `.tab`. Lesson: CSS side effects are invisible to non-visual checks; a human look at the page caught it immediately.

  Blank "Library" / "Paper" tabs (white text on white):
  ![Invisible tab buttons](screenshots/2026-10-02-tab-buttons-invisible.png)

- **UI check (T1.2) ✓ — done by me in my own browser:** query "distillation sashank" → 5 cards with title, authors, year, abstract, View paper / PDF links; tabs readable after the fix. Noted (not fixed, optional): some arXiv abstracts contain raw LaTeX like `\emph{soft}`.
- **Hand-edits:** 0% of code; my contribution was the visual check and spotting the CSS bug.

M1 search results (my check in my own browser):
![M1 search results](screenshots/2026-10-02-m1-search-results.png)

## 2026-10-02 · M2 Library ✓
- **Asked:** continue to M2 (save → library → detail).
- **Agent did:** `app/pdf.py` (download + text extraction, rejects non-PDF responses and text-less scans), `POST /api/papers` (dedupes on arXiv id, downloads the PDF, stores full text), `GET /api/papers`, `GET /api/papers/{id}`, `GET /api/papers/{id}/pdf`; Save button on search cards, Library tab with a "full text ready / unavailable" badge, Paper tab.
- **Bugs during M2, all caught by the completion checks before I saw the UI:**
  1. **Repeated mistake:** server failed to start — `SyntaxError: f-string expression part cannot include a backslash` (a regex `\w` inside an f-string; not allowed before Python 3.12). The agent had made *the same mistake* earlier in the status-line script. It only noticed because every test request failed; it then read the server log. Lesson: the agent doesn't learn within a session unless the lesson is written down.
  2. **Search bug (pre-existing from M1):** `attention is all you need` returned **0 results**. Agent tested raw arXiv queries and confirmed ANDing stopwords (`all:is`) matches nothing. Fix: drop stopwords from the query. My M1 check had used keyword-only queries, so it never exercised this.
  3. **Data quirk:** one saved paper reported 6,783 chars for a 21-page PDF. Agent compared Python vs SQLite lengths: full text (61,973 chars) was stored, but the PDF contained NUL characters and SQLite's `length()` stops at the first one. Fix: strip NULs at extraction; repaired the stored row.
- **API checks (T2.1) ✓:** saved paper has 16,570 chars of text vs 1,247-char abstract; re-save returns the same id; PDF served from `/api/papers/{id}/pdf`; bad PDF URL → saved with `text_status=failed` and a reason; 3 papers still present after server restart.
- **Hand-edits:** 0%.
- **UI check (T2.2/T2.3) ✓ — by me:** saved papers appear in the Library tab with "Full text ready" badges (61,970 and 16,570 chars), Open → Paper tab works.

  Library with two saved papers and full-text badges:
  ![M2 library](screenshots/2026-10-02-m2-library.png)
- **My correction → making the lesson stick (Q5):** I told the agent to *note the error it had and missed* (the repeated f-string backslash bug). It added a repo `CLAUDE.md` — which Claude Code loads automatically every session — with a "known agent mistakes" section and a rule to import-check Python before restarting the server. Lesson: an agent only "remembers" a correction if it's written into the context it reads every time.

## 2026-10-02 · M3 Upload (in progress)
- **Asked:** "yes" (start M3).
- **Agent did:** `app/llm.py` (Gemini client: structured JSON output, readable errors, retry + fallback across models), `app/metadata.py` (Gemini extracts title/authors/year/abstract from the first ~8k chars; heuristic fallback from PDF metadata + "Abstract" heading), `POST /api/upload` (rejects non-PDFs, keeps text-less scans with a "failed" badge), upload form + source badges in the Library tab.
- **Tested on 3 real layouts:** BERT (ACL), Dropout (JMLR), my own arXiv paper — plus a text-less "scanned" PDF and a fake `.pdf` (400).
- **Assumption failed again (A3), measured instead of guessed:** 2 of 3 uploads hit Gemini 503 and fell back to weak heuristics (title = filename). The agent ran 5 calls per model: `gemini-3.8-flash` 3 ok then 429 (free-tier per-minute limit), `gemini-3.5-flash` 503 ×3, `gemini-flash-latest` 5/5 ok. Since limits are per model, it added fallback across models + one delayed retry. Rerun: Dropout and my paper extracted by Gemini; BERT still got all-503 for ~20 s but the fallback recovered correct title/authors/year from the PDF's embedded metadata.
- **"Bug" that wasn't:** my paper came back with no abstract. Agent checked page 1: the PDF genuinely has no abstract section (only arXiv's listing has one), and Gemini correctly returned null as instructed instead of inventing one.
- **Agent slips:** (1) fallback abstract kept line-break hyphenation ("representa- tion") → fixed + repaired stored row. (2) An agent edit script crashed with a `SyntaxError` before writing anything, but the follow-up `checks-ok` still printed because it checked the *unchanged* files — a misleading green light. The agent caught it from the traceback, confirmed nothing was written, redid the edit with its Edit tool, and then verified the *served* files contained the change. Lesson: "the checks passed" only means something if they check the thing you changed.
- **Scope request (Q5):** mid-M3 I asked for a citation graph of saved papers. The agent pointed out it conflicts with my own "no optional features until required workflows work" rule and added it to PLAN.md as backlog item #1 after M4 instead of building it immediately.
- **UI check (T3.3): pending** — deferred by me; I asked the agent to stop calling Gemini and continue, and I will test M3+M4 together.

## 2026-10-02 · M4 Summary + Q&A (built; live test pending)
- **Constraint I set:** "for now don't use the Gemini API, just continue; I'll tell you and then we test." The agent committed M3 as "UI check pending" and kept building.
- **Agent did:** `app/analysis.py` (summary prompt with Problem / Approach / Experiments / Key results / Limitations sections; Q&A prompt that answers only from the paper and says "The paper doesn't say" otherwise; paper text first, instructions/question last; 300k-char cap reported as `truncated`, never silent), `POST /api/papers/{id}/summary` (cached in DB, `?refresh=true` regenerates), `POST /api/papers/{id}/ask`; Paper tab with Summarize/Regenerate button, question box (Enter to send), one-click chips for the 5 example questions from the assignment, Markdown rendering via marked + DOMPurify.
- **How it was tested without Gemini:** the agent replaced `llm.generate` with a fake that records the prompt and returns canned text, against a throwaway temp database. 11 checks passed: full text (a marker planted 50k chars deep) reaches the prompt and the abstract alone is never used (R4); summary cached and refreshable; question placed after the paper with the "only the paper" system prompt (R5); 409 for papers without full text; 404 / 422 for bad input; huge paper truncated and flagged; Gemini outage → readable 503. **0 real API calls.**
- **Not yet verified:** real Gemini output quality and the rendered UI — scheduled for my combined M3+M4 test.

## 2026-10-02 · M5 README (T5.1 ✓)
- **Agent did:** full README (features, architecture, how full text is obtained, external services, setup, config, API, structure, limitations), then the plan's completion check: **fresh `git clone` from GitHub into a scratch folder, followed only the README, with no Gemini key**. Search, save (PDF + 30k chars of text), upload fallback, and the "key not set" message all worked; `data/` was created automatically.
- **Found by that check:** without a key, the Gemini SDK left a half-built client whose cleanup printed `AttributeError` tracebacks in the server log. Fix: check for the key before constructing the client; rerun showed 0 tracebacks.

## 2026-10-02 · Extra: citation graph
- **Asked:** "add the graph now?" — I chose to build backlog item #1 before the live M4 test (it doesn't need Gemini).
- **Agent did:** probed APIs *before* writing code. Semantic Scholar (the plan's choice) rejected 5 of 6 keyless requests with HTTP 429 → assumption failed → it tested **OpenAlex** instead: no key, no rate-limit errors, and better reference coverage (Dropout: 36 refs vs 0 on Semantic Scholar). Built `app/citations.py` (title match with ≥0.9 similarity — a loose search had returned a junk record titled "[1] Nandi, S.…"), cached lookups in new DB columns with an automatic migration, `GET /api/graph`, and a vis-network graph in the Library tab (click a node to open the paper).
- **Checks:** temp DB with 5 known papers → all matched, BERT → Attention edge found, second load instant from cache; migration run twice on a *copy* of my real DB (kept all rows). Known gap: an expected Attention → Dropout edge is missing because OpenAlex matched a duplicate 2025 "Attention" record — documented as a limitation.
- **Agent mistake (privacy) — the most serious one so far:** while probing OpenAlex it put **my email address** in a `mailto=` parameter (OpenAlex's "polite pool") on 3 requests, without asking. The agent had my email only as account context from Claude Code, with an explicit instruction not to send it to unrelated services — and did anyway, because the API docs suggest it. It flagged the mistake itself in its summary, but buried it as one bullet among results; **I called it out as a big bug.** Follow-up: it checked that the email is not in the code, git history or temp files; explained what was sent where (3 GET requests to api.openalex.org, likely retained in their logs, can't be recalled); made the email an opt-in `OPENALEX_EMAIL` setting; and added a "never send personal info" rule to `CLAUDE.md` plus a cross-project memory. Lessons (Q3/Q5): an agent with access to personal context can leak it as a side effect of "being helpful" with an API; and disclosures of mistakes need to be prominent, not buried in a results list.

  The agent's original (understated) disclosure:
  ![Email sent to OpenAlex](screenshots/2026-10-02-email-sent-to-openalex.png)

  **Reported to Anthropic:** I submitted the incident through Claude Code's `/feedback` command (receipt `66a65abe-76a2-43a9-a677-788d79c0d1cd`). To include in the reflection report (Q3).
- **Lesson repeated from M1:** the agent styled the new graph button explicitly instead of inheriting the global `button` style, avoiding the invisible-tab bug.

## 2026-10-06 → 10-10 · Graph v2, Semantic Scholar, live Gemini, speed
- **Asked (in order):** "did we finish?"; write the reflection report (as a doc, then `docs/reflection.html`); deploy (I chose Railway over Vercel after the agent pointed out Vercel has no persistent disk for SQLite/PDFs); improve the graph "like Obsidian"; add papers (incl. ones fitting the course syllabus) so the graph has edges; show only top-N labels; suggested search topics; a simple RefSeek-like design; strip references before sending papers to Gemini; "is Gemini not working?"; "can we make it faster?".

### Tests and checks run

| # | What was tested | How | Result |
|---|---|---|---|
| 1 | Secrets in git history (T5.2) | `git log -p \| grep -iE "AIza\|api_key="`, `git ls-files \| grep env` | 2 hits, both placeholders (`<your key>` in README, the grep itself in PLAN); only `.env.example` tracked |
| 2 | Obsidian-style graph UI | `node --check`, curl of served `app.js`/`index.html`, then my own browser check | Worked, but my screenshot showed overlapping labels → added "Labels: top N" + names on hover |
| 3 | Adding papers via the app's own API | Script: `GET /api/search` → pick exact arXiv id → `POST /api/papers`, 3 s between arXiv calls | 20 papers saved, all `text_status=ready`. Searching the exact titles of "Attention Is All You Need", GPT-3 and Codex did **not** return them in the top 10; adding an author name fixed it |
| 4 | Citation data, OpenAlex | `/api/graph`, then inspected OpenAlex records directly | 12 edges, 15 of 23 papers unlinked. Root cause: Chain-of-Thought's only record has 0 references, ReAct isn't in OpenAlex search, arXiv-DOI lookups return unrelated papers |
| 5 | Agent's first fix: pick the OpenAlex record with most references | Re-resolved all papers (DB backed up first) | **Worse: 12 → 10 edges** (other papers cite a different duplicate record). Reverted, DB restored from backup |
| 6 | Semantic Scholar batch endpoint | One POST for all arXiv ids | 50 arXiv↔arXiv edges found in the probe |
| 7 | Integrated Semantic Scholar + OpenAlex | `/api/graph` after restart | First load: S2 returned 429 on 4/4 retries (51 s), graph fell back to 12 OpenAlex edges. Next load: **61 edges, 0 unlinked papers, 10 edges into my uploaded BERT/Dropout PDFs** (matched by title) |
| 8 | Suggested topics | 8 topic queries through `/api/search` | 10 results each, all on-topic |
| 9 | Reference stripping | Ran `strip_references` on all 23 stored papers + 4 synthetic cases | First version cut **41% of Reflexion, including its appendix** (appendix starts with a bare "A" line). Fixed with year-density + stricter appendix headings: 0–22% cut (~10% avg), appendices kept; errors now only under-cut |
| 10 | Summary spinner never finished ("is Gemini not working?") | Checked server log + open connections; pinged each model with a 45 s limit | `gemini-3.8-flash` and `gemini-flash-latest` accepted requests and **never answered**; `gemini-3.5-flash` 1.2 s. Our code had no timeout, so it hung forever. Also found the old server process still serving my browser after a restart |
| 11 | Timeout + fallback logic | Fake Gemini client, 4 scenarios (hang-hang-ok, all hang, all 503, hang-503-503) | All correct: hung models skipped after the limit and not retried; readable error when all fail |
| 12 | Model speed/quality comparison | Same "Attention" summary on 6 models, 40 s limit | 3.5-flash-lite 2.9 s, flash-lite-latest 2.8 s, 3.5-flash 12.1 s, 3.6-flash 12.2 s (all with WMT/BLEU numbers); 3.7-flash and 3.8-flash timed out |
| 13 | Q&A on the new default (3.5-flash-lite) | Live calls | "What datasets are used?" 1.3 s, WMT 2014 En-De/En-Fr + WSJ with sizes and Section 5.1; "Who won the 2022 World Cup?" 0.8 s → "The paper doesn't say." |

### Agent mistakes (Q3)
- **No timeout on LLM calls since M3.** Every earlier live test either succeeded or failed with an error code, so a model that silently hangs was never exercised. Found only because I saw an endless spinner.
- **A fix that made things worse:** choosing the OpenAlex record with the most references lost edges. The agent measured before/after, reverted, and restored the DB backup it had made beforehand.
- **Reference stripper dropped a whole appendix** on its first version; caught by measuring the cut on every stored paper rather than one example.
- **Restart didn't restart:** `pkill` lets uvicorn finish in-flight requests, so the old process kept serving my browser while the agent tested the new one.
- **Install got stuck:** `brew install railway` hung on Homebrew's auto-update for 5 min; the agent stopped it and used npm.

### Decisions
- Kept arXiv as the search source (every result has a PDF → full-text summaries), Semantic Scholar only for citations.
- Kept sending full text to Gemini (requirement 4), minus the reference list.
- Default model → `gemini-3.5-flash-lite` (speed for the demo; trade-off: summary ran 483 words vs the ~400 asked, and omitted hardware details the larger models gave).
- Label "Suggested topics", not "Recommended for your library": the list is static, so the stronger label would be false.

## 2026-10-10 · Demo video, math rendering, submission prep
- **Asked:** "is there a skill that can record the video?", then "give me the script which I will read and then you can edit them together"; later "add PyMuPDF text when I say it", "add text to the video when required", "use Remotion if relevant".
- **Agent did:** no installed skill could record localhost, so it wrote `scripts/record_demo.py` (Playwright drives the app in headless Chromium against a *copy* of my data on port 8001, with a visible cursor and step captions) and `docs/demo-script.md` (narration per scene). It checked each take by extracting frames and looking at them before showing me.
- **Problems found in its own takes:** take 1 showed raw LaTeX (`$\rightarrow$`) in the summary and Q&A answers scrolled off-screen. A prompt rule against LaTeX reduced but did not remove it (the lite model still wrote 2 formulas), so it added KaTeX rendering; first KaTeX version showed every formula twice (hidden MathML visible) → switched to HTML-only output, verified with a browser screenshot.
- **Narration sync:** I read the script in one take (3:16) while watching. The agent couldn't listen, so it transcribed the audio locally (faster-whisper) and found my paragraphs drifted up to ~20 s behind the scenes. It cut the audio at the pauses between paragraphs, re-recorded with each scene as long as its paragraph, and placed each paragraph at its scene's real start (all within 0.4 s). Labels for hard-to-hear terms (PyMuPDF, SQLite, arXiv, Semantic Scholar · OpenAlex, …) are burned in by `scripts/add_terms.py`.
- **Remotion:** the agent judged it not worth a new React/Node render pipeline on the due date, since ffmpeg covered cutting audio and adding text.
- **Hand-edits:** 0% of code; I recorded the narration and decided what to show.
