"""
test_screener.py
----------------
Pytest suite covering JSON parsing, schema validation, error handling, and exponential backoff retry logic.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from google.genai.errors import APIError

from extraction import _parse_json_response as parse_extraction_json, structure_resume
from matching import _parse_json_response as parse_matching_json, _validate_result, score_match


def test_valid_extraction_json_parsing():
    raw_response = """{
        "skills": ["Python", "FastAPI", "SQLite"],
        "experience": [{"role": "Backend Engineer", "company": "Tech Corp", "duration": "2022-Present", "description": "Built APIs"}],
        "education": [{"degree": "BS CS", "institution": "State University", "year": "2022"}]
    }"""
    parsed = parse_extraction_json(raw_response)
    assert parsed["skills"] == ["Python", "FastAPI", "SQLite"]
    assert len(parsed["experience"]) == 1
    assert parsed["education"][0]["degree"] == "BS CS"


def test_markdown_fenced_json_parsing():
    raw_response = """```json
    {
        "score": 8,
        "justification": "Strong match with relevant experience.",
        "matched_skills": ["Python", "FastAPI"],
        "missing_skills": ["Docker"]
    }
    ```"""
    parsed = parse_matching_json(raw_response)
    assert parsed["score"] == 8
    assert parsed["matched_skills"] == ["Python", "FastAPI"]
    _validate_result(parsed)


def test_missing_required_keys_raises_value_error():
    incomplete_result = {
        "score": 7,
        "justification": "Good candidate.",
        "matched_skills": ["Python"]
        # Missing 'missing_skills'
    }
    with pytest.raises(ValueError, match="LLM match response missing keys"):
        _validate_result(incomplete_result)


def test_out_of_range_score_high_raises_value_error():
    invalid_result = {
        "score": 11,
        "justification": "Overqualified candidate.",
        "matched_skills": ["Python"],
        "missing_skills": []
    }
    with pytest.raises(ValueError, match="LLM returned invalid score: 11"):
        _validate_result(invalid_result)


def test_out_of_range_score_low_raises_value_error():
    invalid_result = {
        "score": 0,
        "justification": "No relevant background.",
        "matched_skills": [],
        "missing_skills": ["Python"]
    }
    with pytest.raises(ValueError, match="LLM returned invalid score: 0"):
        _validate_result(invalid_result)


def test_wrong_type_string_score_raises_value_error():
    invalid_result = {
        "score": "8",
        "justification": "Good match.",
        "matched_skills": ["Python"],
        "missing_skills": []
    }
    with pytest.raises(ValueError, match="LLM returned invalid score: 8"):
        _validate_result(invalid_result)


def test_wrong_type_float_score_raises_value_error():
    invalid_result = {
        "score": 8.5,
        "justification": "Solid fit.",
        "matched_skills": ["Python"],
        "missing_skills": []
    }
    with pytest.raises(ValueError, match="LLM returned invalid score: 8.5"):
        _validate_result(invalid_result)


def test_truncated_json_raises_value_error():
    truncated_response = '{"score": 8, "justification": "Incomplete string...'
    with pytest.raises(ValueError, match="LLM did not return valid JSON"):
        parse_matching_json(truncated_response)


@pytest.mark.asyncio
async def test_retry_on_simulated_429():
    mock_client = AsyncMock()
    
    # First call raises rate limit, second call succeeds
    error_429 = APIError(429, "Rate limit exceeded 429 RESOURCE_EXHAUSTED", response=None)
    success_response = AsyncMock()
    success_response.text = '{"skills": ["Python"], "experience": [], "education": []}'
    
    mock_client.aio.models.generate_content.side_effect = [error_429, success_response]
    
    with patch("extraction.get_client", return_value=mock_client), patch("asyncio.sleep", return_value=None):
        result = await structure_resume("Sample resume text", max_retries=3, base_backoff=0.01)
        assert result["skills"] == ["Python"]
        assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts():
    mock_client = AsyncMock()
    error_429 = error_429 = APIError(429, "Rate limit exceeded 429 RESOURCE_EXHAUSTED", response=None)
    mock_client.aio.models.generate_content.side_effect = error_429

    with patch("matching.get_client", return_value=mock_client), patch("asyncio.sleep", return_value=None):
        candidate = {"skills": ["Python"], "experience": [], "education": []}
        with pytest.raises(RuntimeError, match="Gemini API rate limit reached"):
            await score_match(candidate, "Job text requiring Python", max_retries=3, base_backoff=0.01)
        assert mock_client.aio.models.generate_content.call_count == 3