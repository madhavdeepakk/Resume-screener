"""
test_routes.py
--------------
End-to-end route tests for FastAPI endpoints in main.py.
Mocks out database interactions and extraction/matching modules.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

MOCK_STRUCTURED_CANDIDATE = {
    "skills": ["Python", "FastAPI"],
    "experience": [{"role": "Developer", "company": "Tech Corp", "duration": "2023-Present", "description": "Backend dev"}],
    "education": [{"degree": "B.Tech CS", "institution": "University", "year": "2024"}]
}

MOCK_MATCH_SCORE = {
    "score": 8,
    "justification": "Strong match for backend role.",
    "matched_skills": ["Python", "FastAPI"],
    "missing_skills": []
}


class TestCandidateRoutes:
    @patch("database.insert_candidate", return_value=1)
    @patch("extraction.structure_resume", new_callable=AsyncMock)
    @patch("extraction.extract_raw_text", return_value="Jane Doe\nSkills: Python, FastAPI")
    def test_upload_candidate_success(self, mock_extract, mock_structure, mock_db_insert):
        mock_structure.return_value = MOCK_STRUCTURED_CANDIDATE

        file_bytes = b"Jane Doe\nSkills: Python, FastAPI"
        response = client.post(
            "/candidates",
            files={"file": ("resume.txt", file_bytes, "text/plain")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["filename"] == "resume.txt"
        assert data["skills"] == ["Python", "FastAPI"]

    def test_upload_candidate_invalid_extension(self):
        file_bytes = b"binary content"
        response = client.post(
            "/candidates",
            files={"file": ("resume.exe", file_bytes, "application/octet-stream")}
        )
        assert response.status_code == 400
        assert "Only .pdf and .txt resumes are supported" in response.json()["detail"]


class TestMatchRoutes:
    @patch("database.upsert_match")
    @patch("database.get_job", return_value={"id": 1, "title": "Backend Dev", "raw_text": "Python FastAPI role"})
    @patch("database.get_candidate", return_value={"id": 1, "skills": ["Python"]})
    @patch("matching.score_match", new_callable=AsyncMock)
    def test_match_one_success(self, mock_score, mock_get_cand, mock_get_job, mock_upsert):
        mock_score.return_value = MOCK_MATCH_SCORE

        payload = {"candidate_id": 1, "job_id": 1}
        response = client.post("/match", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["score"] == 8
        mock_score.assert_called_once()

    @patch("database.get_candidate", return_value=None)
    @patch("database.get_job", return_value=None)
    def test_match_one_not_found(self, mock_get_job, mock_get_cand):
        payload = {"candidate_id": 99, "job_id": 99}
        response = client.post("/match", json=payload)

        assert response.status_code == 404
        assert "Candidate or Job not found" in response.json()["detail"]


class TestBulkMatchRoute:
    @patch("database.get_shortlist", return_value=[{"candidate_id": 1, "score": 8, "filename": "resume.txt", "justification": "Strong match", "matched_skills": ["Python"], "missing_skills": []}])
    @patch("database.upsert_match")
    @patch("database.list_candidates", return_value=[{"id": 1, "raw_text": "Resume text"}])
    @patch("database.get_job", return_value={"id": 1, "title": "Backend Dev", "raw_text": "Python FastAPI role"})
    @patch("matching.score_match", new_callable=AsyncMock)
    def test_match_bulk_success(self, mock_score, mock_get_job, mock_list_cand, mock_upsert, mock_shortlist):
        mock_score.return_value = MOCK_MATCH_SCORE

        payload = {"job_id": 1}
        response = client.post("/match/bulk", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == 1
        assert data["scored"] == 1
        assert len(data["shortlist"]) == 1

    @patch("database.get_job", return_value=None)
    def test_match_bulk_job_not_found(self, mock_get_job):
        payload = {"job_id": 99}
        response = client.post("/match/bulk", json=payload)

        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]