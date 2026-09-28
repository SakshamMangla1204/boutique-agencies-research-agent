"""Google Sheets writer for the AI agency / AI Engineer job research agent.

Opens the spreadsheet by GOOGLE_SHEET_ID and creates/updates ONLY the two new
worksheets:
  * AI_RECRUITMENT_AGENCIES
  * AI_ENGINEER_JOB_OPENINGS

The spreadsheet's existing worksheet is never referenced: worksheets are
resolved by name via `worksheet(title)`, and creation uses `add_worksheet`, so
the original sheet's data and headers are untouched.

Credentials are reused from the existing loader in `services/sheets_writer.py`
(local credentials.json or GOOGLE_CREDENTIALS_JSON).
"""
from __future__ import annotations

import os
import time

import gspread
from dotenv import load_dotenv

from services.sheets_writer import _load_credentials

load_dotenv()

AGENCY_WORKSHEET = "AI_RECRUITMENT_AGENCIES"
JOB_WORKSHEET = "AI_ENGINEER_JOB_OPENINGS"

DEFAULT_AGENCY_WORKSHEET = "AI_RECRUITMENT_AGENCIES"

AGENCY_HEADERS = [
    "agency_name", "domain", "country", "primary_city", "state", "service_area",
    "ncr_presence", "geographic_tier", "geographic_priority_score", "agency_type",
    "linkedin", "description", "technical_recruitment", "ai_recruitment",
    "genai_recruitment", "contract_staffing", "bulk_hiring", "active_ai_roles",
    "estimated_ai_positions", "ai_roles", "technologies", "client_industries",
    "bulk_hiring_evidence", "founder", "managing_director", "recruitment_head",
    "ai_practice_lead", "agency_email", "recruitment_email",
    "decision_maker_email", "decision_maker_linkedin", "job_urls", "source_urls",
    "evidence_date", "ai_demand_level", "ai_demand_score", "confidence", "status",
    "created_at", "parse_error", "raw",
]

JOB_HEADERS = [
    "agency_name", "agency_domain", "agency_city", "ncr_presence", "job_title",
    "job_role", "company_or_client", "location", "remote_status",
    "employment_type", "experience_required", "salary", "job_url", "source_url",
    "posted_date", "job_relevance", "job_relevance_score", "relevance_reason",
    "required_skills", "preferred_skills", "technologies", "ai_domain", "llm",
    "genai", "rag", "agents", "nlp", "computer_vision", "model_integration",
    "ai_application_development", "fresher_friendly", "status", "created_at",
]

_client = None
_spreadsheet = None


class SheetsUnavailable(RuntimeError):
    """Raised when the spreadsheet cannot be opened (e.g. not shared)."""


def get_sheet_id() -> str:
    return os.getenv("GOOGLE_SHEET_ID", "").strip()


def get_agency_worksheet_title() -> str:
    return os.getenv("GOOGLE_SHEET_WORKSHEET", "").strip() or DEFAULT_AGENCY_WORKSHEET


def get_client():
    global _client

    if _client is None:
        _client = gspread.authorize(_load_credentials())

    return _client


def get_spreadsheet():
    """Open the configured spreadsheet by ID."""
    global _spreadsheet

    if _spreadsheet is not None:
        return _spreadsheet

    sheet_id = get_sheet_id()

    if not sheet_id:
        raise SheetsUnavailable("GOOGLE_SHEET_ID is not set")

    try:
        _spreadsheet = get_client().open_by_key(sheet_id)
    except gspread.exceptions.APIError as exc:
        raise SheetsUnavailable(
            f"Cannot open spreadsheet {sheet_id!r}. Share it with the service "
            f"account as Editor. Original error: {exc}"
        ) from exc
    except Exception as exc:
        raise SheetsUnavailable(f"Cannot open spreadsheet: {exc}") from exc

    return _spreadsheet


def get_or_create_worksheet(title: str, headers: list):
    """Return the named worksheet, creating it with headers when missing."""
    spreadsheet = get_spreadsheet()

    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=title,
            rows=1000,
            cols=max(len(headers), 10),
        )

    _ensure_headers(worksheet, headers)
    return worksheet


def _ensure_headers(worksheet, headers: list) -> None:
    """Write the header row when the worksheet is empty."""
    first_row = worksheet.row_values(1)

    if not first_row:
        worksheet.append_row(headers)
        return

    # If headers exist but differ, keep the existing header row intact and only
    # report the mismatch - never rewrite a populated sheet.
    if [h.strip() for h in first_row[: len(headers)]] != headers:
        print(
            f"  [sheets] NOTE: existing headers in {worksheet.title!r} differ "
            f"from the expected schema; appending in column order."
        )


