"""Agency research agent: profile, AI-demand, job openings, and contacts.

Each function performs one bounded Tavily search, trims the content, asks the
LLM for strict JSON, and falls back to safe empty/null values on any failure -
so a single bad response can never fabricate data or crash the run.
"""
from __future__ import annotations

import re

from services import search as search_service
from services.llm import get_llm
from utils.json_parse import extract_json_object

from agents.ai_jobs import prompts

_MAX_CONTENT_CHARS = 7000

_NULLISH = {"", "null", "none", "n/a", "na", "unknown", "not specified", "-"}


def _clean(value, default: str = "") -> str:
    """Normalize a scalar LLM field to a stripped string."""
    if value is None:
        return default

    text = str(value).strip()

    if text.lower() in _NULLISH:
        return default

    return text


def _clean_int(value):
    """Return an int only when the model gave a real number, else None.

    This is the guard that prevents fabricated job counts from being stored.
    """
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if value >= 0 else None

    text = str(value).strip()

    if not text or text.lower() in _NULLISH:
        return None

    match = re.search(r"\d+", text)

    if not match:
        return None

    return int(match.group(0))


def _clean_bool(value):
    """Return True/False/None from a tri-state LLM field."""
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()

    if text in _NULLISH:
        return None

    if text in {"true", "yes", "y", "1"}:
        return True

    if text in {"false", "no", "n", "0"}:
        return False

    return None


def _invoke_json(task: str, prompt: str) -> dict:
    """Invoke the LLM and parse a JSON object, returning {} on any failure."""
    try:
        llm = get_llm(task)
        result = llm.invoke(prompt)
        return extract_json_object(result.content)
    except Exception as exc:
        print(f"    [{task}] LLM/parse failure: {exc}")
        return {}


def _search_for(agency_name: str, domain: str, extras: str, max_results: int = 6):
    """Run a targeted search for an agency, preferring its own domain."""
    target = domain or agency_name
    query = f'"{agency_name}" {target} {extras}'
    return search_service.search(query, max_results=max_results)


def research_agency_profile(agency: dict) -> tuple:
    """Research the agency profile. Returns (profile_dict, source_urls)."""
    agency_name = agency.get("agency_name") or ""
    domain = agency.get("domain") or ""
    city = agency.get("search_city") or agency.get("primary_city") or ""

    results = _search_for(
        agency_name,
        domain,
        "recruitment staffing agency about company overview India",
        max_results=6,
    )

    content = search_service.format_results(results, max_chars=_MAX_CONTENT_CHARS)
    sources = search_service.source_urls(results)

    if not content:
        return {}, sources

    data = _invoke_json(
        "agency_research",
        prompts.AGENCY_RESEARCH_PROMPT.format(
            agency_name=agency_name,
            domain=domain,
            city=city,
            rules=prompts.NO_FABRICATION_RULES,
            content=content,
        ),
    )

    profile = {
        "agency_name": _clean(data.get("agency_name"), agency_name) or agency_name,
        "domain": _clean(data.get("domain"), domain)
        .replace("https://", "")
        .replace("http://", "")
        .strip("/"),
        "country": _clean(data.get("country"), "India") or "India",
        "primary_city": _clean(data.get("primary_city"), agency.get("primary_city", "")),
        "state": _clean(data.get("state")),
        "service_area": _clean(data.get("service_area")),
        "ncr_presence": _clean(data.get("ncr_presence")).upper(),
        "agency_type": _clean(data.get("agency_type")),
        "linkedin": _clean(data.get("linkedin")),
        "description": _clean(data.get("description")),
    }

    if profile["ncr_presence"] not in {"YES", "POSSIBLY", "NO", "UNKNOWN"}:
        profile["ncr_presence"] = ""

    return profile, sources


def research_hiring_demand(agency: dict) -> tuple:
    """Research AI/technical hiring demand. Returns (demand_dict, source_urls)."""
    agency_name = agency.get("agency_name") or ""
    domain = agency.get("domain") or ""

    results = _search_for(
        agency_name,
        domain,
        "AI ML GenAI LLM hiring jobs openings technologies staffing",
        max_results=8,
    )

    content = search_service.format_results(results, max_chars=_MAX_CONTENT_CHARS)
    sources = search_service.source_urls(results)

    if not content:
        return {}, sources

    data = _invoke_json(
        "demand_research",
        prompts.DEMAND_RESEARCH_PROMPT.format(
            agency_name=agency_name,
            domain=domain,
            rules=prompts.NO_FABRICATION_RULES,
            content=content,
        ),
    )

    demand = {
        "technical_recruitment": _clean_bool(data.get("technical_recruitment")),
        "ai_recruitment": _clean_bool(data.get("ai_recruitment")),
        "genai_recruitment": _clean_bool(data.get("genai_recruitment")),
        "contract_staffing": _clean_bool(data.get("contract_staffing")),
        "bulk_hiring": _clean_bool(data.get("bulk_hiring")),
        "active_ai_roles": _clean_int(data.get("active_ai_roles")),
        "estimated_ai_positions": _clean_int(data.get("estimated_ai_positions")),
        "ai_roles": _clean(data.get("ai_roles")),
        "technologies": _clean(data.get("technologies")),
        "client_industries": _clean(data.get("client_industries")),
        "bulk_hiring_evidence": _clean(data.get("bulk_hiring_evidence")),
        "evidence_date": _clean(data.get("evidence_date")),
    }

    return demand, sources


