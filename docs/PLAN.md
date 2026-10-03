# HW1 Plan — AI Research Assistant

Source: CS593 `hw1.pdf` — due **Oct 10, 11:59 PM** (app 60%, reflection 40%).
Plan written Oct 2 with Claude Code (Opus 5.5) before implementation. App LLM: Gemini.

## Decisions (resolved Oct 2)

| Question | Decision |
|---|---|
| LLM provider | ~~Claude~~ → **Gemini** (`google-genai` SDK), changed Oct 2 at user request; model via `GEMINI_MODEL` (default `gemini-2.5-flash`) |
| Stack | FastAPI + vanilla JS + SQLite + arXiv API |
| Deployment | Planned (timeboxed), even though the Submission list does not mention it |
| Repo location | `~/Developer/ai-research-assistant` |

## 1. Requirement → Deliverable → Completion condition

| # | Requirement (PDF) | Deliverable | Verifiable completion |
|---|---|---|---|
| R1 | Search by keyword/topic; show title, authors, year, abstract, link | Search tab + `GET /api/search` | Topic query renders ≥5 cards with all 5 fields; link opens |
| R2 | Save results to local DB; survives restart/refresh; browse | Save button, `papers` table, Library tab | Save 2 → restart server + refresh → both listed; re-save doesn't duplicate |
| R3 | Upload PDF; extract title/authors/year/abstract; render like search results | Upload form, `POST /api/upload`, metadata extractor | 2 distinct real PDFs show correct fields (checked vs. page 1) in the same card component |
| R4 | LLM summary based on **content**, not metadata | `POST /api/papers/{id}/summary` | Summary cites details absent from abstract (datasets, numbers); log shows prompt ≈ full-text length |
| R5 | Natural-language Q&A about a selected paper | `POST /api/papers/{id}/ask` + Q&A box | All 5 example questions from the PDF answered paper-specifically; off-paper question → "not stated in the paper" |
| X1 | GUI, frontend+backend, ≥1 external API, local DB, PDF processing, LLM API | Covered by R1–R5 | Each item traceable to a running component |
| S1 | GitHub repo: source, README (setup/run), feature list, deps/config, **no secrets** | Repo + README + `.env.example` | Fresh clone runs from README alone; secret grep of history is empty |
| S2 | Demo video: search, save, upload, summary, Q&A | Video file | All 5 flows visible in order |
| S3 | Reflection Q1–Q5 with **screenshots** of agent failures + corrections | Report + evidence log | Each Q has a section; each failure incident has prompt/output/correction screenshots |
| S4 | Deployment (mentioned in Overview) | Public URL | 5 flows work on URL; saved papers survive redeploy |

## 2. Architecture (smallest that satisfies the requirements)

```
Browser: single index.html + vanilla JS (tabs: Search | Library | Paper detail)
   │ fetch JSON
FastAPI (one Python process, also serves static files)
   ├─ GET  /api/search?q=           → arXiv API (no key)
   ├─ POST /api/papers              → save result → download arXiv PDF → extract text
   ├─ GET  /api/papers, /{id}       → library
   ├─ POST /api/upload              → store PDF → extract text → LLM metadata JSON
   ├─ POST /api/papers/{id}/summary → LLM(full text), cached in DB
   └─ POST /api/papers/{id}/ask     → LLM(full text + question)
SQLite (data/app.db) + data/pdfs/
```

- Libraries: `fastapi`, `uvicorn`, `httpx`, `pymupdf`, `google-genai`, `python-dotenv`, `python-multipart`.
- One table `papers`: `id, source(arxiv|upload), external_id UNIQUE, title, authors(JSON), year, abstract, url, pdf_path, full_text, text_status(ready|failed), summary, created_at`.
- Excluded: React/build step, vector DB/RAG (one paper fits in context), auth, chat persistence, OCR.

## 3. Full paper content for search results

- **Search source = arXiv**, so every result has a PDF at `arxiv.org/pdf/<id>`.
- **On save**, the backend downloads the PDF and runs the *same* extraction pipeline as upload → every saved paper has `full_text`.
- **Upload** → text from the file directly.
- **Failure** (download error, scanned PDF): `text_status=failed`; card shows "Full text unavailable — upload the PDF"; Summarize/Ask disabled. Never silently summarize the abstract.
- **Length**: send full text up to a character cap (start ~150k chars; confirm against model context in T0.3); trim references section first.
- **Scope**: summary/Q&A operate on **saved** papers (search → save → analyze).
- Alternative held in reserve: Semantic Scholar `openAccessPdf` (broader, but many results lack PDFs).

