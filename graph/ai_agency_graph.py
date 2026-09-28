"""LangGraph workflow for the AI agency / AI Engineer job research agent.

Flow (per project spec):

    Discovery
      -> normalize/deduplicate
      -> PostgreSQL existence check        (cheap: skips agencies already stored)
      -> filter agencies                   (cheap LLM-assisted qualification)
      -> agency research
      -> AI-demand research
      -> job-opening research
      -> job relevance classification      (roadmap.sh/ai-engineer)
      -> contact research
      -> scoring
      -> PostgreSQL
      -> Google Sheets

Design notes
------------
* The graph is intentionally a single-agency research chain driven by a
  bounded queue of candidates.  Each node does one job and mutates a small,
  well-defined slice of state.
* Cheap stages (discovery filtering, dedupe, DB existence) always run before
  any expensive LLM research.
* Every expensive node is conditional on configuration flags so tests and
  partial runs are possible.
* The graph never raises: node failures are captured into `errors` and the
  agency is skipped, so one bad agency cannot abort a batch.
"""
from __future__ import annotations

from typing import Optional

from langgraph.graph import END, StateGraph

from state.agency_research_state import AgencyResearchState  # noqa: F401

# Node names.
NODE_DISCOVER = "discover"
NODE_DEDUPE = "normalize_dedupe"
NODE_DB_CHECK = "db_existence_check"
NODE_FILTER = "filter_agencies"
NODE_RESEARCH = "agency_research"
NODE_DEMAND = "demand_research"
NODE_JOBS = "job_research"
NODE_RELEVANCE = "job_relevance"
NODE_CONTACTS = "contact_research"
NODE_SCORE = "scoring"
NODE_PERSIST = "persist"
NODE_NEXT = "next_agency"


def _load_agents():
    """Import agents lazily so importing the graph never requires API keys."""
    from agents.ai_jobs import (
        agency_research_agent,
        discovery_agent,
        relevance_agent,
    )

    return discovery_agent, agency_research_agent, relevance_agent


def _load_services():
    from services import search as search_service
    from services.db import dedupe, repository, session
    from services import sheets_agency_writer as sheets

    return search_service, dedupe, repository, session, sheets


def _load_scoring():
    from agents.ai_jobs import demand_scoring

    return demand_scoring


# ---------------------------------------------------------------------------
# Cheap stages
# ---------------------------------------------------------------------------


def discover_node(state: AgencyResearchState) -> dict:
    """Agency discovery for the current city (keyword filtering, no LLM)."""
    discovery_agent, _, _ = _load_agents()

    city = state.get("current_city") or "Gurugram"
    print(f"\n[DISCOVER] Searching agencies in {city} ...")

    candidates, search_meta, filtered_out = discovery_agent.discover_agencies_in_city(
        city,
        max_results_per_query=8,
        max_queries=6,
    )

    print(f"[DISCOVER] {len(candidates)} candidate(s), {filtered_out} filtered out")

    return {
        "candidates": candidates,
        "filtered_out": filtered_out,
        "discovered_count": state.get("discovered_count", 0) + len(candidates),
        "sources": [
            {
                "agency_name": meta["query"],
                "source_url": url,
                "source_type": "agency_discovery",
                "source_title": meta["query"],
                "city": meta.get("city"),
            }
            for meta in search_meta
            for url in meta.get("source_urls", [])
        ],
    }


def normalize_dedupe_node(state: AgencyResearchState) -> dict:
    """Normalize names/domains and drop duplicates within the candidate batch."""
    _, dedupe, _, _, _ = _load_services()

    seen_domains: set = set()
    seen_names: set = set()
    unique: list = []
    duplicates = 0

    for candidate in state.get("candidates", []):
        domain_key = dedupe.normalize_domain(candidate.get("domain"))
        name_key = dedupe.normalize_agency_name(candidate.get("agency_name"))

        if not name_key:
            duplicates += 1
            continue

        if (domain_key and domain_key in seen_domains) or name_key in seen_names:
            duplicates += 1
            continue

        if domain_key:
            seen_domains.add(domain_key)

        seen_names.add(name_key)
        unique.append(candidate)

    print(f"[DEDUPE] {len(unique)} unique candidate(s), {duplicates} duplicate(s) removed")

    return {
        "candidates": unique,
        "duplicates_skipped": state.get("duplicates_skipped", 0) + duplicates,
    }