def _with_retry(func, *args, retries: int = 3, delay: float = 2.0, **kwargs):
    """Retry a Sheets operation on transient errors."""
    last_exc = None

    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            print(f"  [sheets] attempt {attempt}/{retries} failed: {exc}")

            if attempt < retries:
                time.sleep(delay * attempt)

    raise last_exc


def _cell(value) -> str:
    """Render a value for a spreadsheet cell (blank for unknown/None)."""
    if value is None:
        return ""

    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"

    return str(value)


def build_agency_row(data: dict) -> list:
    return [_cell(data.get(header)) for header in AGENCY_HEADERS]


def build_job_row(data: dict) -> list:
    return [_cell(data.get(header)) for header in JOB_HEADERS]


def get_existing_agency_keys() -> set:
    """Normalized domains/names already present in AI_RECRUITMENT_AGENCIES."""
    from services.db.dedupe import normalize_agency_name, normalize_domain

    try:
        worksheet = get_or_create_worksheet(get_agency_worksheet_title(), AGENCY_HEADERS)
    except SheetsUnavailable:
        return set()

    rows = worksheet.get_all_values()

    if not rows:
        return set()

    headers = [h.strip() for h in rows[0]]
    keys: set = set()

    for row in rows[1:]:
        data = dict(zip(headers, row))

        domain_key = normalize_domain(data.get("domain"))

        if domain_key:
            keys.add(domain_key)

        name_key = normalize_agency_name(data.get("agency_name"))

        if name_key:
            keys.add(name_key)

    return keys


def _job_keys(job: dict) -> set:
    """Dedupe keys for one job row: normalized URL and the fallback triple."""
    from services.db.dedupe import normalize_job_url

    url_key = normalize_job_url(job.get("job_url"))

    fallback = "|".join(
        [
            (job.get("agency_name") or "").strip().lower(),
            (job.get("job_title") or "").strip().lower(),
            (job.get("company_or_client") or "").strip().lower(),
            (job.get("location") or "").strip().lower(),
        ]
    )

    return {key for key in (url_key, fallback) if key and key.strip("|")}


def get_existing_job_keys() -> set:
    """Dedupe keys already stored in AI_ENGINEER_JOB_OPENINGS."""
    try:
        worksheet = get_or_create_worksheet(JOB_WORKSHEET, JOB_HEADERS)
    except SheetsUnavailable:
        return set()

    rows = worksheet.get_all_values()

    if not rows:
        return set()

    headers = [h.strip() for h in rows[0]]
    keys: set = set()

    for row in rows[1:]:
        keys |= _job_keys(dict(zip(headers, row)))

    return keys


def write_agency_row(data: dict, skip_if_exists: bool = True) -> bool:
    """Append one agency row. Returns True when a new row was written."""
    from services.db.dedupe import normalize_agency_name, normalize_domain

    worksheet = get_or_create_worksheet(get_agency_worksheet_title(), AGENCY_HEADERS)

    if skip_if_exists:
        existing = get_existing_agency_keys()
        domain_key = normalize_domain(data.get("domain"))
        name_key = normalize_agency_name(data.get("agency_name"))

        if (domain_key and domain_key in existing) or (name_key and name_key in existing):
            print(f"  [sheets] duplicate agency skipped: {data.get('agency_name')}")
            return False

    _with_retry(worksheet.append_row, build_agency_row(data))
    return True


def write_job_rows(jobs: list, skip_if_exists: bool = True) -> int:
    """Append job rows, deduping against the worksheet and within the batch."""
    if not jobs:
        return 0

    worksheet = get_or_create_worksheet(JOB_WORKSHEET, JOB_HEADERS)
    existing = get_existing_job_keys() if skip_if_exists else set()

    rows_to_write = []
    seen_in_batch: set = set()

    for job in jobs:
        candidate_keys = _job_keys(job)

        if skip_if_exists and candidate_keys & existing:
            continue

        if candidate_keys & seen_in_batch:
            continue

        seen_in_batch |= candidate_keys
        rows_to_write.append(build_job_row(job))

    if not rows_to_write:
        return 0

    _with_retry(worksheet.append_rows, rows_to_write)
    return len(rows_to_write)


def sheets_status() -> str:
    """Human-readable status for startup logging."""
    if not get_sheet_id():
        return "disabled (GOOGLE_SHEET_ID is not set)"

    try:
        spreadsheet = get_spreadsheet()
        return f"enabled (spreadsheet: {spreadsheet.title!r})"
    except SheetsUnavailable as exc:
        return f"disabled ({exc})"