## 4. Assumptions, unknowns, replan triggers

| ID | Assumption | Replan trigger | Fallback |
|---|---|---|---|
| A1 | arXiv API reachable, no key (≤1 req/3s) | 503s / blocked from host | OpenAlex or Semantic Scholar |
| A2 | arXiv PDFs downloadable server-side | Timeouts/blocks | Lazy download on first Summarize; or ask user to upload |
| A3 | Gemini API key (AI Studio free tier) | Key missing / quota or rate limit hit | Switch model via `GEMINI_MODEL`; all calls go through one `complete()` function |
| A4 | Full text fits Gemini context window (1M tokens on 2.5 Flash) | Context-length error | Lower cap → chunked map-reduce summary |
| A5 | PyMuPDF extracts usable text | Garbled/empty text | Mark `failed`; OCR out of scope |
| A6 | LLM returns valid metadata JSON | Parse failure | Retry once → PDF metadata/filename |
| A7 | Host persists SQLite + PDFs | Data lost on redeploy | Attach volume (Railway/Fly); else document + demo locally |
| U1 | Whether deployment is graded | — | Planned anyway, timeboxed to 3h |
| U2 | Video length/format | — | ≤5 min, MP4 |
| R | Public URL spends API credits | — | Spend limit on key; don't publicize URL |

## 5. Milestones and tasks

### M0 — Foundations (Oct 2–3)
| Task | Req | Inputs/deps | Action | Output | Completion check |
|---|---|---|---|---|---|
| T0.1 Repo | S1 | GitHub account | git init in `~/Developer/ai-research-assistant`; `.gitignore` (`.env`, `data/`, `*.db`), `.env.example`, README stub; push | Pushed repo | `git check-ignore .env data/` matches both |
| T0.2 Evidence log | S3 | — | Create `docs/agent-log.md` (date, prompt, agent action, problem, fix) + screenshots folder; screenshot the planning session | Log w/ entry 1 | Entry exists |
| T0.3 Feasibility spike | A1–A6 | API key | Throwaway script: arXiv search → download 1 PDF → extract → 1 LLM call with full text | Console output | Prints title, >20k chars, LLM reply. **Replan if any step fails** |
| T0.4 Skeleton | X1 | T0.1 | FastAPI serving `index.html` with 3 tabs, `/api/health`, SQLite init on startup | Running app | Page loads; `curl /api/health` ok; `app.db` created |

### M1 — Search (Oct 3) → *user can find papers*
| Task | Req | Inputs/deps | Action | Output | Completion check |
|---|---|---|---|---|---|
| T1.1 Search API | R1 | T0.3, T0.4 | `/api/search?q=` → arXiv, parse Atom → `{external_id,title,authors,year,abstract,url,pdf_url}` | JSON list | `curl` returns ~10 items, all fields non-empty |
| T1.2 Search UI | R1 | T1.1 | Input + shared `renderPaperCard()`; empty/error states | Search tab | Browser renders results; link opens; bad query shows message |

### M2 — Library (Oct 4) → *user can save and browse*
| Task | Req | Inputs/deps | Action | Output | Completion check |
|---|---|---|---|---|---|
| T2.1 Save + fetch text | R2, R4 prep | T1.1 | `POST /api/papers`: upsert on `external_id`, download PDF, extract text, set `text_status` | Row with `full_text` | `full_text` length ≫ abstract; re-save → no new row |
| T2.2 Library list | R2 | T2.1 | `GET /api/papers` + Library tab (same card, status badge); "Saved ✓" on search cards | Library tab | Save 2 → refresh → **restart server** → both listed |
| T2.3 Detail view | R4/R5 prep | T2.2 | Click card → detail panel with metadata, empty Summary/Q&A areas | Detail panel | Opens for any saved paper |

