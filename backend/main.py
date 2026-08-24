"""
main.py
-------
FastAPI entrypoint featuring concurrent async batch scoring with free-tier Gemini API safety limits.
"""

import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import logging
import os

from dotenv import load_dotenv
load_dotenv(override=True)  # Forces overwriting stale environment variables

import os
from fastapi import FastAPI

import database as db
import extraction
import matching

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resume_screener")

MAX_CONCURRENT_LLM_CALLS = 2

app = FastAPI(title="Smart Resume Screener")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()
    logger.info("Database initialized at %s", db.DB_PATH)
    if not os.environ.get("GEMINI_API_KEY"):
        logger.warning("GEMINI_API_KEY is not set.")


class JobCreate(BaseModel):
    title: str
    description: str


@app.post("/jobs")
def create_job(job: JobCreate):
    job_id = db.insert_job(job.title, job.description)
    return {"id": job_id, "title": job.title}


@app.get("/jobs")
def list_jobs():
    return db.list_jobs()


@app.post("/candidates")
async def upload_candidate(file: UploadFile = File(...)):
    if not (file.filename.lower().endswith(".pdf") or file.filename.lower().endswith(".txt")):
        raise HTTPException(400, "Only .pdf and .txt resumes are supported")

    file_bytes = await file.read()
    try:
        raw_text = extraction.extract_raw_text(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(422, str(e))

    try:
        structured = await extraction.structure_resume(raw_text)
    except Exception as e:
        logger.error("LLM extraction failed for %s: %s", file.filename, e)
        raise HTTPException(502, f"Resume parsing failed: {e}")

    candidate_id = db.insert_candidate(file.filename, raw_text, structured)
    return {"id": candidate_id, "filename": file.filename, **structured}


@app.get("/candidates")
def list_candidates():
    return db.list_candidates()


@app.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: int):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


class MatchRequest(BaseModel):
    candidate_id: int
    job_id: int


@app.post("/match")
async def match_one(req: MatchRequest):
    candidate = db.get_candidate(req.candidate_id)
    job = db.get_job(req.job_id)
    if not candidate or not job:
        raise HTTPException(404, "Candidate or Job not found")

    try:
        result = await matching.score_match(candidate, job["raw_text"])
    except Exception as e:
        logger.error("Matching failed: %s", e)
        raise HTTPException(502, f"Matching failed: {e}")

    db.upsert_match(req.candidate_id, req.job_id, result)
    return result


class BulkMatchRequest(BaseModel):
    job_id: int


@app.post("/match/bulk")
async def match_bulk(req: BulkMatchRequest):
    job = db.get_job(req.job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    candidates = db.list_candidates()
    if not candidates:
        return {"job_id": req.job_id, "scored": 0, "failed": [], "shortlist": []}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

    async def worker(candidate):
        async with semaphore:
            try:
                res = await matching.score_match(candidate, job["raw_text"])
                db.upsert_match(candidate["id"], req.job_id, res)
                return None
            except Exception as e:
                logger.error("Matching failed for candidate %s: %s", candidate["id"], e)
                return {"candidate_id": candidate["id"], "error": str(e)}

    results = await asyncio.gather(*[worker(c) for c in candidates])
    errors = [r for r in results if r is not None]

    return {
        "job_id": req.job_id,
        "scored": len(candidates) - len(errors),
        "failed": errors,
        "shortlist": db.get_shortlist(req.job_id),
    }


@app.get("/shortlist/{job_id}")
def shortlist(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return db.get_shortlist(job_id)


frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")