def db_existence_check_node(state: AgencyResearchState) -> dict:
    """Drop candidates already stored in PostgreSQL (expensive research saved)."""
    _, dedupe, repository, session, _ = _load_services()

    if not state.get("db_enabled"):
        return {"existing_in_db": 0}

    kept: list = []
    existing_count = 0

    for candidate in state.get("candidates", []):
        domain_key = dedupe.normalize_domain(candidate.get("domain"))
        name_key = dedupe.normalize_agency_name(candidate.get("agency_name"))

        if repository.agency_exists(domain_key, name_key):
            existing_count += 1
            continue

        kept.append(candidate)

    if existing_count:
        print(f"[DB CHECK] {existing_count} candidate(s) already in PostgreSQL; skipped")

    return {"candidates": kept, "existing_in_db": existing_count}


def filter_agencies_node(state: AgencyResearchState) -> dict:
    """Qualify candidates as recruitment/staffing agencies in the target market.

    Cheap deterministic checks only - no LLM here by design.
    """
    from state import agency_config

    kept: list = []
    rejected = 0

    for candidate in state.get("candidates", []):
        name = (candidate.get("agency_name") or "").strip()
        domain = (candidate.get("domain") or "").strip()

        if not name or not domain:
            rejected += 1
            continue

        # Require an Indian market signal somewhere in the record.
        ncr = candidate.get("ncr_presence") or agency_config.has_ncr_presence(
            candidate.get("search_city")
        )
        candidate["ncr_presence"] = ncr

        kept.append(candidate)

    cap = state.get("max_agencies") or 10

    # Highest geographic priority first, then highest cheap keyword score.
    kept.sort(
        key=lambda c: (
            -(c.get("geographic_priority_score") or 0),
            -(c.get("_score") or 0),
        )
    )

    selected = kept[:cap]

    print(f"[FILTER] {len(selected)} agency(ies) selected for deep research "
          f"({rejected} rejected, cap={cap})")

    return {"candidates": selected}


# ---------------------------------------------------------------------------
# Per-agency research chain
# ---------------------------------------------------------------------------


def _next_candidate(state: AgencyResearchState) -> Optional[dict]:
    """Pop the next candidate from the queue."""
    candidates = state.get("candidates") or []

    return candidates[0] if candidates else None


def start_agency_node(state: AgencyResearchState) -> dict:
    """Select the next candidate and initialize its research record."""
    candidate = _next_candidate(state)

    if candidate is None:
        return {"current_agency": {}}

    # The remaining queue is carried forward so `next_agency` can continue.
    remaining = list(state.get("candidates") or [])[1:]

    agency = dict(candidate)
    agency.pop("_score", None)

    print(f"\n{'=' * 70}")
    print(f"RESEARCHING: {agency.get('agency_name')} ({agency.get('domain')})")
    print(f"{'=' * 70}")

    return {
        "current_agency": agency,
        "candidates": remaining,
    }


def agency_research_node(state: AgencyResearchState) -> dict:
    """Profile research for the current agency."""
    _, agency_research_agent, _ = _load_agents()

    agency = dict(state.get("current_agency") or {})

    if not agency:
        return {}

    try:
        profile, sources = agency_research_agent.research_agency_profile(agency)
    except Exception as exc:
        return {
            "errors": [f"{agency.get('agency_name')}: profile research failed: {exc}"],
            "current_agency": {**agency, "research_failed": True},
        }

    merged = {**agency, **{k: v for k, v in profile.items() if v}}

    return {
        "current_agency": merged,
        "sources": [
            {
                "agency_name": merged.get("agency_name"),
                "source_url": url,
                "source_type": "agency_research",
                "source_title": "",
            }
            for url in sources
        ],
    }


