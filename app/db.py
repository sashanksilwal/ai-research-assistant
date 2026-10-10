import json
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

# Columns returned to the frontend; full_text stays server-side (only its length is exposed).
PUBLIC_COLUMNS = """
    id, source, external_id, title, authors, year, abstract, url, pdf_path,
    text_status, summary, created_at, length(full_text) AS text_chars
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Columns added after the first release; init_db adds any that an existing database lacks.
ADDED_COLUMNS = {
    "openalex_id": "TEXT",
    "openalex_refs": "TEXT",     # JSON list of OpenAlex work ids this paper cites
    "openalex_status": "TEXT",   # NULL = not looked up yet; 'ok' | 'not_found' | 'error'
    "s2_refs": "TEXT",           # JSON list of {"arxiv", "title"} this paper cites (Semantic Scholar)
    "s2_status": "TEXT",         # NULL = not looked up yet; 'ok' | 'not_found' | 'error'
}


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(papers)")}
        for name, sql_type in ADDED_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE papers ADD COLUMN {name} {sql_type}")


def _to_paper(row: sqlite3.Row) -> dict:
    paper = dict(row)
    paper["authors"] = json.loads(paper["authors"])
    paper["pdf_url"] = f"/api/papers/{paper['id']}/pdf" if paper.pop("pdf_path") else None
    return paper


def list_papers() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT {PUBLIC_COLUMNS} FROM papers ORDER BY id DESC").fetchall()
    return [_to_paper(r) for r in rows]


def get_paper(paper_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {PUBLIC_COLUMNS} FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return _to_paper(row) if row else None


def get_by_external_id(external_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {PUBLIC_COLUMNS} FROM papers WHERE external_id = ?", (external_id,)).fetchone()
    return _to_paper(row) if row else None


def get_pdf_path(paper_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT pdf_path FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return row["pdf_path"] if row else None


def delete_paper(paper_id: int) -> tuple[bool, str | None]:
    """Remove a paper's row; return (whether it existed, its stored PDF path)."""
    with connect() as conn:
        row = conn.execute("SELECT pdf_path FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if not row:
            return False, None
        conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    return True, row["pdf_path"]


def insert_paper(**fields) -> int:
    fields["authors"] = json.dumps(fields.get("authors", []))
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO papers ({cols}) VALUES ({marks})", tuple(fields.values()))
    return cur.lastrowid


def get_full_text(paper_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT full_text FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return row["full_text"] if row else None


def set_summary(paper_id: int, summary: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE papers SET summary = ? WHERE id = ?", (summary, paper_id))


def papers_needing_openalex() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title FROM papers WHERE openalex_status IS NULL OR openalex_status = 'error'"
        ).fetchall()
    return [dict(r) for r in rows]


def set_openalex(paper_id: int, status: str, openalex_id: str | None, refs: list[str]) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE papers SET openalex_status = ?, openalex_id = ?, openalex_refs = ? WHERE id = ?",
            (status, openalex_id, json.dumps(refs), paper_id),
        )


def papers_needing_s2() -> list[dict]:
    """arXiv papers whose Semantic Scholar references have not been fetched (or last fetch errored)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, external_id FROM papers WHERE external_id IS NOT NULL"
            " AND (s2_status IS NULL OR s2_status = 'error')"
        ).fetchall()
    return [dict(r) for r in rows]


def set_s2(paper_id: int, status: str, refs: list[dict]) -> None:
    with connect() as conn:
        conn.execute("UPDATE papers SET s2_status = ?, s2_refs = ? WHERE id = ?", (status, json.dumps(refs), paper_id))


def papers_for_graph() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, external_id, title, year, source, openalex_id, openalex_refs, openalex_status,"
            " s2_refs, s2_status FROM papers ORDER BY id"
        ).fetchall()
    return [
        {**dict(r), "openalex_refs": json.loads(r["openalex_refs"] or "[]"), "s2_refs": json.loads(r["s2_refs"] or "[]")}
        for r in rows
    ]
