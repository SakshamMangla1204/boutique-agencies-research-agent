"""Agency discovery: broad search -> normalize -> cheap filter -> candidates.

Keyword stage (free, no LLM):
  * generate NCR-first search queries
  * run Tavily searches
  * keep only results that look like a recruitment/staffing agency page with
    signs of AI/IT focus, using deterministic keyword checks
  * normalize names/domains and dedupe in-process

Only the surviving candidates reach the LLM extraction step, so we never pay
to deeply research every raw search result.
"""
from __future__ import annotations

import re

from services import search as search_service
from services.db.dedupe import normalize_agency_name, normalize_domain
from state import agency_config
from state import search_queries

# Agency-type keywords used for the cheap relevance filter.
AGENCY_SIGNAL_KEYWORDS = (
    "recruitment", "recruiting", "recruiter", "staffing", "manpower",
    "talent acquisition", "talent solutions", "executive search",
    "headhunting", "head hunting", "placement", "hiring partner",
    "contract staffing", "permanent staffing", "executive recruitment",
    "hr consultancy", "human resources consultancy", "people solutions",
)

# AI/technology focus keywords for the cheap AI-relevance filter.
TECH_SIGNAL_KEYWORDS = (
    "ai", "artificial intelligence", "machine learning", "data science",
    "generative ai", "genai", "llm", "nlp", "technology", "it staffing",
    "software", "engineering", "technical", "digital", "cloud", "data",
)

# Domains that are never agencies themselves (aggregators, social, job boards).
AGGREGATOR_DOMAINS = (
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "glassdoor.com", "indeed.com", "naukri.com", "monster.com",
    "ambitionbox.com", "glassdoor.co.in", "crunchbase.com", "wikipedia.org",
    "bloomberg.com", "quora.com", "reddit.com", "medium.com", "yelp.com",
    "clutch.co", "goodfirms.co", "designrush.com", "sortlist.com",
    "timesjobs.com", "foundit.in", "shine.com", "hirist.com", "cutshort.io",
    "wellfound.com", "instahyre.com", "tracxn.com", "zaubacorp.com",
    "justdial.com", "sulekha.com", "google.com", "bing.com",
)

# Career/job-listing paths that indicate a job page rather than an agency site.
_JOB_PATH_RE = re.compile(
    r"/(jobs?|careers?|vacanc(?:y|ies)|openings?|apply|positions?)(/|$|\?)",
    re.IGNORECASE,
)

NON_AGENCY_TITLE_PATTERNS = (
    r"\bjobs?\b.*\b(hiring|opening|vacancy)\b",
    r"\bapply now\b",
    r"\bjob description\b",
    r"\bsalary\b",
    r"\binterview questions\b",
    r"\btop \d+\b",
    r"\bbest \d+\b",
    r"\blist of\b",
    r"\bhow to\b",
)


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    """Whole-word (or phrase) keyword check, tolerant of surrounding text."""
    lowered = f" {text.lower()} "

    for keyword in keywords:
        if " " in keyword:
            if keyword in lowered:
                return True
        elif re.search(rf"[^a-z]{re.escape(keyword)}[^a-z]", lowered):
            return True

    return False


def is_aggregator(domain: str) -> bool:
    """True when the domain is a job board / social / directory site."""
    if not domain:
        return True

    return any(
        domain == blocked or domain.endswith("." + blocked)
        for blocked in AGGREGATOR_DOMAINS
    )


def score_candidate(result: dict) -> tuple:
    """Cheaply score one raw search result. Returns (score, reason).

    A score below the caller's threshold means the result is discarded before
    any LLM call.
    """
    url = result.get("url") or ""
    title = result.get("title") or ""
    content = result.get("content") or ""

    domain = normalize_domain(url)

    if not domain:
        return 0, "no usable domain"

    if is_aggregator(domain):
        return 0, f"aggregator/social domain ({domain})"

    combined = f"{title} {content}"

    if not _has_keyword(combined, AGENCY_SIGNAL_KEYWORDS):
        return 0, "no recruitment/staffing agency signal"

    if not _has_keyword(combined, TECH_SIGNAL_KEYWORDS):
        return 0, "agency-like page without AI/technology signal"

    for pattern in NON_AGENCY_TITLE_PATTERNS:
        if re.search(pattern, title.lower()):
            return 0, "looks like a blog/job-listing page rather than an agency site"

    if _JOB_PATH_RE.search(url):
        return 0, "URL path points to a job listing, not an agency site"

    score = 0

    if _has_keyword(title.lower(), AGENCY_SIGNAL_KEYWORDS):
        score += 3

    if _has_keyword(
        combined,
        ("ai", "artificial intelligence", "generative ai", "genai", "llm", "machine learning"),
    ):
        score += 3

    if _has_keyword(
        combined,
        ("it staffing", "technology recruitment", "technical recruitment", "contract staffing"),
    ):
        score += 2

    if _has_keyword(
        combined,
        ("india", "gurugram", "gurgaon", "noida", "delhi", "mumbai", "bengaluru"),
    ):
        score += 1

    return score, "agency + technology signals"


# Titles that are not agency names.
_TITLE_NOISE_RE = re.compile(
    r"\s*[|\-–—]\s*(home|about us|contact us|jobs?|careers?|services|blog|"
    r"india|official site|best .*|top .*)\s*$",
    re.IGNORECASE,
)
_TITLE_LEGAL_RE = re.compile(
    r"\s*[|\-–—]\s*(pvt\.?\s*ltd\.?|private limited|limited|ltd\.?|llp|inc\.?)\s*$",
    re.IGNORECASE,
)
_GENERIC_TITLE_RE = re.compile(
    r"^(home|jobs?|careers?|about|contact|recruitment|staffing|services|"
    r"welcome|index)\b",
    re.IGNORECASE,
)


