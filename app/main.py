import re
import sqlite3
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analysis, arxiv, db, llm, metadata, pdf
from .config import PDF_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="AI Research Assistant", lifespan=lifespan)


class SearchResult(BaseModel):
    external_id: str
    title: str
    authors: list[str]
    year: int | None = None
    abstract: str | None = None
    url: str | None = None
    pdf_url: str


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search")
async def search(q: str = Query(..., min_length=1, max_length=200)):
    try:
        return await arxiv.search(q)
    except arxiv.ArxivError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/papers")
async def save_paper(paper: SearchResult):
    """Save an arXiv search result, downloading its PDF so the full text is available."""
    existing = db.get_by_external_id(paper.external_id)
    if existing:
        return existing

    pdf_path, full_text, text_error = None, None, None
    try:
        data = await pdf.download(paper.pdf_url)
        safe_id = re.sub(r"[^\w.-]", "_", paper.external_id)
        pdf_path = PDF_DIR / f"arxiv-{safe_id}.pdf"
        pdf_path.write_bytes(data)
        full_text = await run_in_threadpool(pdf.extract_text, data)
    except pdf.PdfError as e:
        text_error = str(e)

    try:
        paper_id = db.insert_paper(
            source="arxiv",
            external_id=paper.external_id,
            title=paper.title,
            authors=paper.authors,
            year=paper.year,
            abstract=paper.abstract,
            url=paper.url,
            pdf_path=str(pdf_path) if pdf_path else None,
            full_text=full_text,
            text_status="ready" if full_text else "failed",
        )
    except sqlite3.IntegrityError:  # saved concurrently by another request
        return db.get_by_external_id(paper.external_id)
    return {**db.get_paper(paper_id), "text_error": text_error}


MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@app.post("/api/upload")
async def upload_paper(file: UploadFile = File(...)):
    """Store an uploaded PDF, extract its text, and pull title/authors/year/abstract with Gemini."""
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF is larger than 50 MB.")

    filename = file.filename or "upload.pdf"
    pdf_path = PDF_DIR / f"upload-{uuid.uuid4().hex}.pdf"
    pdf_path.write_bytes(data)

    try:
        full_text = await run_in_threadpool(pdf.extract_text, data)
        text_error = None
    except pdf.PdfError as e:
        full_text, text_error = None, str(e)

    if full_text:
        meta, meta_warning = await metadata.extract(full_text, data, filename)
    else:
        meta, meta_warning = metadata.fallback("", data, filename), None

    paper_id = db.insert_paper(
        source="upload",
        title=meta["title"],
        authors=meta["authors"],
        year=meta["year"],
        abstract=meta["abstract"],
        pdf_path=str(pdf_path),
        full_text=full_text,
        text_status="ready" if full_text else "failed",
    )
    return {**db.get_paper(paper_id), "text_error": text_error, "metadata_warning": meta_warning}


@app.get("/api/papers")
def list_papers():
    return db.list_papers()


@app.get("/api/papers/{paper_id}")
def get_paper(paper_id: int):
    paper = db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@app.get("/api/papers/{paper_id}/pdf")
def get_paper_pdf(paper_id: int):
    path = db.get_pdf_path(paper_id)
    if not path:
        raise HTTPException(status_code=404, detail="No PDF stored for this paper")
    return FileResponse(path, media_type="application/pdf")


def _require_full_text(paper_id: int) -> str:
    paper = db.get_paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    text = db.get_full_text(paper_id)
    if paper["text_status"] != "ready" or not text:
        raise HTTPException(
            status_code=409,
            detail="This paper's full text is unavailable, so it can't be summarized or questioned. "
            "Upload the PDF to add the full text.",
        )
    return text


@app.post("/api/papers/{paper_id}/summary")
async def summarize_paper(paper_id: int, refresh: bool = False):
    """Summarize from the paper's full text; cached in the DB unless refresh=true."""
    text = _require_full_text(paper_id)
    cached = db.get_paper(paper_id)["summary"]
    if cached and not refresh:
        return {"summary": cached, "cached": True, "truncated": len(text) > analysis.MAX_TEXT_CHARS}
    try:
        summary, truncated = await analysis.summarize(text)
    except llm.LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))
    db.set_summary(paper_id, summary)
    return {"summary": summary, "cached": False, "truncated": truncated}


class Question(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


@app.post("/api/papers/{paper_id}/ask")
async def ask_paper(paper_id: int, body: Question):
    text = _require_full_text(paper_id)
    try:
        reply, truncated = await analysis.answer(text, body.question.strip())
    except llm.LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"question": body.question, "answer": reply, "truncated": truncated}


# Mounted last so /api/* routes take precedence.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
