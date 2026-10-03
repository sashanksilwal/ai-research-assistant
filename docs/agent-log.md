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

_TODO: rest of model list (down to gemini-3.8-flash); the "we will use gemini" message._

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
  _TODO screenshot: search results page (my capture went to a macOS temp folder and was lost — retake; let the thumbnail disappear so it saves to Desktop)._
- **Hand-edits:** 0% of code; my contribution was the visual check and spotting the CSS bug.
