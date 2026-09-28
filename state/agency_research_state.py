"""LangGraph state for the AI agency / AI Engineer job research pipeline.

The state is deliberately COMPACT: expensive payloads (raw web content) are
never accumulated here.  Only normalized records and source URLs travel
between nodes, and all list fields use `operator.add` reducers so parallel
branches can contribute without overwriting each other.
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict


class AgencyCandidate(TypedDict, total=False):
    """A cheaply-discovered agency candidate BEFORE expensive research."""

    agency_name: str
    domain: str
    primary_city: str
    state: str
    country: str
    service_area: str
    ncr_presence: str
    agency_type: str
    linkedin: str
    description: str
    source_url: str
    search_city: str
    geographic_tier: str
    geographic_priority_score: int
    # Populated by the database existence check.
    exists_in_db: bool
    filter_reason: str


class JobRecord(TypedDict, total=False):
    """A single AI Engineer roadmap-classified job opening."""

    agency_name: str
    agency_domain: str
    job_title: str
    job_role: str
    company_or_client: str
    location: str
    remote_status: str
    employment_type: str
    experience_required: str
    salary: str
    job_url: str
    source_url: str
    posted_date: str
    job_relevance: str
    job_relevance_score: int
    relevance_reason: str
    relevance_source: str
    required_skills: str
    preferred_skills: str
    technologies: str
    ai_domain: str
    llm: bool
    genai: bool
    rag: bool
    agents: bool
    nlp: bool
    computer_vision: bool
    model_integration: bool
    ai_application_development: bool
    fresher_friendly: str
    normalized_job_url: str
    dedupe_fallback_key: str
    is_duplicate: bool


class AgencyRecord(TypedDict, total=False):
    """A fully-researched agency with demand + contacts."""

    agency_name: str
    domain: str
    normalized_domain: str
    normalized_name: str
    country: str
    primary_city: str
    state: str
    service_area: str
    ncr_presence: str
    geographic_tier: str
    geographic_priority_score: int
    agency_type: str
    linkedin: str
    description: str

    # Hiring demand.
    technical_recruitment: Optional[bool]
    ai_recruitment: Optional[bool]
    genai_recruitment: Optional[bool]
    contract_staffing: Optional[bool]
    bulk_hiring: Optional[bool]
    active_ai_roles: Optional[int]
    estimated_ai_positions: Optional[int]
    ai_roles: str
    technologies: str
    client_industries: str
    bulk_hiring_evidence: str
    evidence_date: str
    ai_demand_level: str
    ai_demand_score: Optional[int]
    confidence: str

    # Contacts.
    contacts: list[dict]
    founder: str
    managing_director: str
    recruitment_head: str
    ai_practice_lead: str
    agency_email: str
    recruitment_email: str
    decision_maker_email: str
    decision_maker_linkedin: str

    # Jobs.
    job_openings: list[dict]

    # Provenance.
    source_urls: list[str]
    job_urls: list[str]

    status: str
    parse_error: str
    raw: str


class AgencyResearchState(TypedDict, total=False):
    """Top-level graph state."""

    # --- run configuration ---
    run_id: str
    target_cities: list[str]
    max_agencies: int
    include_expansion: bool
    enable_db: bool
    enable_sheets: bool

    # --- discovery ---
    current_city: str
    search_queries: list[str]
    candidates: list[dict]
    duplicates_skipped: int
    existing_in_db: int
    filtered_out: int

    # --- research loop (one agency at a time) ---
    current_agency: dict
    agencies: Annotated[list[dict], operator.add]
    jobs: Annotated[list[dict], operator.add]
    sources: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]

    # --- bookkeeping ---
    discovered_count: int
    processed_count: int
    written_db_count: int
    written_sheet_count: int
    job_count: int
    target_job_count: int
    db_enabled: bool
    sheets_enabled: bool
    stop_reason: str
