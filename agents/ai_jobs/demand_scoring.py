"""AI-demand scoring for recruitment agencies.

Exact rubric from the project spec (max 100):

    AI/ML recruitment specialization      25   (min of explicit signals)
    active AI/ML hiring evidence          25
    multiple/bulk AI hiring               20
    contract technical staffing           10
    relevant decision maker identified    10
    professional/business email identified 10

Geographic priority is tracked in a SEPARATE field and is never added here.
"""
from __future__ import annotations

from services.db.dedupe import classify_email_type

# Individual component maxima.
SCORE_SPECIALIZATION = 25
SCORE_ACTIVE_HIRING = 25
SCORE_BULK_HIRING = 20
SCORE_CONTRACT_STAFFING = 10
SCORE_DECISION_MAKER = 10
SCORE_BUSINESS_EMAIL = 10

MAX_SCORE = (
    SCORE_SPECIALIZATION
    + SCORE_ACTIVE_HIRING
    + SCORE_BULK_HIRING
    + SCORE_CONTRACT_STAFFING
    + SCORE_DECISION_MAKER
    + SCORE_BUSINESS_EMAIL
)

# Demand level thresholds.
LEVEL_HIGH = 70
LEVEL_MEDIUM = 45
LEVEL_LOW = 20

# Roles that count as a "relevant decision maker" for outreach.
DECISION_MAKER_ROLE_KEYWORDS = (
    "recruitment head",
    "talent acquisition head",
    "head of talent",
    "head of recruitment",
    "ai practice lead",
    "practice head",
    "delivery head",
    "managing director",
    "founder",
    "co-founder",
    "ceo",
    "director",
    "partner",
    "vp talent",
    "talent lead",
    "staffing head",
    "business head",
)


def _truthy(value) -> bool:
    """Interpret tri-state booleans coming from the LLM/JSON layer."""
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"true", "yes", "y", "1"}


def is_decision_maker(role: str | None) -> bool:
    """True when a contact role counts as a relevant decision maker."""
    if not role:
        return False

    lowered = str(role).lower()

    return any(keyword in lowered for keyword in DECISION_MAKER_ROLE_KEYWORDS)


def compute_ai_demand_score(
    technical_recruitment=None,
    ai_recruitment=None,
    genai_recruitment=None,
    contract_staffing=None,
    bulk_hiring=None,
    active_ai_roles: int | None = None,
    estimated_ai_positions: int | None = None,
    has_multiple_openings: bool = False,
    contacts: list[dict] | None = None,
) -> tuple[int, str, dict]:
    """Compute the AI-demand score.

    Returns (score, level, breakdown).  Only publicly supported evidence earns
    points; unknown values score 0 rather than being guessed.
    """
    breakdown: dict[str, int] = {}

    technical = _truthy(technical_recruitment)
    ai = _truthy(ai_recruitment)
    genai = _truthy(genai_recruitment)
    contract = _truthy(contract_staffing)
    bulk = _truthy(bulk_hiring)

    # --- 1. AI/ML recruitment specialization (25) --------------------------
    if genai or ai:
        breakdown["specialization"] = SCORE_SPECIALIZATION
    elif technical:
        breakdown["specialization"] = 12
    else:
        breakdown["specialization"] = 0

    # --- 2. Active AI/ML hiring evidence (25) -------------------------------
    active_roles = active_ai_roles if isinstance(active_ai_roles, int) else None

    if active_roles is None and isinstance(estimated_ai_positions, int):
        active_roles = estimated_ai_positions

    if active_roles is not None and active_roles > 0:
        breakdown["active_hiring"] = SCORE_ACTIVE_HIRING
    elif ai or genai:
        # Claimed AI recruitment with no verified openings: partial credit only.
        breakdown["active_hiring"] = 10
    else:
        breakdown["active_hiring"] = 0

    # --- 3. Multiple / bulk AI hiring (20) ----------------------------------
    if bulk or has_multiple_openings or (active_roles is not None and active_roles >= 3):
        breakdown["bulk_hiring"] = SCORE_BULK_HIRING
    elif active_roles is not None and active_roles > 1:
        breakdown["bulk_hiring"] = 10
    else:
        breakdown["bulk_hiring"] = 0

    # --- 4. Contract technical staffing (10) --------------------------------
    breakdown["contract_staffing"] = SCORE_CONTRACT_STAFFING if contract else 0

    # --- 5. Relevant decision maker identified (10) -------------------------
    decision_maker_found = any(
        is_decision_maker((contact or {}).get("role"))
        for contact in (contacts or [])
    )
    breakdown["decision_maker"] = SCORE_DECISION_MAKER if decision_maker_found else 0

    # --- 6. Professional/business email identified (10) ---------------------
    business_email_found = False

    for contact in contacts or []:
        email = (contact or {}).get("email")

        if email and classify_email_type(email) == "business":
            business_email_found = True
            break

    breakdown["business_email"] = SCORE_BUSINESS_EMAIL if business_email_found else 0

    score = sum(breakdown.values())
    score = max(0, min(MAX_SCORE, score))

    return score, demand_level(score), breakdown


def demand_level(score: int | None) -> str:
    """Map a score to a qualitative demand level."""
    if score is None:
        return "UNKNOWN"

    if score >= LEVEL_HIGH:
        return "HIGH"

    if score >= LEVEL_MEDIUM:
        return "MEDIUM"

    if score >= LEVEL_LOW:
        return "LOW"

    return "VERY_LOW"


def confidence_for(score: int | None, sources: int = 0, has_hiring_evidence: bool = False) -> str:
    """Overall confidence in the agency record."""
    if score is None:
        return "UNKNOWN"

    if score >= LEVEL_HIGH and sources >= 2 and has_hiring_evidence:
        return "HIGH"

    if score >= LEVEL_MEDIUM and sources >= 1:
        return "MEDIUM"

    if sources >= 1:
        return "LOW"

    return "UNKNOWN"