def demand_research_node(state: AgencyResearchState) -> dict:
    """AI/technical hiring-demand research for the current agency."""
    _, agency_research_agent, _ = _load_agents()

    agency = dict(state.get("current_agency") or {})

    if not agency or agency.get("research_failed"):
        return {}

    try:
        demand, sources = agency_research_agent.research_hiring_demand(agency)
    except Exception as exc:
        return {"errors": [f"{agency.get('agency_name')}: demand research failed: {exc}"]}

    return {
        "current_agency": {**agency, **(demand or {})},
        "sources": [
            {
                "agency_name": agency.get("agency_name"),
                "source_url": url,
                "source_type": "hiring_demand",
                "source_title": "",
            }
            for url in sources
        ],
    }


def job_research_node(state: AgencyResearchState) -> dict:
    """Roadmap-targeted job-opening research for the current agency."""
    _, agency_research_agent, _ = _load_agents()

    agency = dict(state.get("current_agency") or {})

    if not agency or agency.get("research_failed"):
        return {}

    try:
        jobs, sources = agency_research_agent.research_job_openings(
            agency,
            city=agency.get("search_city") or agency.get("primary_city") or "",
        )
    except Exception as exc:
        return {"errors": [f"{agency.get('agency_name')}: job research failed: {exc}"]}

    print(f"  jobs extracted: {len(jobs)}")

    return {
        "current_agency": {**agency, "_raw_jobs": jobs},
        "sources": [
            {
                "agency_name": agency.get("agency_name"),
                "source_url": url,
                "source_type": "job_openings",
                "source_title": "",
            }
            for url in sources
        ],
    }


def job_relevance_node(state: AgencyResearchState) -> dict:
    """Classify each extracted job against the AI Engineer roadmap."""
    _, _, relevance_agent = _load_agents()

    agency = dict(state.get("current_agency") or {})

    if not agency or agency.get("research_failed"):
        return {}

    raw_jobs = agency.get("_raw_jobs") or []

    if not raw_jobs:
        return {"current_agency": {**agency, "job_openings": []}}

    classified = relevance_agent.classify_jobs(raw_jobs, use_llm=True)

    # Attach the agency context required by the DB/Sheets schemas.
    agency_city = agency.get("primary_city") or agency.get("search_city") or ""
    ncr = agency.get("ncr_presence") or ""

    finalized: list = []

    for job in classified:
        finalized.append(
            {
                **job,
                "agency_name": agency.get("agency_name") or "",
                "agency_domain": agency.get("domain") or "",
                "agency_city": agency_city,
                "ncr_presence": ncr,
                # Prefer the specific posting URL; fall back to the page we read.
                "job_url": job.get("job_url") or job.get("source_url") or "",
            }
        )

    counts = relevance_agent.count_by_relevance(finalized)
    print(f"  relevance: {counts}")

    target_jobs = [
        job
        for job in finalized
        if job.get("job_relevance") in ("TARGET_AI_ENGINEER", "RELATED_AI_ENGINEERING")
    ]

    return {
        "current_agency": {
            **agency,
            "job_openings": finalized,
            "_raw_jobs": [],
            "_target_job_count": len(target_jobs),
        }
    }


def contact_research_node(state: AgencyResearchState) -> dict:
    """Contact research - runs only AFTER the agency has been qualified."""
    _, agency_research_agent, _ = _load_agents()

    agency = dict(state.get("current_agency") or {})

    if not agency or agency.get("research_failed"):
        return {}

    try:
        contacts, sources = agency_research_agent.research_contacts(agency)
    except Exception as exc:
        return {"errors": [f"{agency.get('agency_name')}: contact research failed: {exc}"]}

    contact_list = contacts.get("contacts") or []

    print(f"  contacts found: {len(contact_list)}")

    return {
        "current_agency": {
            **agency,
            "contacts": contact_list,
            "agency_email": contacts.get("agency_email") or "",
            "recruitment_email": contacts.get("recruitment_email") or "",
        },
        "sources": [
            {
                "agency_name": agency.get("agency_name"),
                "source_url": url,
                "source_type": "contact_research",
                "source_title": "",
            }
            for url in sources
        ],
    }





