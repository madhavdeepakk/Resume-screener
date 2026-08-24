"""
database.py
-----------
SQLite persistence layer with composite indexes and strict PRAGMA foreign keys.
"""

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "resume_screener.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    skills TEXT NOT NULL,          -- JSON array
    experience TEXT NOT NULL,      -- JSON array
    education TEXT NOT NULL,       -- JSON array
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    justification TEXT NOT NULL,
    matched_skills TEXT NOT NULL,   -- JSON array
    missing_skills TEXT NOT NULL,   -- JSON array
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(candidate_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_matches_job_score ON matches(job_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_matches_candidate ON matches(candidate_id);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def insert_candidate(filename: str, raw_text: str, structured: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO candidates (filename, raw_text, skills, experience, education)
               VALUES (?, ?, ?, ?, ?)""",
            (
                filename,
                raw_text,
                json.dumps(structured.get("skills", [])),
                json.dumps(structured.get("experience", [])),
                json.dumps(structured.get("education", [])),
            ),
        )
        return cur.lastrowid


def insert_job(title: str, raw_text: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (title, raw_text) VALUES (?, ?)",
            (title, raw_text),
        )
        return cur.lastrowid


def upsert_match(candidate_id: int, job_id: int, result: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO matches (candidate_id, job_id, score, justification, matched_skills, missing_skills)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(candidate_id, job_id) DO UPDATE SET
                 score=excluded.score,
                 justification=excluded.justification,
                 matched_skills=excluded.matched_skills,
                 missing_skills=excluded.missing_skills,
                 created_at=datetime('now')""",
            (
                candidate_id,
                job_id,
                result["score"],
                result["justification"],
                json.dumps(result.get("matched_skills", [])),
                json.dumps(result.get("missing_skills", [])),
            ),
        )
        return cur.lastrowid


def get_candidate(candidate_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        return _candidate_row_to_dict(row) if row else None


def get_job(job_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_candidates() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM candidates ORDER BY id DESC").fetchall()
        return [_candidate_row_to_dict(r) for r in rows]


def list_jobs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def get_shortlist(job_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT m.*, c.filename
               FROM matches m JOIN candidates c ON c.id = m.candidate_id
               WHERE m.job_id = ?
               ORDER BY m.score DESC""",
            (job_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["matched_skills"] = json.loads(d["matched_skills"])
            d["missing_skills"] = json.loads(d["missing_skills"])
            out.append(d)
        return out


def _candidate_row_to_dict(row) -> dict:
    d = dict(row)
    d["skills"] = json.loads(d["skills"])
    d["experience"] = json.loads(d["experience"])
    d["education"] = json.loads(d["education"])
    return d