def _name_from_title(title: str) -> str:
    """Derive a plausible agency name from a page title (deterministic)."""
    if not title:
        return ""

    text = _TITLE_NOISE_RE.sub("", title.strip())
    text = _TITLE_LEGAL_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text).strip(" -|–—")

    if not text or len(text) < 3 or len(text) > 90:
        return ""

    if _GENERIC_TITLE_RE.match(text):
        return ""

    return text


# Descriptive page titles that are NOT agency names, e.g.
# "AI Recruiter in Gurugram", "Top 10 IT Staffing Companies", "IT Staffing Services".
_DESCRIPTIVE_TITLE_RE = re.compile(
    r"\b(in|for|near|at)\s+[A-Z][a-z]+"          # "in Gurugram"
    r"|\b(talent|staffing|recruitment|recruiting|manpower|consultants?|"
    r"solutions?|services?|agency|agencies|companies|firms?|jobs?|careers?)\b",
    re.IGNORECASE,
)


def _name_from_domain(domain: str, title: str = "") -> str:
    """Build a readable agency name from the domain (most reliable fallback).

    'antal.com' -> 'Antal'
    'mukulconsultants.com' -> 'Mukulconsultants'
    'recruitinghub.ai' -> 'Recruitinghub'
    """
    if not domain:
        return ""

    # Only the registrable label, without TLD/subdomain.
    core = domain.split(".")[0]
    core = re.sub(r"^(www|careers|jobs|hire|staffing)-?", "", core, flags=re.IGNORECASE)

    if not core or len(core) < 3:
        return ""

    # Prefer a clean word from the title when it matches the domain core.
    if title:
        for token in re.findall(r"[A-Za-z][A-Za-z&.\-]{2,}", title):
            cleaned = token.strip(".-&")

            if (
                cleaned
                and cleaned.lower().replace(" ", "") in core.lower().replace("-", "")
                and not _DESCRIPTIVE_TITLE_RE.search(cleaned)
            ):
                return cleaned

    return core.replace("-", " ").title()


def _resolve_agency_name(title: str, domain: str) -> str:
    """Pick the most trustworthy agency name available.

    A title is only trusted when it does not look like a descriptive/marketing
    page title; otherwise we fall back to the domain, which is far less likely
    to invent marketing copy as a company name.
    """
    from_title = _name_from_title(title)

    if from_title and not _DESCRIPTIVE_TITLE_RE.search(from_title):
        # Reject titles that are mostly generic industry words.
        words = from_title.split()

        if len(words) <= 6:
            return from_title

    return _name_from_domain(domain, title)



def extract_candidates_from_results(
    results: list[dict],
    search_city: str,
    min_score: int = 3,
) -> tuple:
    """Cheaply filter search results into agency candidates (no LLM).

    Returns (candidates, filtered_out_count).
    """
    tier, priority = agency_config.city_priority(search_city)

    seen_names: set[str] = set()
    seen_domains: set[str] = set()

    candidates: list[dict] = []
    filtered_out = 0

    for result in results:
        score, reason = score_candidate(result)

        if score < min_score:
            filtered_out += 1
            continue

        url = result.get("url") or ""
        domain = normalize_domain(url)
        agency_name = _name_from_title((result.get("title") or "").strip())

        if not agency_name:
            filtered_out += 1
            continue

        name_key = normalize_agency_name(agency_name)

        if not name_key or name_key in seen_names or domain in seen_domains:
            filtered_out += 1
            continue

        seen_names.add(name_key)
        seen_domains.add(domain)

        canonical_city = agency_config.canonical_city(search_city)

        candidates.append(
            {
                "agency_name": agency_name,
                "domain": domain,
                "primary_city": canonical_city.title() if canonical_city else search_city,
                "state": "",
                "country": "India",
                "service_area": "",
                "ncr_presence": agency_config.has_ncr_presence(search_city),
                "agency_type": "",
                "linkedin": "",
                "description": (result.get("content") or "")[:500],
                "source_url": url,
                "search_city": search_city,
                "geographic_tier": tier,
                "geographic_priority_score": priority,
                "exists_in_db": False,
                "filter_reason": reason,
                "_score": score,
            }
        )

    return candidates, filtered_out


def discover_agencies_in_city(
    city: str,
    max_results_per_query: int = 8,
    max_queries: int = 6,
    min_score: int = 3,
) -> tuple:
    """Discover agency candidates for one city.

    Returns (candidates, search_meta, filtered_out).
    """
    queries = search_queries.agency_search_queries(city, limit=max_queries)

    all_results: list[dict] = []
    search_meta: list[dict] = []
    filtered_out = 0

    for query in queries:
        results = search_service.search(query, max_results=max_results_per_query)

        if not results:
            continue

        search_meta.append(
            {
                "query": query,
                "city": city,
                "result_count": len(results),
                "source_urls": search_service.source_urls(results),
                "source_type": "agency_discovery",
            }
        )

        all_results.extend(results)

    candidates, filtered = extract_candidates_from_results(
        all_results,
        search_city=city,
        min_score=min_score,
    )

    return candidates, search_meta, filtered_out + filtered
