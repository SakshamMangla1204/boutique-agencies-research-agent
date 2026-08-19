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
    - "research"   -> Groq     (llama-3.3-70b-versatile)
    - "contact"    -> Groq     (llama-3.3-70b-versatile)
    - "extraction" -> Groq     (llama-3.3-70b-versatile)

    Instances are cached per task.
    """
    key = task.strip().lower()

    if key in _llm_cache:
        return _llm_cache[key]

    if key == "discovery":
        api_key = _require_env("MISTRAL_API_KEY")
        llm = ChatMistralAI(
            model=MISTRAL_MODEL,
            temperature=0,
            api_key=api_key,
        )
    elif key in ("research", "contact", "extraction"):
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