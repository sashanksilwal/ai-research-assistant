import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL CHECK (source IN ('arxiv', 'upload')),
    external_id TEXT UNIQUE,              -- arXiv id; NULL for uploads
    title       TEXT NOT NULL,
    authors     TEXT NOT NULL DEFAULT '[]',  -- JSON list of names
    year        INTEGER,
    abstract    TEXT,
    url         TEXT,
    pdf_path    TEXT,
    full_text   TEXT,
    text_status TEXT NOT NULL DEFAULT 'failed' CHECK (text_status IN ('ready', 'failed')),
    summary     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
