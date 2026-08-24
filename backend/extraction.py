import os
import json
import fitz  # PyMuPDF
from google import genai
from google.genai import types

def extract_raw_text(file_bytes: bytes, filename: str) -> str:
    if filename.lower().endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    
    if filename.lower().endswith(".pdf"):
        text = ""
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text()
        return text.strip()
    
    raise ValueError("Unsupported file format")

async def structure_resume(raw_text: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing")

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are an expert ATS system. Extract key details from this resume text into valid JSON.
    Return ONLY JSON with these exact keys: "skills", "experience", "education".

    - "skills": list of string skills
    - "experience": list of objects containing "role", "company", "duration", "description"
    - "education": list of objects containing "degree", "institution", "year"

    Resume Text:
    {raw_text}
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
        raise ValueError(f"Failed to parse LLM JSON response: {e}")