"""ResearchOS API — thin FastAPI layer over the existing research pipeline.

All API keys and Google credentials remain server-side. The browser only
receives job state summaries and the spreadsheet navigation URL.
"""
import os
import threading
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from main import run_research_pipeline
from services.sheets_writer import get_sheet

app = FastAPI(title="ResearchOS API", version="1.0.0")

# Local development origins are always allowed. The deployed Vercel frontend
# origin is provided via the FRONTEND_URL environment variable (set on Render).
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

_frontend_url = os.getenv("FRONTEND_URL", "").strip()

if _frontend_url:
    ALLOWED_ORIGINS.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Job store (in-memory for this stage; no Redis/Celery/DB).
# ---------------------------------------------------------------------------

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()

VALID_ENTITY_TYPES = {"company", "college", "vc_firm", "startup", "job", "custom"}
DEFAULT_FIELDS = ["company_name", "website", "linkedin", "description"]
MAX_RESULTS_HARD_LIMIT = 50


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    entity_type: str = "company"
    fields: list[str] = Field(default_factory=lambda: list(DEFAULT_FIELDS))
    max_results: int = Field(10, ge=1, le=MAX_RESULTS_HARD_LIMIT)


def _job_summary(job: dict) -> dict:
    return {
        "status": job.get("status"),
        "stage": job.get("stage"),
        "discovered": job.get("discovered", 0),
        "processed": job.get("processed", 0),
        "written": job.get("written", 0),
        "duplicates": job.get("duplicates", 0),
        "failed": job.get("failed", 0),
        "stop_reason": job.get("stop_reason"),
        "error": job.get("error"),
        "sheet_url": job.get("sheet_url"),
        "entities": job.get("entities", []),
        "failed_entities": job.get("failed_entities", []),
        "logs": job.get("logs", []),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


def _append_log(job: dict, stage: str, message: str) -> None:
    """Append a timestamped log entry to the job's log stream."""
    logs = job.setdefault("logs", [])
    logs.append({
        "ts": time.time(),
        "stage": stage,
        "message": message,
    })


def _make_callback(job_id: str):
    """Build the progress callback bridging run_research_pipeline -> job store."""

    def cb(stage: str, data: dict):
        with _LOCK:
            job = JOBS[job_id]

            if stage == "startup":
                job["stage"] = "sheets"
                job["known_entities"] = data.get("known_entities", 0)
                _append_log(
                    job,
                    "sheets",
                    f"Loaded {data.get('known_entities', 0)} existing entities from Google Sheets",
                )

            elif stage == "discovery_start":
                job["stage"] = "discovery"
                _append_log(
                    job,
                    "discovery",
                    f"Discovery batch {data.get('batch', '?')} started",
                )

            elif stage == "discovery":
                job["discovered"] = data.get("found", job.get("discovered", 0))
                _append_log(
                    job,
                    "discovery",
                    f"Discovered {data.get('found', 0)} entities in batch {data.get('batch', '?')}",
                )

            elif stage == "discovery_filter":
                job["duplicates"] = job.get("duplicates", 0) + data.get(
                    "existing", 0
                )
                _append_log(
                    job,
                    "dedup",
                    f"{data.get('new', 0)} new entities after filtering "
                    f"({data.get('existing', 0)} already known)",
                )

            elif stage == "entity_start":
                job["stage"] = "research"
                job["current_entity"] = data.get("entity")
                _append_log(
                    job,
                    "research",
                    f"Processing: {data.get('entity', '?')} "
                    f"({data.get('index', '?')}/{data.get('total', '?')})",
                )

            elif stage == "entity_processed":
                job["stage"] = "extraction"
                job["processed"] = job.get("processed", 0) + 1
                _append_log(
                    job,
                    "extraction",
                    f"Extracting requested fields for {data.get('entity', '?')}",
                )

            elif stage == "entity_written":
                job["stage"] = "sheets"
                job["written"] = job.get("written", 0) + 1
                entities = job.get("entities", [])
                entities.append(data.get("entity"))
                job["entities"] = entities
                _append_log(
                    job,
                    "sheets",
                    f"Row written successfully for {data.get('entity', '?')}",
                )

            elif stage == "entity_duplicate":
                job["stage"] = "sheets"
                job["duplicates"] = job.get("duplicates", 0) + 1
                _append_log(
                    job,
                    "sheets",
                    f"Skipped duplicate: {data.get('entity', '?')}",
                )

            elif stage == "entity_failed":
                job["failed"] = job.get("failed", 0) + 1
                failed_entities = job.get("failed_entities", [])
                failed_entities.append(
                    {"entity": data.get("entity"), "reason": data.get("reason")}
                )
                job["failed_entities"] = failed_entities
                _append_log(
                    job,
                    "error",
                    f"Failed {data.get('entity', '?')}: {data.get('reason', 'unknown error')}",
                )

            elif stage == "complete":
                job["status"] = "complete"
                job["stage"] = "complete"
                job["stop_reason"] = data.get("stop_reason")
                job["discovered"] = data.get("total_discovered", job.get("discovered", 0))
                job["processed"] = data.get("entities_processed", job.get("processed", 0))
                job["written"] = data.get("written", job.get("written", 0))
                job["duplicates"] = data.get("duplicates_skipped_level1", 0) + data.get(
                    "duplicates_skipped_level2", 0
                )
                job["failed"] = data.get("failed", job.get("failed", 0))
                job["entities"] = data.get("discovered_entities", job.get("entities", []))
                job["failed_entities"] = [
                    {"entity": e, "reason": r}
                    for e, r in data.get("failed_entities", [])
                ]
                try:
                    job["sheet_url"] = get_sheet().url
                except Exception:
                    job["sheet_url"] = None
                _append_log(
                    job,
                    "complete",
                    f"Pipeline complete — {data.get('written', 0)} rows written, "
                    f"{data.get('failed', 0)} failed",
                )

            elif stage == "pipeline_failed":
                job["status"] = "failed"
                job["stage"] = "failed"
                job["stop_reason"] = data.get("stop_reason")
                job["error"] = data.get("error")
                _append_log(
                    job,
                    "error",
                    f"Pipeline failed: {data.get('error', 'unknown error')}",
                )

            elif stage == "startup_failed":
                job["status"] = "failed"
                job["stage"] = "failed"
                job["error"] = data.get("error")
                _append_log(
                    job,
                    "error",
                    f"Startup failed: {data.get('error', 'unknown error')}",
                )

            job["updated_at"] = time.time()

    return cb


def _run_job(job_id: str, request: ResearchRequest):
    config = {
        "query": request.query,
        "entity_type": request.entity_type,
        "fields": request.fields,
        "max_results": request.max_results,
    }

    try:
        run_research_pipeline(config, progress_callback=_make_callback(job_id))
    except Exception as exc:
        with _LOCK:
            job = JOBS[job_id]
            job["status"] = "failed"
            job["stage"] = "failed"
            job["error"] = str(exc)
            _append_log(job, "error", f"Unexpected error: {exc}")
            job["updated_at"] = time.time()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "researchos"}


@app.post("/api/research")
def start_research(request: ResearchRequest):
    if request.fields and len(request.fields) > 20:
        raise HTTPException(status_code=400, detail="Too many fields (max 20).")

    if request.entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type. Must be one of: {sorted(VALID_ENTITY_TYPES)}",
        )

    job_id = uuid.uuid4().hex

    with _LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "running",
            "stage": "startup",
            "request": request.model_dump(),
            "discovered": 0,
            "processed": 0,
            "written": 0,
            "duplicates": 0,
            "failed": 0,
            "known_entities": 0,
            "stop_reason": None,
            "error": None,
            "sheet_url": None,
            "entities": [],
            "failed_entities": [],
            "current_entity": None,
            "logs": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        _append_log(JOBS[job_id], "start", f"JOB STARTED — Query: {request.query}")

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, request),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/api/research/{job_id}")
def get_research_job(job_id: str):
    job = JOBS.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return _job_summary(job)