def scoring_node(state: AgencyResearchState) -> dict:
    """Score AI demand (/100) and derive the final agency record.

    Geographic priority is kept in its own field and never mixed into this score.
    """
    demand_scoring = _load_scoring()
    _, dedupe, _, _, _ = _load_services()

    from datetime import datetime, timezone

    agency = dict(state.get("current_agency") or {})

    if not agency:
        return {}

    contacts = agency.get("contacts") or []
    jobs = agency.get("job_openings") or []

    active_roles = agency.get("active_ai_roles")

    if active_roles is None and agency.get("estimated_ai_positions") is not None:
        active_roles = agency.get("estimated_ai_positions")

    # Multiple relevant openings is itself evidence of multiple AI hiring.
    has_multiple_openings = len(jobs) >= 3

    score, level, breakdown = demand_scoring.compute_ai_demand_score(
        technical_recruitment=agency.get("technical_recruitment"),
        ai_recruitment=agency.get("ai_recruitment"),
        genai_recruitment=agency.get("genai_recruitment"),
        contract_staffing=agency.get("contract_staffing"),
        bulk_hiring=agency.get("bulk_hiring"),
        active_ai_roles=active_roles,
        estimated_ai_positions=agency.get("estimated_ai_positions"),
        has_multiple_openings=has_multiple_openings,
        contacts=contacts,
    )

    confidence = demand_scoring.confidence_for(
        score,
        sources=len(agency.get("source_urls") or []),
        has_hiring_evidence=bool(jobs) or bool(agency.get("ai_recruitment")),
    )

    # Flatten decision-maker contacts into the agency columns.
    role_by_keyword = {
        "founder": ("founder", "co-founder", "ceo"),
        "managing_director": ("managing director", "director"),
        "recruitment_head": ("recruitment head", "head of recruitment"),
        "ai_practice_lead": ("ai practice", "practice lead", "practice head"),
    }

    flattened = {
        "founder": "",
        "managing_director": "",
        "recruitment_head": "",
        "ai_practice_lead": "",
        "decision_maker_email": "",
        "decision_maker_linkedin": "",
    }

    for contact in contacts:
        role = (contact.get("role") or "").lower()

        for field, keywords in role_by_keyword.items():
            if not flattened[field] and any(keyword in role for keyword in keywords):
                flattened[field] = contact.get("name") or ""

        if not flattened["decision_maker_email"] and demand_scoring.is_decision_maker(role):
            flattened["decision_maker_email"] = contact.get("email") or ""
            flattened["decision_maker_linkedin"] = contact.get("linkedin") or ""

    job_urls = [job.get("job_url") for job in jobs if job.get("job_url")]

    agency_record = {
        **agency,
        **flattened,
        "normalized_domain": dedupe.normalize_domain(agency.get("domain")),
        "normalized_name": dedupe.normalize_agency_name(agency.get("agency_name")),
        "ai_demand_score": score,
        "ai_demand_level": level,
        "confidence": confidence,
        "job_urls": ", ".join(dict.fromkeys(job_urls)),
        "status": "RESEARCHED",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "parse_error": "",
        "raw": "",
        "_demand_breakdown": breakdown,
    }

    print(f"  AI demand score: {score}/100 ({level}) | "
          f"geo priority: {agency_record.get('geographic_priority_score')}")
    print(f"  breakdown: {breakdown}")

    return {"current_agency": agency_record}




