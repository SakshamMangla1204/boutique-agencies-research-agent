"""AI Engineer roadmap taxonomy and job-relevance classification.

Source of truth for the target role family:
    https://roadmap.sh/ai-engineer

This module is deliberately deterministic (no LLM).  It is used in two places:

1. as a *cheap* pre-filter, so expensive LLM research only runs on plausible
   AI-engineering job candidates, and
2. as a guardrail for the LLM relevance classifier (which may override the
   heuristic score, but only within the vocabulary defined here).

The system must NOT degrade into a generic ML-job scraper, so the title sets
below distinguish:
  * TARGET_TITLES              - AI-engineering roles, always in scope
  * CONDITIONAL_TITLES         - classic ML/CV/NLP/MLOps titles that are in
                                 scope ONLY when the JD shows practical AI
                                 engineering work (LLMs, RAG, agents, ...)
  * EXCLUDED_TITLE_PATTERNS    - research/analytics/data-engineering roles that
                                 are not AI application engineering
"""

from __future__ import annotations

import re

ROADMAP_URL = "https://roadmap.sh/ai-engineer"

# ---------------------------------------------------------------------------
# Relevance labels
# ---------------------------------------------------------------------------

TARGET_AI_ENGINEER = "TARGET_AI_ENGINEER"
RELATED_AI_ENGINEERING = "RELATED_AI_ENGINEERING"
NOT_RELEVANT = "NOT_RELEVANT"

RELEVANCE_LABELS = (
    TARGET_AI_ENGINEER,
    RELATED_AI_ENGINEERING,
    NOT_RELEVANT,
)

# ---------------------------------------------------------------------------
# Title sets
# ---------------------------------------------------------------------------

# Roles that are in scope by title alone (still scored by JD content).
TARGET_TITLES = (
    "ai engineer",
    "artificial intelligence engineer",
    "generative ai engineer",
    "genai engineer",
    "gen ai engineer",
    "llm engineer",
    "large language model engineer",
    "ai application engineer",
    "llm application engineer",
    "rag engineer",
    "agentic ai engineer",
    "ai agent engineer",
    "applied ai engineer",
    "ai developer",
    "genai developer",
    "llm developer",
    "ai solutions engineer",
    "ai integration engineer",
    "ai automation engineer",
    "ai platform engineer",
)

# ML-family titles: in scope only if the JD shows practical AI engineering.
CONDITIONAL_TITLES = (
    "machine learning engineer",
    "ml engineer",
    "nlp engineer",
    "computer vision engineer",
    "cv engineer",
    "mlops engineer",
    "machine learning developer",
    "ml developer",
    "machine learning solutions engineer",
)

# Excluded / low-priority title patterns (research, analytics, data plumbing).
EXCLUDED_TITLE_PATTERNS = (
    r"\bresearch scientist\b",
    r"\bai research scientist\b",
    r"\bml researcher\b",
    r"\bmachine learning researcher\b",
    r"\bdeep learning researcher\b",
    r"\bresearch engineer\b",
    r"\bdata analyst\b",
    r"\bbusiness analyst\b",
    r"\bbi analyst\b",
    r"\bdata engineer\b",
    r"\banalytics engineer\b",
    r"\bstatistician\b",
    r"\bdata scientist\b",
    r"\bembedded ai\b",
    r"\bfpga\b",
    r"\bsemiconductor\b",
    r"\bhardware\b",
)

# ---------------------------------------------------------------------------
# AI-engineering technology vocabulary (roadmap-aligned)
# ---------------------------------------------------------------------------

