"""Job relevance classification against the AI Engineer roadmap.

Two-stage design (cheap -> expensive):

1. `classify_heuristic` runs the deterministic roadmap classifier from
   `agents.ai_jobs.roadmap`.  It is free and always runs.
2. `classify_with_llm` is only called for jobs that the heuristic marks as
   plausible candidates, and only when the JD text is substantial enough to
   justify a call.  The LLM may refine the label, but its output is validated
   against the allowed vocabulary so it cannot invent a new category.

The final record always carries `relevance_source` ("heuristic" or "llm") so it
is auditable which stage produced the label.
"""
from __future__ import annotations

from services.llm import get_llm
from utils.json_parse import extract_json_object

from agents.ai_jobs import prompts
from agents.ai_jobs import roadmap

# Minimum JD length (characters) that justifies an LLM relevance call.
MIN_JD_CHARS_FOR_LLM = 120

_MAX_JD_CHARS = 3000


def normalize_relevance(value) -> str:
    """Coerce any label to one of the three allowed values."""
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")

    if text in roadmap.RELEVANCE_LABELS:
        return text

    # Tolerate common model variations.
    if "NOT" in text and "RELEVANT" in text:
        return roadmap.NOT_RELEVANT

    if "TARGET" in text:
        return roadmap.TARGET_AI_ENGINEER

    if "RELATED" in text or "ADJACENT" in text:
        return roadmap.RELATED_AI_ENGINEERING

    return roadmap.NOT_RELEVANT


def _job_text(job: dict) -> str:
    """Combine the JD-bearing fields of a job into one string."""
    return " ".join(
        str(job.get(key) or "")
        for key in ("jd_summary", "required_skills", "preferred_skills", "description")
    ).strip()


def classify_heuristic(job: dict) -> dict:
    """Deterministic first pass. Returns the full roadmap-derived field set."""
    jd_text = _job_text(job)
    fields = roadmap.build_job_record_fields(job.get("job_title") or "", jd_text)

    # The explicit experience field from the source beats inferred JD text.
    explicit_experience = (job.get("experience_required") or "").strip()

    if explicit_experience:
        fields["experience_bucket"] = roadmap.detect_experience_bucket(
            explicit_experience
        )

    fields["fresher_friendly"] = roadmap.classify_fresher(explicit_experience, jd_text)
    fields["relevance_source"] = "heuristic"

    return fields


def should_use_llm(job: dict, heuristic: dict) -> bool:
    """Decide whether an LLM call is worth it for this job.

    This is the token-efficiency gate: clearly-target and clearly-irrelevant
    jobs are never sent to the LLM.
    """
    jd_text = " ".join(
        str(job.get(key) or "")
        for key in ("jd_summary", "required_skills", "preferred_skills")
    ).strip()

    if len(jd_text) < MIN_JD_CHARS_FOR_LLM:
        # Not enough evidence to justify spending tokens.
        return False

    relevance = heuristic.get("job_relevance")
    score = heuristic.get("job_relevance_score") or 0

    # Borderline "related" jobs are exactly where an LLM adds value.
    if relevance == roadmap.RELATED_AI_ENGINEERING:
        return True

    # Targets below the high-confidence band get a second opinion.
    if relevance == roadmap.TARGET_AI_ENGINEER and score < 75:
        return True

    return False


def classify_with_llm(job: dict, heuristic: dict) -> dict:
    """Refine a borderline classification with the LLM (validated output)."""
    jd_text = " ".join(
        str(job.get(key) or "")
        for key in ("jd_summary", "required_skills", "preferred_skills")
    ).strip()[:_MAX_JD_CHARS]

    try:
        llm = get_llm("job_relevance")
        result = llm.invoke(
            prompts.JOB_RELEVANCE_PROMPT.format(
                roadmap_url=prompts.ROADMAP_URL,
                job_title=job.get("job_title") or "",
                location=job.get("location") or "",
                jd_text=jd_text,
                required_skills=job.get("required_skills") or "",
                preferred_skills=job.get("preferred_skills") or "",
                rules=prompts.NO_FABRICATION_RULES,
            )
        )
        data = extract_json_object(result.content)
    except Exception as exc:
        print(f"    [job_relevance] LLM failure, keeping heuristic: {exc}")
        return heuristic

    refined = dict(heuristic)

    refined["job_relevance"] = normalize_relevance(data.get("job_relevance"))

    try:
        score = int(data.get("job_relevance_score"))
        refined["job_relevance_score"] = max(0, min(100, score))
    except (TypeError, ValueError):
        pass

    reason = str(data.get("relevance_reason") or "").strip()

    if reason:
        refined["relevance_reason"] = reason

    domain = str(data.get("ai_domain") or "").strip()

    if domain in roadmap.AI_DOMAIN_KEYWORDS:
        refined["ai_domain"] = domain

    for flag in (
        "llm",
        "genai",
        "rag",
        "agents",
        "nlp",
        "computer_vision",
        "model_integration",
        "ai_application_development",
    ):
        if isinstance(data.get(flag), bool):
            refined[flag] = data[flag]

    fresher = str(data.get("fresher_friendly") or "").strip().upper()

    if fresher in roadmap.FRESHER_FRIENDLY_VALUES:
        refined["fresher_friendly"] = fresher

    refined["relevance_source"] = "llm"

    return refined


def classify_job(job: dict, use_llm: bool = True) -> dict:
    """Classify one job, returning the complete roadmap-derived field set."""
    heuristic = classify_heuristic(job)

    if not use_llm or not should_use_llm(job, heuristic):
        return heuristic

    return classify_with_llm(job, heuristic)


def classify_jobs(jobs: list, use_llm: bool = True) -> list:
    """Classify a batch of jobs, preserving order."""
    classified: list[dict] = []

    for job in jobs:
        fields = classify_job(job, use_llm=use_llm)
        merged = dict(job)
        merged.update(fields)
        classified.append(merged)

    return classified


def count_by_relevance(jobs: list) -> dict:
    """Tally jobs per relevance label."""
    counts = {label: 0 for label in roadmap.RELEVANCE_LABELS}

    for job in jobs:
        label = job.get("job_relevance")

        if label in counts:
            counts[label] += 1

    return counts
