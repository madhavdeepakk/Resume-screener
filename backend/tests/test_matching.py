"""
test_matching.py
-----------------
Tests the scoring/validation logic in matching.py against realistic
MOCKED LLM responses, including ones that violate the schema (missing
keys, out-of-range scores, wrong types) -- these are the failure modes
_validate_result() exists to catch before bad data reaches the database.

Run: pytest backend/tests/test_matching.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import matching


def _fake_response(text: str):
    """Build an object shaped like a Gemini GenerateContentResponse."""
    resp = MagicMock()
    resp.text = text
    return resp


SAMPLE_CANDIDATE = {
    "skills": ["Python", "FastAPI", "PostgreSQL"],
    "experience": [
        {"role": "Backend Engineer", "company": "Acme", "duration": "2022-Present", "description": "Built APIs"}
    ],
    "education": [{"degree": "B.S. CS", "institution": "UW", "year": "2020"}],
}

SAMPLE_JOB_TEXT = "Backend Engineer role requiring Python, FastAPI, and PostgreSQL."


class TestValidateResult:
    def test_valid_result_passes(self):
        result = {
            "score": 8,
            "justification": "Strong match on core stack.",
            "matched_skills": ["Python", "FastAPI"],
            "missing_skills": [],
        }
        matching._validate_result(result)  # should not raise

    def test_missing_key_raises(self):
        result = {"score": 8, "justification": "ok", "matched_skills": []}
        with pytest.raises(ValueError, match="missing keys"):
            matching._validate_result(result)

    def test_score_out_of_range_raises(self):
        result = {"score": 15, "justification": "ok", "matched_skills": [], "missing_skills": []}
        with pytest.raises(ValueError, match="invalid score"):
            matching._validate_result(result)

    def test_score_zero_raises(self):
        result = {"score": 0, "justification": "ok", "matched_skills": [], "missing_skills": []}
        with pytest.raises(ValueError, match="invalid score"):
            matching._validate_result(result)

    def test_score_as_string_raises(self):
        """LLMs sometimes return "8" instead of 8 -- must be caught, not silently coerced."""
        result = {"score": "8", "justification": "ok", "matched_skills": [], "missing_skills": []}
        with pytest.raises(ValueError, match="invalid score"):
            matching._validate_result(result)

    def test_score_as_float_raises(self):
        result = {"score": 8.5, "justification": "ok", "matched_skills": [], "missing_skills": []}
        with pytest.raises(ValueError, match="invalid score"):
            matching._validate_result(result)


class TestBuildMatchUserPrompt:
    def test_includes_job_text_and_candidate_data(self):
        prompt = matching.build_match_user_prompt(SAMPLE_CANDIDATE, SAMPLE_JOB_TEXT)
        assert SAMPLE_JOB_TEXT in prompt
        assert "Python" in prompt
        assert "Backend Engineer" in prompt


class TestScoreMatch:
    @pytest.mark.asyncio
    @patch('matching.genai.Client')
    async def test_well_formed_response(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_fake_response("""
            {
              "score": 9,
              "justification": "Candidate has direct experience with Python, FastAPI, and PostgreSQL matching all core requirements.",
              "matched_skills": ["Python", "FastAPI", "PostgreSQL"],
              "missing_skills": []
            }
            """)
        )
        result = await matching.score_match(SAMPLE_CANDIDATE, SAMPLE_JOB_TEXT)
        assert result["score"] == 9
        assert "PostgreSQL" in result["matched_skills"]

    @pytest.mark.asyncio
    @patch("matching.genai.Client")
    async def test_response_with_invalid_score_raises(self, mock_client_cls):
        """If the LLM violates its own schema, score_match must fail loudly
        (caught upstream and reported), not silently store garbage."""
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_fake_response("""
            {"score": 42, "justification": "way too high", "matched_skills": [], "missing_skills": []}
            """)
        )
        with pytest.raises(ValueError):
            await matching.score_match(SAMPLE_CANDIDATE, SAMPLE_JOB_TEXT)

    @pytest.mark.asyncio
    @patch("matching.genai.Client")
    async def test_response_missing_field_raises(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_fake_response(
                '{"score": 7, "justification": "ok"}'
            )
        )
        with pytest.raises(ValueError):
            await matching.score_match(SAMPLE_CANDIDATE, SAMPLE_JOB_TEXT)

    @pytest.mark.asyncio
    @patch("matching.genai.Client")
    async def test_markdown_fenced_response_still_works(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=_fake_response(
                '```json\n{"score": 6, "justification": "Partial match.", "matched_skills": ["Python"], "missing_skills": ["PostgreSQL"]}\n```'
            )
        )
        result = await matching.score_match(SAMPLE_CANDIDATE, SAMPLE_JOB_TEXT)
        assert result["score"] == 6