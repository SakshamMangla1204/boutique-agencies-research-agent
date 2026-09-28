"""Search-query builders for AI agency discovery and AI Engineer job searches.

Two query families:

1. AGENCY discovery - boutique/small/mid-size AI & IT recruitment/staffing
   firms in the location currently being worked.
2. JOB discovery - roadmap-aligned AI Engineer roles
   (https://roadmap.sh/ai-engineer) - never a generic ML-job sweep.

Query generation is pure Python so it is free and deterministic.  It runs
BEFORE any LLM call so we never burn tokens exploring the wrong market.
"""
from __future__ import annotations

from state.agency_config import EXPANSION_SEARCH_ORDER, NCR_SEARCH_ORDER

# Agency-discovery query cores.
AGENCY_QUERY_TEMPLATES = (
    "AI recruitment {city}",
    "AI staffing {city}",
    "IT staffing {city}",
    "technology recruitment {city}",
    "technical recruitment agency {city}",
    "AI recruitment agency {city}",
    "GenAI recruitment {city}",
    "contract IT staffing {city}",
    "engineering recruitment {city}",
    "talent acquisition agency {city}",
    "executive search technology {city}",
    "boutique recruitment agency {city}",
    "AI hiring partner {city}",
)

# Roadmap-aligned job-search role keywords.  Priority order matters: the first
# ones are the strongest AI-engineer signals.
JOB_ROLE_KEYWORDS = (
    "AI Engineer",
    "Generative AI Engineer",
    "GenAI Engineer",
    "LLM Engineer",
    "RAG Engineer",
    "AI Application Engineer",
    "Agentic AI Engineer",
    "Applied AI Engineer",
    "AI Developer",
)

# Secondary role keywords, used to broaden coverage without going generic.
SECONDARY_JOB_ROLE_KEYWORDS = (
    "LLM Application Engineer",
    "AI Solutions Engineer",
    "AI Integration Engineer",
    "AI Automation Engineer",
    "AI Platform Engineer",
    "Artificial Intelligence Engineer",
    "GenAI Developer",
)

JOB_SEARCH_SUFFIXES = (
    "{query} jobs",
    "{query} hiring",
    "{query} job opening",
    "{query} recruitment agency",
)

# City labels used in job searches: NCR first, then expansion hubs.
JOB_SEARCH_CITIES = tuple(
    dict.fromkeys(
        [entry[0] for entry in NCR_SEARCH_ORDER]
        + [entry[0] for entry in EXPANSION_SEARCH_ORDER]
    )
)


def agency_search_queries(city: str, limit: int | None = None) -> list[str]:
    """Discovery queries for recruitment/staffing agencies in one city."""
    queries = [template.format(city=city) for template in AGENCY_QUERY_TEMPLATES]

    if limit is not None:
        return queries[:limit]

    return queries


def job_search_queries(
    city: str,
    role_keywords: tuple[str, ...] = JOB_ROLE_KEYWORDS,
    limit: int | None = None,
) -> list[str]:
    """Roadmap-aligned AI Engineer job queries for one city.

    Produces every (role x suffix) combination, so 'AI Engineer' Gurgaon yields
    'AI Engineer Gurgaon jobs', '... hiring', etc.
    """
    queries: list[str] = []

    for role in role_keywords:
        base = f'"{role}" {city}'
        queries.append(base)
        queries.extend(
            suffix.format(query=base) for suffix in JOB_SEARCH_SUFFIXES
        )

    if limit is not None:
        return queries[:limit]

    return queries


def ncr_first_search_plan(include_expansion: bool = False) -> list[dict]:
    """Return the ordered discovery plan (highest geographic priority first)."""
    plan = [
        {
            "city": city_label,
            "canonical_city": canonical,
            "tier": tier,
            "priority": priority,
            "region": "NCR",
        }
        for city_label, canonical, tier, priority in NCR_SEARCH_ORDER
    ]

    if include_expansion:
        plan.extend(
            {
                "city": city_label,
                "canonical_city": canonical,
                "tier": tier,
                "priority": priority,
                "region": "EXPANSION",
            }
            for city_label, canonical, tier, priority in EXPANSION_SEARCH_ORDER
        )

    return plan
