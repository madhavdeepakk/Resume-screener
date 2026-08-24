"""
test_database.py
----------------
Tests database operations (jobs, candidates, matches, shortlist).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import database as db


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Use an isolated temporary database file for each test execution."""
    test_db = tmp_path / "test_screener.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    yield
    if test_db.exists():
        test_db.unlink()


def test_insert_and_list_jobs():
    job_id = db.insert_job("Python Developer", "Experience with FastAPI and relational databases.")
    assert job_id > 0

    jobs = db.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Python Developer"


def test_insert_and_get_candidate():
    structured = {
        "skills": ["Python", "FastAPI"],
        "experience": [{"role": "Dev", "company": "Co", "duration": "2 years", "description": "Backend"}],
        "education": [{"degree": "BS CS", "institution": "Uni", "year": "2024"}]
    }
    cand_id = db.insert_candidate("resume.pdf", "Raw text content", structured)
    assert cand_id > 0

    candidate = db.get_candidate(cand_id)
    assert candidate["filename"] == "resume.pdf"
    assert candidate["skills"] == ["Python", "FastAPI"]


def test_upsert_match_and_shortlist():
    job_id = db.insert_job("Backend Engineer", "Python skills")
    cand_id = db.insert_candidate("john.pdf", "Python dev", {"skills": ["Python"]})

    match_result = {
        "score": 9,
        "justification": "Exact skill alignment.",
        "matched_skills": ["Python"],
        "missing_skills": []
    }
    db.upsert_match(cand_id, job_id, match_result)

    shortlist = db.get_shortlist(job_id)
    assert len(shortlist) == 1
    assert shortlist[0]["candidate_id"] == cand_id
    assert shortlist[0]["score"] == 9