from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Research Assistant", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Mounted last so /api/* routes take precedence.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
