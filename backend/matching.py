import os
import json
from google import genai
from google.genai import types

async def score_match(candidate: dict, job_description: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing")

    client = genai.Client(api_key=api_key)

    prompt = f"""
    Evaluate candidate suitability for the following job description.
    Return ONLY a JSON object with these exact keys:
    - "score": integer scale 1 to 10
    - "justification": short string explaining the rating
    - "matched_skills": list of matching skills found in candidate profile
    - "missing_skills": list of skills required by job but missing in candidate profile

    Job Description:
    {job_description}

    Candidate Profile:
    {json.dumps(candidate)}
    """

    response = await client.aio.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    try:
        return json.loads(response.text)
    except Exception as e:
        raise ValueError(f"Failed to parse LLM matching response: {e}")