def research_job_openings(agency: dict, city: str = "") -> tuple:
    """Research AI Engineer job openings. Returns (jobs_list, source_urls)."""
    agency_name = agency.get("agency_name") or ""
    domain = agency.get("domain") or ""
    focus_city = city or agency.get("search_city") or agency.get("primary_city") or "India"

    # Roadmap-aligned role keywords constrain the search so this never becomes a
    # generic ML-job sweep.
    role_terms = " OR ".join(
        f'"{role}"'
        for role in (
            "AI Engineer",
            "Generative AI Engineer",
            "LLM Engineer",
            "RAG Engineer",
            "Agentic AI Engineer",
            "Applied AI Engineer",
        )
    )

    query = f'"{agency_name}" {focus_city} jobs ({role_terms})'

    results = search_service.search(query, max_results=8)
    sources = search_service.source_urls(results)

    content = search_service.format_results(results, max_chars=_MAX_CONTENT_CHARS)

    if not content:
        return [], sources

    data = _invoke_json(
        "job_research",
        prompts.JOB_RESEARCH_PROMPT.format(
            roadmap_url=prompts.ROADMAP_URL,
            agency_name=agency_name,
            city=focus_city,
            rules=prompts.NO_FABRICATION_RULES,
            content=content,
        ),
    )

    raw_jobs = data.get("jobs")

    if not isinstance(raw_jobs, list):
        return [], sources

    jobs: list[dict] = []

    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue

        title = _clean(raw.get("job_title"))

        if not title:
            continue

        jobs.append(
            {
                "job_title": title,
                "company_or_client": _clean(raw.get("company_or_client")),
                "location": _clean(raw.get("location"), focus_city),
                "remote_status": _clean(raw.get("remote_status"), "Not specified"),
                "employment_type": _clean(raw.get("employment_type"), "Not specified"),
                "experience_required": _clean(raw.get("experience_required")),
                "salary": _clean(raw.get("salary")),
                "job_url": _clean(raw.get("job_url")),
                "source_url": _clean(raw.get("source_url")),
                "posted_date": _clean(raw.get("posted_date")),
                "required_skills": _clean(raw.get("required_skills")),
                "preferred_skills": _clean(raw.get("preferred_skills")),
                "jd_summary": _clean(raw.get("jd_summary")),
            }
        )

    return jobs, sources


def research_contacts(agency: dict) -> tuple:
    """Research publicly published decision-maker contacts.

    Returns (contacts_dict, source_urls).  Emails are only ever stored when
    they appear verbatim in the search results, together with their source URL.
    """
    from services.db.dedupe import classify_email_type

    agency_name = agency.get("agency_name") or ""
    domain = agency.get("domain") or ""

    results = _search_for(
        agency_name,
        domain,
        "contact recruitment head talent acquisition founder managing director email",
        max_results=8,
    )

    content = search_service.format_results(results, max_chars=_MAX_CONTENT_CHARS)
    sources = search_service.source_urls(results)

    empty = {"contacts": [], "agency_email": "", "recruitment_email": ""}

    if not content:
        return empty, sources

    data = _invoke_json(
        "contact_research",
        prompts.CONTACT_RESEARCH_PROMPT.format(
            agency_name=agency_name,
            domain=domain,
            rules=prompts.NO_FABRICATION_RULES,
            content=content,
        ),
    )

    raw_contacts = data.get("contacts")
    contacts: list[dict] = []

    if isinstance(raw_contacts, list):
        for raw in raw_contacts:
            if not isinstance(raw, dict):
                continue

            name = _clean(raw.get("name"))
            role = _clean(raw.get("role"))
            email = _clean(raw.get("email"))

            if not name and not email:
                continue

            email_type = _clean(raw.get("email_type")).lower()

            if not email:
                email_type = "unknown"
            elif email_type not in {"business", "freemail"}:
                # Derive it locally so the label is consistent with our rules.
                email_type = classify_email_type(email)

            contacts.append(
                {
                    "name": name,
                    "role": role,
                    "linkedin": _clean(raw.get("linkedin")),
                    "email": email,
                    "email_type": email_type,
                    "source_url": _clean(raw.get("source_url")),
                }
            )

    return {
        "contacts": contacts,
        "agency_email": _clean(data.get("agency_email")),
        "recruitment_email": _clean(data.get("recruitment_email")),
    }, sources

