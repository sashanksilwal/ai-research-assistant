from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import arxiv
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Research Assistant", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/search")
async def search(q: str = Query(..., min_length=1, max_length=200)):
    try:
        return await arxiv.search(q)
    except arxiv.ArxivError as e:
        raise HTTPException(status_code=502, detail=str(e))


# Mounted last so /api/* routes take precedence.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
