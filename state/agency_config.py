"""Geographic discovery priority for the AI agency research agent.

Priority drives DISCOVERY ORDER ONLY.  It is intentionally kept separate from
the AI-demand score so the two never get conflated.

Priority table (per project spec):
    Gurugram                   100
    Noida                       95
    Delhi                       90
    Greater Noida               85
    Faridabad / Ghaziabad       75
    Other NCR                   70
    Chandigarh / Mohali / Jaipur 60
    Major Indian tech hubs      50
    Other India                 40
"""
from __future__ import annotations

import re

# Canonical city -> (tier label, priority score).
CITY_PRIORITY: dict[str, tuple[str, int]] = {
    "gurugram": ("NCR_TIER_1", 100),
    "gurgaon": ("NCR_TIER_1", 100),
    "noida": ("NCR_TIER_1", 95),
    "delhi": ("NCR_TIER_1", 90),
    "new delhi": ("NCR_TIER_1", 90),
    "greater noida": ("NCR_TIER_2", 85),
    "faridabad": ("NCR_TIER_3", 75),
    "ghaziabad": ("NCR_TIER_3", 75),
    "chandigarh": ("NORTH_TIER_1", 60),
    "mohali": ("NORTH_TIER_1", 60),
    "jaipur": ("NORTH_TIER_1", 60),
    "bengaluru": ("TECH_HUB", 50),
    "bangalore": ("TECH_HUB", 50),
    "hyderabad": ("TECH_HUB", 50),
    "pune": ("TECH_HUB", 50),
    "mumbai": ("TECH_HUB", 50),
    "chennai": ("TECH_HUB", 50),
    "kolkata": ("TECH_HUB", 50),
    "ahmedabad": ("TECH_HUB", 50),
}

# Aliases that should resolve to a canonical city.
CITY_ALIASES: dict[str, str] = {
    "gurgaon": "gurugram",
    "new delhi": "delhi",
    "delhi ncr": "delhi",
    "ncr": "delhi",
    "bangalore": "bengaluru",
    "greater noida west": "greater noida",
    "noida extension": "greater noida",
    "gurugram haryana": "gurugram",
    "mohali": "mohali",
}

# Cities that count as NCR presence.
NCR_CITIES = {
    "gurugram", "gurgaon", "noida", "delhi", "new delhi", "greater noida",
    "faridabad", "ghaziabad", "ghaziabad", "sonipat", "rohtak", "bahadurgarh",
}

NCR_STATE = "Haryana/Delhi/Uttar Pradesh"

DEFAULT_TIER = "OTHER_INDIA"
DEFAULT_PRIORITY = 40

# NCR-first, in strict discovery-priority order.
# (city label used for searching, canonical city, tier, priority)
NCR_SEARCH_ORDER: list[tuple[str, str, str, int]] = [
    ("Gurugram", "gurugram", "NCR_TIER_1", 100),
    ("Gurgaon", "gurugram", "NCR_TIER_1", 100),
    ("Noida", "noida", "NCR_TIER_1", 95),
    ("Delhi", "delhi", "NCR_TIER_1", 90),
    ("Delhi NCR", "delhi", "NCR_TIER_1", 90),
    ("Greater Noida", "greater noida", "NCR_TIER_2", 85),
    ("Faridabad", "faridabad", "NCR_TIER_3", 75),
    ("Ghaziabad", "ghaziabad", "NCR_TIER_3", 75),
]

# Expanded order, applied after the NCR batch.
EXPANSION_SEARCH_ORDER: list[tuple[str, str, str, int]] = [
    ("Chandigarh", "chandigarh", "NORTH_TIER_1", 60),
    ("Mohali", "mohali", "NORTH_TIER_1", 60),
    ("Jaipur", "jaipur", "NORTH_TIER_1", 60),
    ("Bengaluru", "bengaluru", "TECH_HUB", 50),
    ("Hyderabad", "hyderabad", "TECH_HUB", 50),
    ("Pune", "pune", "TECH_HUB", 50),
    ("Mumbai", "mumbai", "TECH_HUB", 50),
    ("Chennai", "chennai", "TECH_HUB", 50),
]

_CLEAN_RE = re.compile(r"[^a-z0-9\s]")


def canonical_city(city: str | None) -> str:
    """Map a free-text city to its canonical lowercase form ('' if unknown)."""
    if not city:
        return ""

    text = _CLEAN_RE.sub(" ", str(city).lower())
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    if text in CITY_ALIASES:
        text = CITY_ALIASES[text]

    if text in CITY_PRIORITY:
        return text

    # Substring match for verbose values like "Sector 62, Noida, UP".
    for known in sorted(list(CITY_PRIORITY) + list(CITY_ALIASES), key=len, reverse=True):
        if known in text:
            return CITY_ALIASES.get(known, known)

    return text


def city_priority(city: str | None) -> tuple[str, int]:
    """Return (geographic_tier, geographic_priority_score) for a city."""
    canonical = canonical_city(city)

    if canonical in CITY_PRIORITY:
        return CITY_PRIORITY[canonical]

    return DEFAULT_TIER, DEFAULT_PRIORITY


def geographic_priority_score(city: str | None) -> int:
    return city_priority(city)[1]


def geographic_tier(city: str | None) -> str:
    return city_priority(city)[0]


def has_ncr_presence(city_or_area: str | None) -> str:
    """Return 'YES' / 'POSSIBLY' / 'NO' / 'UNKNOWN' for NCR presence."""
    if not city_or_area:
        return "UNKNOWN"

    text = _CLEAN_RE.sub(" ", str(city_or_area).lower())
    canonical = canonical_city(city_or_area)

    if canonical in NCR_CITIES:
        return "YES"

    if "ncr" in text or "national capital region" in text:
        return "YES"

    if any(city in text for city in NCR_CITIES):
        return "YES"

    # Mentions India but no NCR city -> the agency may still serve NCR.
    if "india" in text:
        return "POSSIBLY"

    return "NO"


def is_ncr(city_or_area: str | None) -> bool:
    return has_ncr_presence(city_or_area) == "YES"
