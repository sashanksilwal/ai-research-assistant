# AI Research Assistant

CS593 HW1 — search arXiv papers, save them to a local library, upload PDFs, and use Gemini to summarize papers and answer questions about them.

> Work in progress. See [`docs/PLAN.md`](docs/PLAN.md) for the plan.

## Quick start

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then set GEMINI_API_KEY
.venv/bin/uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```