# Core AI-engineering technologies, grouped by weight.  A weight of 2 marks
# strong AI-application-engineering signals; 1 marks supporting signals.
TECHNOLOGY_WEIGHTS = {
    # --- Strong: modern AI application engineering ---
    "llm": 2,
    "large language model": 2,
    "generative ai": 2,
    "genai": 2,
    "gen ai": 2,
    "rag": 2,
    "retrieval augmented generation": 2,
    "retrieval-augmented generation": 2,
    "langchain": 2,
    "langgraph": 2,
    "llamaindex": 2,
    "agentic": 2,
    "ai agent": 2,
    "ai agents": 2,
    "vector database": 2,
    "vector db": 2,
    "vector store": 2,
    "pinecone": 2,
    "weaviate": 2,
    "qdrant": 2,
    "chroma": 2,
    "milvus": 2,
    "faiss": 2,
    "prompt engineering": 2,
    "fine-tuning": 2,
    "fine tuning": 2,
    "lora": 2,
    "peft": 2,
    "embeddings": 2,
    "openai": 2,
    "gpt-4": 2,
    "gpt4": 2,
    "gemini": 2,
    "claude": 2,
    "anthropic": 2,
    "ollama": 2,
    "hugging face": 2,
    "huggingface": 2,
    "transformers": 2,
    "model serving": 2,
    "inference": 2,
    "vllm": 2,
    "ai integration": 2,
    "ai api": 2,
    "ai apis": 2,
    "ai application": 2,
    "ai applications": 2,
    "ai pipeline": 2,
    "ai pipelines": 2,
    "production ai": 2,
    "copilot": 2,
    "chatbot": 2,
    "conversational ai": 2,
    "semantic search": 2,
    "guardrails": 2,
    "evals": 2,
    "evaluation": 2,
    "mcp": 2,
    "multimodal": 2,
    # --- Supporting: general AI/ML engineering ---
    "python": 1,
    "pytorch": 1,
    "tensorflow": 1,
    "keras": 1,
    "scikit-learn": 1,
    "sklearn": 1,
    "numpy": 1,
    "pandas": 1,
    "nlp": 1,
    "natural language processing": 1,
    "computer vision": 1,
    "opencv": 1,
    "deep learning": 1,
    "neural network": 1,
    "neural networks": 1,
    "model deployment": 1,
    "mlops": 1,
    "docker": 1,
    "kubernetes": 1,
    "fastapi": 1,
    "flask": 1,
    "rest api": 1,
    "microservices": 1,
    "sql": 1,
    "spark": 1,
    "airflow": 1,
    "aws": 1,
    "azure": 1,
    "gcp": 1,
    "gpu": 1,
}

# Technology -> boolean job_openings column.
TECHNOLOGY_FLAGS = {
    "llm": ("llm", "large language model", "llms", "large language models"),
    "genai": ("generative ai", "genai", "gen ai", "openai", "gpt-4", "gpt4", "gemini", "claude", "anthropic", "ollama"),
    "rag": ("rag", "retrieval augmented generation", "retrieval-augmented generation", "llamaindex", "vector database", "vector db", "vector store", "embeddings", "semantic search"),
    "agents": ("agentic", "ai agent", "ai agents", "langgraph", "langchain", "crewai", "autogen", "mcp"),
    "nlp": ("nlp", "natural language processing", "transformers", "hugging face", "huggingface"),
    "computer_vision": ("computer vision", "opencv", "image processing", "yolo", "segmentation"),
    "model_integration": ("model serving", "inference", "vllm", "ai api", "ai apis", "ai integration", "model deployment", "pretrained", "pre-trained", "fine-tuning", "fine tuning", "lora", "peft", "openai", "gemini", "claude", "hugging face", "huggingface"),
    "ai_application_development": ("ai application", "ai applications", "ai pipeline", "ai pipelines", "production ai", "prompt engineering", "chatbot", "conversational ai", "copilot", "ai automation", "python"),
}

# AI domains used for the `ai_domain` column.
AI_DOMAIN_KEYWORDS = {
    "GenAI/LLM": ("llm", "generative ai", "genai", "gen ai", "gpt", "claude", "gemini", "prompt engineering"),
    "RAG/Retrieval": ("rag", "retrieval", "vector", "embedding", "semantic search"),
    "Agentic AI": ("agentic", "ai agent", "langgraph", "crewai", "autogen", "mcp"),
    "NLP": ("nlp", "natural language", "transformers", "text classification", "named entity"),
    "Computer Vision": ("computer vision", "opencv", "image", "video", "segmentation", "detection"),
    "Speech/Audio": ("speech", "asr", "tts", "audio", "voice"),
    "MLOps/Platform": ("mlops", "model serving", "inference", "kubernetes", "deployment", "observability"),
    "Conversational AI": ("chatbot", "conversational", "virtual assistant", "voice bot"),
    "Recommendation": ("recommendation", "ranking", "personalization"),
}

# ---------------------------------------------------------------------------
# Fresher / experience classification
# ---------------------------------------------------------------------------

FRESHER_BUCKETS = ("0 years", "0-1", "0-2", "1-2", "2-3", "3+", "not specified")

FRESHER_FRIENDLY_VALUES = ("YES", "POSSIBLY", "NO", "UNKNOWN")

_EXP_RANGE_RE = re.compile(
    r"(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*(?:\+)?\s*(?:years?|yrs?)",
    re.IGNORECASE,
)
_EXP_PLUS_RE = re.compile(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)", re.IGNORECASE)
_EXP_SINGLE_RE = re.compile(r"(\d{1,2})\s*(?:years?|yrs?)", re.IGNORECASE)
_FRESHER_RE = re.compile(
    r"\b(fresher|freshers|entry[- ]level|graduate|trainee|internship|"
    r"no prior experience|0\s*[-to]\s*1\s*year|0\s*[-to]\s*2\s*years?)\b",
    re.IGNORECASE,
)