### M3 — Upload (Oct 5) → *user can add own PDF*
| Task | Req | Inputs/deps | Action | Output | Completion check |
|---|---|---|---|---|---|
| T3.1 Upload endpoint | R3 | T2.1 extractor | `POST /api/upload`: validate PDF, store, extract text | Row with text | `curl -F file=@paper.pdf` creates row |
| T3.2 Metadata extraction | R3 | T3.1, LLM client | First ~6k chars → LLM → JSON `{title,authors[],year,abstract}`; fallback per A6 | Populated fields | 3 PDFs (arXiv, conference, journal) match page 1 by eye |
| T3.3 Upload UI | R3 | T3.2 | File picker on Library tab, "processing…" state, new card appears | Upload flow | Browser upload → card like search result → survives refresh |

### M4 — AI (Oct 6) → *MVP complete; feature freeze*
| Task | Req | Inputs/deps | Action | Output | Completion check |
|---|---|---|---|---|---|
| T4.1 LLM client | R4, R5 | `.env` key | One `complete(system, user)`; model from env; clear error if key missing | Module | Works; missing key → readable error, not a stack trace |
| T4.2 Summary | R4 | T4.1, T2.1 | Prompt with capped full text; sections: problem / method / results / limitations; cache in `summary` | Endpoint | Non-abstract details present; second call instant; `failed` papers refused |
| T4.3 Q&A | R5 | T4.1 | Full text + question; "answer only from the paper; say if not stated" | Endpoint | 5 PDF example questions answered specifically; World Cup question declined |
| T4.4 Detail UI | R4, R5 | T4.2, T4.3 | Summarize button + rendered summary; question box + session-only answer list | Full UI | **All 5 demo flows work locally on a saved and an uploaded paper** |

### M5 — Docs & deployment (Oct 7)
| Task | Req | Inputs/deps | Action | Output | Completion check |
|---|---|---|---|---|---|
| T5.1 README | S1 | M4 | Overview, features, architecture, stack, setup (Python version, venv, `pip install -r`, `.env`), run, layout, endpoints, limitations, agent used | README.md | **Clone into a new dir, follow only README** → app runs |
| T5.2 Secret audit | S1 | T5.1 | `git log -p \| grep -iE "AIza\|api_key="`; `git ls-files \| grep .env` | — | Zero hits (except `.env.example`) |
| T5.3 Deploy | S4 | M4 | Host with persistent volume; key in host env; `DATA_DIR` env; spend limit on key | Public URL | 5 flows on URL; saved papers survive redeploy. **Timebox 3h** |

### M6 — Demo & reflection (Oct 8–9, buffer Oct 10)
| Task | Req | Inputs/deps | Action | Output | Completion check |
|---|---|---|---|---|---|
| T6.1 Demo script | S2 | M4 | Choose query + PDF beforehand; script flows 1–5; reset DB | Script | Dry run < 5 min, no dead air |
| T6.2 Record | S2 | T6.1 | Screen recording (QuickTime), local or deployed | MP4 | All 5 flows visible, text legible |
| T6.3 Reflection | S3 | Evidence log | Write Q1–Q5 from log; Q3 uses screenshot sequences (prompt → bad output → correction → result) | Report PDF | 5 sections; every Q3 incident has before/after screenshots |
| T6.4 Submit | all | — | Repo link + video + report on Brightspace | — | Links open in a private window (repo public/shared) |

## 6. Ongoing reflection evidence (T0.2 → end)

- **Screenshot immediately** when the agent is wrong — before scrolling or retrying (prompt, output, correction, result).
- **End of each milestone**: 3–5 lines in `docs/agent-log.md` — what was asked, what worked, what was hand-edited (rough %), which prompting style worked.
- Backups: Claude Code transcripts under `~/.claude/projects/`; `/export` a session to recreate screenshots later.
- Record how any PDF-processing skill was chosen/vetted (built-in vs. third-party) — material for Q5.

## 7. Validation and scope

- Validation = the per-task curl/browser checks above; optional single `scripts/smoke.sh`. No test suite (HW2).
- Deferred until M4 passes: RAG/embeddings, persistent chat history, metadata editing, tags, delete, OCR, React.
- When an assumption in §4 fails: record it in the log, apply the fallback, and update this plan.

## Replan log

- **Oct 2 — LLM provider changed to Gemini** (user decision during M0). Impact: SDK `anthropic` → `google-genai`; env var `GEMINI_API_KEY`; A3/A4 updated. No change to architecture or milestones.
- **Oct 2 — T0.3 spike:** A1 (arXiv search), A2 (PDF download, 8.6 MB), A5 (68,792 chars from 18 pages) confirmed. A3/A4 pending a Gemini key.
