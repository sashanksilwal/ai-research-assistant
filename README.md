# AI Research Assistant

A small web app for working with research papers: search arXiv, save papers to a local library, upload your own PDFs, and use Google Gemini to summarize a paper or answer questions about it, grounded in the paper's **full text**.

Built for CS593 HW1 using a coding agent (Claude Code). See [`docs/PLAN.md`](docs/PLAN.md) for the plan and [`docs/agent-log.md`](docs/agent-log.md) for the development log.

![Search results](docs/screenshots/2026-10-02-m1-search-results.png)

## Features

| Feature | How it works |
|---|---|
| **Search papers** | Keyword/topic search over the arXiv API. Results show title, authors, year, abstract, and links to the paper page and PDF. |
| **Save to a local library** | "Save to library" stores the paper in SQLite **and downloads its PDF**, extracting the full text. The library survives page refreshes and server restarts. |
| **Upload PDFs** | Upload any paper PDF. Gemini extracts the title, authors, year and abstract from the first pages, so it renders like a search result. Falls back to the PDF's embedded metadata if Gemini is unavailable. |
| **Summarize** | Gemini writes a structured summary (problem, approach, experiments, key results, limitations) from the paper's full text, not just its abstract. Summaries are cached; "Regenerate" makes a new one. |
| **Ask questions** | Ask anything about a paper, or click one of the example questions. Answers come only from the paper's text; if the paper doesn't say, the answer says so. |
| **Citation graph** *(extra)* | "Show citation graph" in the Library draws your saved papers as nodes with an arrow A → B when A cites B, using reference lists from OpenAlex. Click a node to open the paper. |

![Library](docs/screenshots/2026-10-02-m2-library.png)

## Architecture

```
Browser: static/index.html + app.js (vanilla JS; tabs: Search | Library | Paper)
   │ fetch JSON
FastAPI app (app/main.py) — one Python process, also serves the static files
   ├─ app/arxiv.py      arXiv API search → normalized paper dicts
   ├─ app/pdf.py        PDF download + text extraction (PyMuPDF)
   ├─ app/metadata.py   title/authors/year/abstract from uploaded PDFs (Gemini + fallback)
   ├─ app/analysis.py   summary and Q&A prompts over the full text
   ├─ app/llm.py        Gemini client: structured output, retries, model fallback, readable errors
   ├─ app/citations.py  citation links between library papers (OpenAlex)
   └─ app/db.py         SQLite access
data/app.db (SQLite)  +  data/pdfs/ (saved and uploaded PDFs)     ← created on first run, not in git
```

**How full text is obtained.** Every arXiv result has a free PDF. When you save a search result, the backend downloads that PDF and extracts its text with the same pipeline used for uploads. Papers whose PDF can't be read (e.g. scanned images) get a "Full text unavailable" badge, and summary/Q&A are disabled for them rather than silently falling back to the abstract.

**Tech stack:** Python 3.11, FastAPI, Uvicorn, SQLite, PyMuPDF, httpx, `google-genai` SDK; frontend in plain HTML/CSS/JS, with `marked` + `DOMPurify` (from a CDN) to render the model's Markdown safely and `vis-network` for the citation graph.

### External services

| Service | Used for | Key needed | Notes |
|---|---|---|---|
| [arXiv API](https://info.arxiv.org/help/api/index.html) (`export.arxiv.org/api/query`) | Paper search, PDF downloads | No | arXiv asks for ≤1 request every 3 s; interactive use stays well below that. |
| [OpenAlex API](https://docs.openalex.org/) | Citation graph: matching papers by title and reading their reference lists | No | Lookups are cached per paper in the database. Optional `OPENALEX_EMAIL` gets faster service. |
| [Google Gemini API](https://ai.google.dev/) | Upload metadata extraction, summaries, Q&A | Yes (`GEMINI_API_KEY`) | The free tier has low per-minute limits and occasional "high demand" errors; the app retries and falls back across models (see `GEMINI_FALLBACK_MODELS`). |

## Setup and running

Requirements: Python 3.10+ (developed on 3.11) and a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

```bash
git clone https://github.com/sashanksilwal/ai-research-assistant.git
cd ai-research-assistant

python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# edit .env and set GEMINI_API_KEY=<your key>

.venv/bin/uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The database and PDF folder are created automatically under `data/` on first run.

Search and the library work without a Gemini key; uploads fall back to the PDF's embedded metadata, and summary/Q&A show an error until a key is set.

### Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — (required for AI features) | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Main model |
| `GEMINI_FALLBACK_MODELS` | `gemini-flash-latest,gemini-3.5-flash` | Tried in order when the main model is rate-limited (429) or overloaded (503) |
| `DATA_DIR` | `data` | Where the SQLite database and PDFs are stored |
| `OPENALEX_EMAIL` | — (optional) | Contact email sent to OpenAlex for its faster "polite pool" |

`.env` is git-ignored; never commit API keys.

## Using the app

1. **Search** tab: enter keywords (e.g. `retrieval augmented generation`) → **Save to library** on any result. Saving takes a few seconds while the PDF downloads.
2. **Library** tab: browse saved and uploaded papers; upload a PDF with the bar at the top; **Show citation graph** to see which saved papers cite each other.
3. **Open** a paper → **Paper** tab: **Summarize with Gemini**, then ask questions in the box or click an example question.

## API

| Method & path | Description |
|---|---|
| `GET /api/search?q=` | Search arXiv (10 results) |
| `POST /api/papers` | Save a search result (downloads PDF, extracts text); returns the existing paper if already saved |
| `POST /api/upload` | Upload a PDF (multipart `file`) |
| `GET /api/papers` | List the library |
| `GET /api/papers/{id}` | One paper (metadata, summary, text status) |
| `GET /api/papers/{id}/pdf` | The stored PDF |
| `POST /api/papers/{id}/summary[?refresh=true]` | Summarize from full text (cached) |
| `POST /api/papers/{id}/ask` | Body `{"question": "..."}` → answer from full text |
| `GET /api/graph` | Citation graph of the library: `{nodes, edges}` |
| `GET /api/health` | Health check |

Interactive API docs are at <http://127.0.0.1:8000/docs> (generated by FastAPI).

## Project structure

```
app/            FastAPI backend (modules described under Architecture)
static/         Frontend: index.html, app.js, styles.css
scripts/spike.py  Feasibility check used before building (arXiv → PDF → text → Gemini)
docs/           PLAN.md (work plan), agent-log.md (coding-agent log), screenshots/
CLAUDE.md       Notes for the coding agent (known mistakes, workflow rules)
requirements.txt, .env.example
```

## Limitations

- Single user, no authentication; not production-hardened.
- Summaries and Q&A send up to ~300,000 characters of a paper to Gemini; longer documents are truncated, and the UI says so.
- Scanned PDFs without a text layer can be stored but not summarized (no OCR).
- Q&A is single-turn: each question is answered independently, and the question history is not saved.
- Search covers arXiv only, with arXiv's relevance ranking.
- Some arXiv abstracts contain raw LaTeX (e.g. `\emph{...}`), shown as-is.
- The citation graph depends on OpenAlex's data: papers are matched by title, OpenAlex sometimes has duplicate records for famous papers, and very new papers may have no reference list yet, so some real citations can be missing.
