import os

from dotenv import load_dotenv

load_dotenv()

from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI

# Current model selection based on official provider documentation.
GROQ_MODEL = "openai/gpt-oss-120b"
MISTRAL_MODEL = "mistral-large-latest"

_llm_cache = {}


def _require_env(name: str) -> str:
    """Return a required environment variable or fail with a clear message."""
    value = os.getenv(name, "").strip()

    if not value:
        print(f"{name} is missing from .env")
        raise ValueError(f"{name} is missing from .env")

    return value


def get_llm(task: str):
    """Return the configured LangChain LLM for a pipeline task.

    - "discovery"  -> Mistral  (mistral-large-latest)
    - "research"   -> Groq     (openai/gpt-oss-120b)
    - "contact"    -> Groq     (openai/gpt-oss-120b)
    - "extraction" -> Groq     (openai/gpt-oss-120b)

    AI agency / AI Engineer job research agent tasks (all Groq):
    - "agency_discovery"   -> extract agency candidates from search results
    - "agency_research"    -> authoritative agency profile fields
    - "demand_research"    -> AI/technical hiring-demand evidence
    - "job_research"       -> structured AI Engineer job openings
    - "job_relevance"      -> roadmap relevance classification + reason
    - "contact_research"   -> publicly published decision-maker contacts

    Instances are cached per task.  No new provider or credential is
    introduced: the pipeline reuses the existing Groq and Mistral keys.
    """
    key = task.strip().lower()

    if key in _llm_cache:
        return _llm_cache[key]

    groq_tasks = (
        "research",
        "contact",
        "extraction",
        "agency_discovery",
        "agency_research",
        "demand_research",
        "job_research",
        "job_relevance",
        "contact_research",
    )

    if key == "discovery":
        api_key = _require_env("MISTRAL_API_KEY")
        llm = ChatMistralAI(
            model=MISTRAL_MODEL,
            temperature=0,
            api_key=api_key,
        )
    elif key in groq_tasks:
        api_key = _require_env("GROQ_API_KEY")
        llm = ChatGroq(
            model=GROQ_MODEL,
            temperature=0,
            api_key=api_key,
        )
    else:
        raise ValueError(f"Unknown LLM task: {task!r}")

    _llm_cache[key] = llm
    return llm