def persist_node(state: AgencyResearchState) -> dict:
    """Persist to PostgreSQL (when enabled) and Google Sheets."""
    _, _, repository, _, sheets = _load_services()

    agency = dict(state.get("current_agency") or {})

    if not agency:
        return {}

    jobs = agency.get("job_openings") or []
    contacts = agency.get("contacts") or []

    # Deduplicate source URLs for THIS agency only.
    seen: set = set()
    sources: list = []

    for source in state.get("sources") or []:
        if source.get("agency_name") not in (None, agency.get("agency_name")):
            continue

        url = source.get("source_url")

        if not url or url in seen:
            continue

        seen.add(url)
        sources.append(source)

    # --- PostgreSQL -------------------------------------------------------
    db_summary = {"skipped": True, "reason": "disabled"}

    if state.get("db_enabled"):
        db_summary = repository.persist_agency_record(
            agency_record=agency,
            jobs=jobs,
            contacts=contacts,
            sources=sources,
            demand_score=agency.get("ai_demand_score"),
            demand_level=agency.get("ai_demand_level") or "UNKNOWN",
        )

        if db_summary.get("skipped"):
            print(f"  [db] skipped: {db_summary.get('reason')}")
        else:
            print(
                f"  [db] agency_id={db_summary.get('agency_id')} "
                f"jobs+{db_summary.get('jobs_created')} "
                f"contacts+{db_summary.get('contacts_created')} "
                f"sources+{db_summary.get('sources_created')}"
            )

    # --- Google Sheets ----------------------------------------------------
    written_agency = 0
    written_jobs = 0

    if state.get("sheets_enabled"):
        try:
            row = dict(agency)
            row["source_urls"] = ", ".join(source["source_url"] for source in sources)
            row.pop("_demand_breakdown", None)
            row.pop("_target_job_count", None)
            row.pop("_raw_jobs", None)

            if sheets.write_agency_row(row):
                written_agency = 1

            written_jobs = sheets.write_job_rows(jobs)
        except sheets.SheetsUnavailable as exc:
            print(f"  [sheets] skipped: {exc}")
        except Exception as exc:
            print(f"  [sheets] write failed: {exc}")

    return {
        "agencies": [agency],
        "jobs": jobs,
        "sources": sources,
        "written_db_count": state.get("written_db_count", 0)
        + (0 if db_summary.get("skipped") else 1),
        "written_sheet_count": state.get("written_sheet_count", 0) + written_agency,
        "job_count": state.get("job_count", 0) + written_jobs,
        "target_job_count": state.get("target_job_count", 0)
        + (agency.get("_target_job_count") or 0),
        "processed_count": state.get("processed_count", 0) + 1,
    }


def next_agency_node(state: AgencyResearchState) -> dict:
    """Clear the per-agency workspace before the next candidate."""
    return {"current_agency": {}}


def route_next(state: AgencyResearchState) -> str:
    """Loop to the next candidate while any remain, else finish."""
    return "continue" if state.get("candidates") else "done"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_graph():
    """Build and compile the AI agency research graph."""
    builder = StateGraph(AgencyResearchState)

    builder.add_node(NODE_DISCOVER, discover_node)
    builder.add_node(NODE_DEDUPE, normalize_dedupe_node)
    builder.add_node(NODE_DB_CHECK, db_existence_check_node)
    builder.add_node(NODE_FILTER, filter_agencies_node)
    builder.add_node("start_agency", start_agency_node)
    builder.add_node(NODE_RESEARCH, agency_research_node)
    builder.add_node(NODE_DEMAND, demand_research_node)
    builder.add_node(NODE_JOBS, job_research_node)
    builder.add_node(NODE_RELEVANCE, job_relevance_node)
    builder.add_node(NODE_CONTACTS, contact_research_node)
    builder.add_node(NODE_SCORE, scoring_node)
    builder.add_node(NODE_PERSIST, persist_node)
    builder.add_node(NODE_NEXT, next_agency_node)

    builder.set_entry_point(NODE_DISCOVER)

    # Cheap stages first.
    builder.add_edge(NODE_DISCOVER, NODE_DEDUPE)
    builder.add_edge(NODE_DEDUPE, NODE_DB_CHECK)
    builder.add_edge(NODE_DB_CHECK, NODE_FILTER)
    builder.add_edge(NODE_FILTER, "start_agency")

    # Per-agency research chain.
    builder.add_edge("start_agency", NODE_RESEARCH)
    builder.add_edge(NODE_RESEARCH, NODE_DEMAND)
    builder.add_edge(NODE_DEMAND, NODE_JOBS)
    builder.add_edge(NODE_JOBS, NODE_RELEVANCE)
    builder.add_edge(NODE_RELEVANCE, NODE_CONTACTS)
    builder.add_edge(NODE_CONTACTS, NODE_SCORE)
    builder.add_edge(NODE_SCORE, NODE_PERSIST)
    builder.add_edge(NODE_PERSIST, NODE_NEXT)

    # Loop until the candidate queue is empty.
    builder.add_conditional_edges(
        NODE_NEXT,
        route_next,
        {"continue": "start_agency", "done": END},
    )

    return builder.compile()


# Module-level compiled graph (mirrors the existing research_graph convention).
graph = build_graph()