def normalize_title(title: str) -> str:
    """Lowercase/compact a job title for matching."""
    if not title:
        return ""

    text = str(title).lower()
    text = re.sub(r"[^a-z0-9+#./ ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_experience_bucket(text: str) -> str:
    """Map free text to one of FRESHER_BUCKETS ('not specified' when absent)."""
    if not text:
        return "not specified"

    text = str(text)

    match = _EXP_RANGE_RE.search(text)

    if match:
        low = int(match.group(1))
        high = int(match.group(2))

        if low == 0 and high <= 1:
            return "0-1"
        if low == 0 and high <= 2:
            return "0-2"
        if low <= 1 and high <= 2:
            return "1-2"
        if low <= 2 and high <= 3:
            return "2-3"
        if low == 0:
            return "0-1"
        if high >= 3 or low >= 3:
            return "3+"

    if _FRESHER_RE.search(text):
        return "0 years"

    # "3+ years", "5+ yrs" -> open-ended upper bound.
    match = _EXP_PLUS_RE.search(text)

    if match:
        years = int(match.group(1))

        if years == 0:
            return "0 years"
        if years == 1:
            return "0-1"
        if years == 2:
            return "1-2"
        return "3+"

    match = _EXP_SINGLE_RE.search(text)

    if match:
        years = int(match.group(1))

        if years == 0:
            return "0 years"
        if years == 1:
            return "0-1"
        if years == 2:
            return "1-2"
        if years == 3:
            return "2-3"
        return "3+"

    return "not specified"


def classify_fresher(experience_required: str, jd_text: str = "") -> str:
    """Return YES / POSSIBLY / NO / UNKNOWN from experience + JD wording."""
    combined = f"{experience_required or ''} {jd_text or ''}".strip()
    bucket = detect_experience_bucket(combined)
    lowered = combined.lower()

    if bucket in ("0 years", "0-1"):
        return "YES"

    if bucket == "0-2":
        return "YES"

    if bucket == "1-2":
        return "POSSIBLY"

    if bucket in ("2-3", "3+"):
        return "NO"

    # No explicit experience information.
    if _FRESHER_RE.search(lowered):
        return "POSSIBLY"

    return "UNKNOWN"


def detect_ai_domain(text: str) -> str:
    """Best-effort AI domain label, or '' when nothing matches."""
    if not text:
        return ""

    lowered = str(text).lower()
    best_domain = ""
    best_hits = 0

    for domain, keywords in AI_DOMAIN_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in lowered)

        if hits > best_hits:
            best_hits = hits
            best_domain = domain

    return best_domain


def extract_technologies(text: str, limit: int = 25) -> list[str]:
    """Return matched technologies from the roadmap vocabulary, deduped."""
    if not text:
        return []

    lowered = str(text).lower()
    found: list[str] = []
    seen: set[str] = set()

    for technology in TECHNOLOGY_WEIGHTS:
        if technology in lowered and technology not in seen:
            seen.add(technology)
            found.append(technology)

            if len(found) >= limit:
                break

    return found


def technology_signal_score(text: str) -> int:
    """Weighted count of AI-engineering technology mentions."""
    if not text:
        return 0

    lowered = str(text).lower()
    return sum(weight for tech, weight in TECHNOLOGY_WEIGHTS.items() if tech in lowered)


def technology_flags(text: str) -> dict:
    """Compute the boolean AI-signal columns for a job record."""
    lowered = (text or "").lower()

    return {
        column: any(keyword in lowered for keyword in keywords)
        for column, keywords in TECHNOLOGY_FLAGS.items()
    }


def title_strength(title: str) -> tuple:
    """Classify a title alone.

    Returns (bucket, score) where bucket is one of "target", "conditional",
    "excluded", "other" and score is a 0-50 heuristic.
    """
    normalized = normalize_title(title)

    if not normalized:
        return "other", 0

    for pattern in EXCLUDED_TITLE_PATTERNS:
        if re.search(pattern, normalized):
            # A clearly AI-engineering title wins over a weak exclude match
            # (e.g. "AI Engineer (PhD preferred)" is still a target role).
            if any(target in normalized for target in TARGET_TITLES):
                break
            return "excluded", 0

    # Longest match first so "generative ai engineer" beats "ai engineer".
    for target in sorted(TARGET_TITLES, key=len, reverse=True):
        if target in normalized:
            if target in ("ai platform engineer", "ai solutions engineer", "ai integration engineer"):
                return "target", 40
            return "target", 50

    for conditional in sorted(CONDITIONAL_TITLES, key=len, reverse=True):
        if conditional in normalized:
            return "conditional", 20

    return "other", 5


# ---------------------------------------------------------------------------
# Composite relevance classification
# ---------------------------------------------------------------------------

