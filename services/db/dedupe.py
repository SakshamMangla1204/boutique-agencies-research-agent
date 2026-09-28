"""Deterministic normalization helpers for agency/job deduplication.

Pure Python, no LLM and no network.  These run on EVERY discovered record, so
they must stay cheap.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Structural/legal suffixes that should not affect agency identity.
#
# IMPORTANT: business-descriptor words like "staffing", "recruitment" and
# "talent" are intentionally NOT stripped.  Two different agencies genuinely
# named "ABC Staffing" and "ABC Recruitment" must not collapse into one key,
# and a short name like "ABC Staffing" must not reduce to just "abc".
AGENCY_SUFFIX_TOKENS = {
    "inc", "llc", "ltd", "limited", "pvt", "private", "corp", "corporation",
    "co", "company", "llp", "plc",
}

_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_SPLIT_RE = re.compile(r"[-_/]+")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# ATS / job-board hosts whose path carries the posting identity.
_ATS_HOSTS = (
    "greenhouse.io", "lever.co", "workable.com", "smartrecruiters.com",
    "ashbyhq.com", "jobvite.com", "icims.com", "recruitee.com",
    "wellfound.com", "naukri.com", "linkedin.com", "indeed.com",
)

# Tracking/query noise stripped from job URLs so the same posting found via
# different links normalizes to one dedupe key.
_URL_NOISE_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "referrer", "src", "trackingid", "trk",
    "gh_src", "lever-source", "lever-origin", "jobboardsource", "from",
    "lipi", "originalreferer", "position", "pagename",
}


def normalize_domain(url_or_domain: str | None) -> str:
    """Normalize a website/URL to a bare registrable domain.

    'https://www.ABC-Staffing.com/jobs?x=1' -> 'abcstaffing.com'
    """
    if not url_or_domain:
        return ""

    text = str(url_or_domain).strip().lower()

    if not text:
        return ""

    if not _URL_RE.match(text):
        text = "http://" + text

    try:
        host = urlparse(text).netloc
    except ValueError:
        return ""

    host = host.split("@")[-1].split(":")[0]
    host = host.removeprefix("www.")

    # Collapse 'in.linkedin.com' style country subdomains for well-known hosts.
    if any(host.endswith(ats) for ats in _ATS_HOSTS):
        for ats in _ATS_HOSTS:
            if host.endswith(ats):
                host = ats
                break
    elif host.count(".") > 1:
        parts = host.split(".")
        # Keep the registrable domain (strip arbitrary subdomains).
        host = ".".join(parts[-2:])

    return host


def normalize_agency_name(name: str | None) -> str:
    """Normalize an agency name for the name-based fallback dedupe path."""
    if not name:
        return ""

    text = str(name).strip()

    if not text:
        return ""

    if _URL_RE.match(text):
        path = text.split("?", 1)[0].rstrip("/")
        segment = path.rsplit("/", 1)[-1]

        if segment:
            text = _SLUG_SPLIT_RE.sub(" ", segment)

    text = text.lower().strip()
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    tokens = [token for token in text.split() if token not in AGENCY_SUFFIX_TOKENS]

    # Compact form removes differences between "abc staffing pvt ltd",
    # "ABC Staffing" and "abcstaffing".
    return "".join(tokens)


def normalize_job_url(url: str | None) -> str:
    """Normalize a job URL: strip tracking params, query noise, trailing slash.

    Returns '' when the input is not a usable URL.
    """
    if not url:
        return ""

    text = str(url).strip()

    if not text or not _URL_RE.match(text):
        return ""

    try:
        parsed = urlparse(text)
    except ValueError:
        return ""

    scheme = "https"
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"

    kept_params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in _URL_NOISE_PARAMS
    ]

    query = urlencode(kept_params)

    return urlunparse((scheme, netloc, path, "", query, ""))


def job_dedupe_fallback_key(
    agency_id: int | None,
    job_title: str | None,
    company_or_client: str | None,
    location: str | None,
) -> str:
    """Fallback job dedupe key: agency_id + normalized title + client + location."""
    title = _WHITESPACE_RE.sub(" ", (job_title or "").strip().lower())
    client = _WHITESPACE_RE.sub(" ", (company_or_client or "").strip().lower())
    loc = _WHITESPACE_RE.sub(" ", (location or "").strip().lower())

    loc = re.sub(r"[^a-z0-9\s]", "", loc)
    loc = loc.strip()

    return f"{agency_id or 0}|{title}|{client}|{loc}"


def extract_email_domain(email: str | None) -> str:
    """Return the domain part of an email, or '' when invalid."""
    if not email or "@" not in str(email):
        return ""

    return str(email).split("@", 1)[1].strip().lower()


# Free-mail providers are not "business" emails for outreach scoring.
FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com",
    "rediffmail.com", "live.com", "icloud.com", "aol.com", "protonmail.com",
}


def classify_email_type(email: str | None) -> str:
    """'business' | 'freemail' | 'unknown' - used for the +10 demand points."""
    domain = extract_email_domain(email)

    if not domain:
        return "unknown"

    return "freemail" if domain in FREEMAIL_DOMAINS else "business"
