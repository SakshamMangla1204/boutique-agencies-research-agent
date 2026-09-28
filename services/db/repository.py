"""Database repository: upsert agencies, job openings, contacts, sources.

Every write is idempotent.  Deduplication follows the project spec:

Job openings
  primary  : normalized_job_url
  fallback : agency_id + normalized job_title + company_or_client + location

Agencies
  primary  : normalized domain
  fallback : normalized agency name

When the database is unavailable (no DATABASE_URL) every function returns a
safe "skipped" result so the pipeline can continue in Sheets-only mode.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from services.db import dedupe
from services.db import session

from services.db.models import (
    Agency,
    Contact,
    HiringDemand,
    JobOpening,
    ResearchSource,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def find_agency(db, normalized_domain: str, normalized_name: str) -> Optional[Agency]:
    """Find an existing agency by domain (primary) then name (fallback)."""
    if normalized_domain:
        found = (
            db.query(Agency)
            .filter(Agency.normalized_domain == normalized_domain)
            .one_or_none()
        )

        if found:
            return found

    if normalized_name:
        return (
            db.query(Agency)
            .filter(Agency.normalized_name == normalized_name)
            .one_or_none()
        )

    return None


def find_job(db, normalized_job_url, agency_id, fallback_key) -> Optional[JobOpening]:
    """Find an existing job opening by URL (primary) then the fallback key."""
    if normalized_job_url:
        found = (
            db.query(JobOpening)
            .filter(JobOpening.normalized_job_url == normalized_job_url)
            .one_or_none()
        )

        if found:
            return found

    if agency_id is not None and fallback_key:
        return (
            db.query(JobOpening)
            .filter(
                JobOpening.agency_id == agency_id,
                JobOpening.dedupe_fallback_key == fallback_key,
            )
            .one_or_none()
        )

    return None


def agency_exists(normalized_domain: str, normalized_name: str) -> bool:
    """Database existence check used before expensive agency research."""
    db = get_session_or_none()

    if db is None:
        return False

    try:
        return find_agency(db, normalized_domain, normalized_name) is not None
    finally:
        db.close()


def get_session_or_none():
    """Return a session, or None when the DB is disabled."""
    if not session.is_db_enabled():
        return None

    return session.get_session()


def upsert_agency(db, agency: dict) -> tuple:
    """Insert or update an agency. Returns (Agency, created_bool)."""
    normalized_domain = dedupe.normalize_domain(agency.get("domain"))
    normalized_name = dedupe.normalize_agency_name(agency.get("agency_name"))

    existing = find_agency(db, normalized_domain, normalized_name)

    fields = {
        "agency_name": agency.get("agency_name") or "",
        "normalized_name": normalized_name,
        "domain": agency.get("domain") or None,
        "normalized_domain": normalized_domain or None,
        "country": agency.get("country") or None,
        "primary_city": agency.get("primary_city") or None,
        "state": agency.get("state") or None,
        "service_area": agency.get("service_area") or None,
        "ncr_presence": agency.get("ncr_presence") or None,
        "agency_type": agency.get("agency_type") or None,
        "linkedin": agency.get("linkedin") or None,
        "description": agency.get("description") or None,
        "geographic_tier": agency.get("geographic_tier") or None,
        "geographic_priority_score": agency.get("geographic_priority_score"),
    }

    if existing:
        for key, value in fields.items():
            # Never overwrite a known value with an empty one.
            if value in (None, ""):
                continue

            setattr(existing, key, value)

        existing.updated_at = _utc_now()
        return existing, False

    record = Agency(**fields)
    db.add(record)
    db.flush()
    return record, True


def upsert_hiring_demand(db, agency_id: int, demand: dict, score: int, level: str):
    """Insert or update the hiring_demand row for an agency."""
    existing = (
        db.query(HiringDemand)
        .filter(HiringDemand.agency_id == agency_id)
        .one_or_none()
    )

    if existing is None:
        existing = HiringDemand(agency_id=agency_id)
        db.add(existing)

    for key in (
        "technical_recruitment",
        "ai_recruitment",
        "genai_recruitment",
        "contract_staffing",
        "bulk_hiring",
        "active_ai_roles",
        "estimated_ai_positions",
        "ai_roles",
        "technologies",
        "client_industries",
        "bulk_hiring_evidence",
        "evidence_date",
    ):
        value = demand.get(key)

        if value in (None, ""):
            continue

        setattr(existing, key, value)

    existing.ai_demand_score = score
    existing.ai_demand_level = level

    db.flush()
    return existing


def upsert_source(db, agency_id: int, source: dict):
    """Insert a research source if it is not already recorded."""
    url = (source.get("source_url") or "").strip()

    if not url:
        return None

    existing = (
        db.query(ResearchSource)
        .filter(
            ResearchSource.agency_id == agency_id,
            ResearchSource.source_url == url,
        )
        .one_or_none()
    )

    if existing:
        return existing

    record = ResearchSource(
        agency_id=agency_id,
        source_url=url,
        source_type=source.get("source_type") or None,
        source_title=source.get("source_title") or None,
    )
    db.add(record)
    db.flush()
    return record


def upsert_contact(db, agency_id: int, contact: dict):
    """Insert a contact if the (agency, name, role) triple is new."""
    name = (contact.get("name") or "").strip()
    role = (contact.get("role") or "").strip()

    if not name and not (contact.get("email") or "").strip():
        return None

    existing = (
        db.query(Contact)
        .filter(
            Contact.agency_id == agency_id,
            Contact.name == (name or None),
            Contact.role == (role or None),
        )
        .one_or_none()
    )

    if existing:
        # Fill in newly discovered public details, never blank out existing ones.
        for key in ("linkedin", "email", "email_type", "source_url"):
            value = contact.get(key)

            if value and not getattr(existing, key):
                setattr(existing, key, value)

        return existing

    record = Contact(
        agency_id=agency_id,
        name=name or None,
        role=role or None,
        linkedin=contact.get("linkedin") or None,
        email=contact.get("email") or None,
        email_type=contact.get("email_type") or None,
        source_url=contact.get("source_url") or None,
    )
    db.add(record)
    db.flush()
    return record


def upsert_job_opening(db, agency_id, job: dict) -> tuple:
    """Insert or update a job opening. Returns (JobOpening, created_bool)."""
    normalized_url = dedupe.normalize_job_url(job.get("job_url"))
    fallback_key = dedupe.job_dedupe_fallback_key(
        agency_id,
        job.get("job_title"),
        job.get("company_or_client"),
        job.get("location"),
    )

    existing = find_job(db, normalized_url, agency_id, fallback_key)

    fields = {
        "agency_id": agency_id,
        "normalized_job_url": normalized_url or None,
        "dedupe_fallback_key": fallback_key or None,
        "job_title": job.get("job_title") or None,
        "job_role": job.get("job_role") or None,
        "company_or_client": job.get("company_or_client") or None,
        "location": job.get("location") or None,
        "remote_status": job.get("remote_status") or None,
        "employment_type": job.get("employment_type") or None,
        "experience_required": job.get("experience_required") or None,
        "salary": job.get("salary") or None,
        "job_url": job.get("job_url") or None,
        "source_url": job.get("source_url") or None,
        "posted_date": job.get("posted_date") or None,
        "job_relevance": job.get("job_relevance") or None,
        "job_relevance_score": job.get("job_relevance_score"),
        "relevance_reason": job.get("relevance_reason") or None,
        "required_skills": job.get("required_skills") or None,
        "preferred_skills": job.get("preferred_skills") or None,
        "technologies": job.get("technologies") or None,
        "ai_domain": job.get("ai_domain") or None,
        "llm": job.get("llm"),
        "genai": job.get("genai"),
        "rag": job.get("rag"),
        "agents": job.get("agents"),
        "nlp": job.get("nlp"),
        "computer_vision": job.get("computer_vision"),
        "model_integration": job.get("model_integration"),
        "ai_application_development": job.get("ai_application_development"),
        "fresher_friendly": job.get("fresher_friendly") or None,
        "relevance_source": job.get("relevance_source") or None,
    }

    if existing:
        for key, value in fields.items():
            if key == "agency_id":
                continue

            # Booleans are meaningful even when False.
            if isinstance(value, bool):
                setattr(existing, key, value)
                continue

            if value not in (None, ""):
                setattr(existing, key, value)

        existing.updated_at = _utc_now()
        return existing, False

    record = JobOpening(**fields)
    db.add(record)
    db.flush()
    return record, True


def persist_agency_record(
    agency_record: dict,
    jobs: list,
    contacts: list,
    sources: list,
    demand_score,
    demand_level: str,
) -> dict:
    """Persist one fully-researched agency and its related rows.

    Returns a summary dict with insert/update counts, or {"skipped": True} when
    the database is unavailable.
    """
    db = get_session_or_none()

    if db is None:
        return {"skipped": True, "reason": "database not configured"}

    summary = {
        "skipped": False,
        "agency_id": None,
        "agency_created": False,
        "jobs_created": 0,
        "jobs_updated": 0,
        "contacts_created": 0,
        "sources_created": 0,
    }

    try:
        agency, created = upsert_agency(db, agency_record)
        summary["agency_id"] = agency.id
        summary["agency_created"] = created

        upsert_hiring_demand(db, agency.id, agency_record, demand_score, demand_level)

        for job in jobs:
            _, job_created = upsert_job_opening(db, agency.id, job)

            if job_created:
                summary["jobs_created"] += 1
            else:
                summary["jobs_updated"] += 1

        for contact in contacts:
            if upsert_contact(db, agency.id, contact):
                summary["contacts_created"] += 1

        for source in sources:
            if upsert_source(db, agency.id, source):
                summary["sources_created"] += 1

        db.commit()
    except Exception as exc:
        db.rollback()
        summary["skipped"] = True
        summary["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()

    return summary