# Score boundaries for the deterministic classifier.
_TARGET_MIN_SCORE = 60
_RELATED_MIN_SCORE = 35


def classify_job_relevance(
    job_title: str,
    jd_text: str = "",
    required_skills: str = "",
    preferred_skills: str = "",
    technologies: str = "",
) -> tuple:
    """Classify a job into TARGET_AI_ENGINEER / RELATED_AI_ENGINEERING / NOT_RELEVANT.

    This is the deterministic first pass (no LLM).  It deliberately does NOT
    rely on the title alone: the JD body, required skills, preferred skills and
    extracted technologies all contribute.

    Returns (relevance, score, reason).
    """
    title_bucket, title_score = title_strength(job_title)

    content = " ".join(
        part for part in (jd_text, required_skills, preferred_skills, technologies) if part
    )
    content_score = technology_signal_score(content)
    flags = technology_flags(content)
    strong_flags = [
        key
        for key in ("llm", "genai", "rag", "agents", "model_integration", "ai_application_development")
        if flags.get(key)
    ]

    # ---- Hard exclusion: clear cut for research/analytics/data roles --------
    if title_bucket == "excluded":
        # Even then, a JD saturated with LLM/RAG/agent work can rescue it.
        if content_score >= 12 and len(strong_flags) >= 3:
            score = min(60, 35 + len(strong_flags) * 4)
            return (
                RELATED_AI_ENGINEERING,
                score,
                f"Excluded-by-title role ('{job_title}') but JD shows substantial "
                f"practical AI engineering signals: {', '.join(strong_flags)}.",
            )

        return (
            NOT_RELEVANT,
            0,
            f"Title matches an excluded research/analytics/data pattern "
            f"('{job_title}'); no practical AI-engineering evidence in the JD.",
        )

    # ---- Target titles -----------------------------------------------------
    if title_bucket == "target":
        score = title_score + min(50, content_score * 2)

        if not strong_flags:
            # Target title but no AI technology evidence at all: verify, do not
            # blindly trust the title.
            score = min(score, 55)
            return (
                RELATED_AI_ENGINEERING,
                score,
                "Title is in the AI-engineer family but the JD shows no explicit "
                "LLM/GenAI/RAG/agent/technology evidence.",
            )

        return (
            TARGET_AI_ENGINEER,
            min(100, score),
            f"AI-engineer title ('{job_title}') with practical AI engineering "
            f"evidence: {', '.join(strong_flags)}.",
        )

    # ---- Conditional ML-family titles -------------------------------------
    if title_bucket == "conditional":
        if content_score >= 10 and strong_flags:
            score = min(85, 35 + min(40, content_score * 2))
            return (
                TARGET_AI_ENGINEER,
                score,
                f"ML-family title ('{job_title}') whose JD is centred on practical "
                f"AI engineering: {', '.join(strong_flags)}.",
            )

        if content_score >= 6:
            return (
                RELATED_AI_ENGINEERING,
                min(60, 30 + content_score),
                f"ML-family title ('{job_title}') with partial AI-engineering "
                f"signals; include conditionally.",
            )

        return (
            RELATED_AI_ENGINEERING,
            min(45, 25 + content_score),
            f"ML-family title ('{job_title}') without LLM/GenAI/RAG/agent "
            f"evidence in the JD.",
        )

    # ---- Title not in either list: judge purely on content -----------------
    if content_score >= 14 and len(strong_flags) >= 2:
        return (
            TARGET_AI_ENGINEER,
            min(80, 40 + content_score),
            f"Non-standard title ('{job_title}') but the JD is clearly practical "
            f"AI engineering: {', '.join(strong_flags)}.",
        )

    if content_score >= 6:
        return (
            RELATED_AI_ENGINEERING,
            min(55, 25 + content_score),
            f"Non-standard title ('{job_title}') with some AI-engineering "
            f"content signals.",
        )

    return (
        NOT_RELEVANT,
        min(20, content_score),
        f"Neither the title ('{job_title}') nor the JD indicate AI-engineering "
        f"work.",
    )


def build_job_record_fields(job_title: str, jd_text: str = "") -> dict:
    """Derive all roadmap-dependent columns for a job from title + JD text.

    Returns a dict containing relevance, score, reason, technology flags,
    ai_domain, detected technologies, experience bucket and fresher_friendly.
    """
    relevance, score, reason = classify_job_relevance(job_title, jd_text)

    flags = technology_flags(jd_text)

    return {
        "job_relevance": relevance,
        "job_relevance_score": score,
        "relevance_reason": reason,
        "technologies": ", ".join(extract_technologies(jd_text)),
        "ai_domain": detect_ai_domain(jd_text),
        "experience_bucket": detect_experience_bucket(jd_text),
        "fresher_friendly": classify_fresher(jd_text, jd_text),
        **flags,
    }

