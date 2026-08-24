# Markdown
VIDEO DEMO: https://drive.google.com/file/d/1ZtXmy2MaANo_juMmDusLYgjzzSAAKpmD/view?usp=sharing
# \# Smart Resume Screener

# 

# An intelligent full-stack system that ingests resumes (PDF/Text), extracts structured skills and career history, and scores candidate compatibility against job descriptions using Google's Gemini API.

# 

# \## Architecture \& Data Flow

# 

# \[Resume PDF / Text] ──> \[pdfplumber / OCR] ──> \[Raw Text]

# │

# ▼

# \[Gemini 2.5 Flash]

# (Structured Output)

# │

# ▼

# \[SQLite Database]

# (Candidates \& Jobs)

# │

# ▼

# \[Gemini 2.5 Flash]

# (Scoring \& Rubric)

# │

# ▼

# \[Shortlist View]

# (Ranked Dashboard UI)

# 

# 

# \## Why These Choices?

# 

# \- \*\*Google GenAI SDK (`google-genai`)\*\*: Replaced the Anthropic SDK to leverage Google's free-tier Gemini API.

# \- \*\*Model Choice (`gemini-2.5-flash`)\*\*: Selected for high inference speed, lightweight footprint, robust JSON mode adherence, and inclusion in Google AI Studio's free tier quotas. Centralized as a `MODEL` constant across backend modules.

# \- \*\*Native Structured JSON Output\*\*: Configured requests using `response\\\_mime\\\_type="application/json"` and strict `response\\\_schema` parameters. This eliminates loose formatting variations from LLM output.

# \- \*\*Untrusted Input Defense\*\*: Kept fallback markdown fence stripping (`\\\_parse\\\_json\\\_response`) and strict runtime validation (`\\\_validate\\\_result`) to ensure invalid scores or missing schema keys raise explicit errors before reaching storage.

# \- \*\*Rate-Limit Resiliency\*\*: The Gemini free tier imposes strict RPM/RPD limits. Concurrency is limited (`MAX\\\_CONCURRENT\\\_LLM\\\_CALLS = 2`), combined with automated exponential backoff retries (`3` attempts) for HTTP 429 (`RESOURCE\\\_EXHAUSTED`) status codes.

# 

# \## Setup \& Running

# 

# 1\. \*\*Install Dependencies\*\*:

# &#x20;  ```bash

# &#x20;  python -m venv venv

# &#x20;  source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# &#x20;  pip install -r backend/requirements.txt

# 

