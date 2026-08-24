"""
test_extraction.py
-------------------
Tests the parsing/validation logic in extraction.py against realistic
MOCKED LLM responses (including malformed ones). This does not require
a live GEMINI_API_KEY and does not verify actual model output quality
-- it verifies the code correctly handles the shapes of responses a real
call could plausibly return, including the failure modes.

Run: pytest backend/tests/test_extraction.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import extraction


def _fake_response(text: str):
    """Build an object shaped like a Gemini GenerateContentResponse."""
    resp = MagicMock()
    resp.text = text
    return resp


class TestParseJsonResponse:
    def test_clean_json(self):
        result = extraction._parse_json_response('{"skills": ["Python"]}')
        assert result == {"skills": ["Python"]}

    def test_json_wrapped_in_markdown_fences(self):
        text = '```json\n{"skills": ["Python", "SQL"]}\n```'
        result = extraction._parse_json_response(text)
        assert result == {"skills": ["Python", "SQL"]}

    def test_json_wrapped_in_bare_fences(self):
        text = '```\n{"skills": []}\n```'
        result = extraction._parse_json_response(text)
        assert result == {"skills": []}

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="did not return valid JSON"):
            extraction._parse_json_response("this is not json at all")

    def test_truncated_json_raises_value_error(self):
        with pytest.raises(ValueError):
            extraction._parse_json_response('{"skills": ["Python"')


class TestStructureResume:
    @pytest.mark.asyncio
    @patch("extraction.genai.Client")
    async def test_well_formed_response(self, mock_client_cls):
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.aio.models.generate_content = AsyncMock(
            return_value=_fake_response("""
            {
              "skills": ["Python", "FastAPI", "PostgreSQL"],
              "experience": [
                {"role": "Backend Engineer", "company": "Acme", "duration": "2022-Present", "description": "Built APIs"}
              ],
              "education": [
                {"degree": "B.S. Computer Science", "institution": "UW", "year": "2020"}
              ]
            }
            """)
        )

        result = await extraction.structure_resume("some raw resume text")

        assert result["skills"] == ["Python", "FastAPI", "PostgreSQL"]
        assert len(result["experience"]) == 1
        assert result["experience"][0]["role"] == "Backend Engineer"
        assert len(result["education"]) == 1

    @pytest.mark.asyncio
    @patch("extraction.genai.Client")
    async def test_markdown_wrapped_response_still_parses(self, mock_client_cls):
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.aio.models.generate_content = AsyncMock(
            return_value=_fake_response(
                '```json\n{"skills": ["Java"], "experience": [], "education": []}\n```'
            )
        )

        result = await extraction.structure_resume("raw text")

        assert result["skills"] == ["Java"]

    @pytest.mark.asyncio
    @patch("extraction.genai.Client")
    async def test_malformed_llm_output_raises(self, mock_client_cls):
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.aio.models.generate_content = AsyncMock(
            return_value=_fake_response("I cannot parse this resume.")
        )

        with pytest.raises(ValueError):
            await extraction.structure_resume("raw text")


class TestExtractRawText:
    def test_plain_text_file(self):
        text = extraction.extract_raw_text(b"Jane Doe\nSkills: Python", "resume.txt")
        assert text == "Jane Doe\nSkills: Python"

    def test_empty_text_file(self):
        text = extraction.extract_raw_text(b"", "resume.txt")
        assert text == ""

    def test_real_pdf_extracts_text(self):
        """Regression check against a real PDF, not a mock -- this part
        doesn't touch the LLM so it's safe to test for real."""
        pdf_path = Path("/mnt/user-data/uploads/smart_resume_screener__1_.pdf")
        if not pdf_path.exists():
            pytest.skip("sample PDF not present in this environment")
        text = extraction.extract_raw_text(pdf_path.read_bytes(), "test.pdf")
        assert "Smart Resume Screener" in text
        assert len(text) > 100