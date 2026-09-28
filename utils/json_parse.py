"""Shared, tolerant JSON extraction from LLM responses.

The existing agents each carried their own copy of this fence/think-tag
stripping logic.  This module centralises it so the new AI agency agents can
reuse one tested implementation without changing the working existing agents.
"""
from __future__ import annotations

import json
import re

_THINK_RE = re.compile(r"(?si)<think>.*?</think>")
_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*|\s*```\s*$")


def strip_model_preamble(content: str) -> str:
    """Remove reasoning blocks some models emit before the real answer."""
    if not content:
        return ""

    return _THINK_RE.sub("", content).strip()


def strip_code_fences(content: str) -> str:
    """Remove a wrapping ```json ... ``` fence when present."""
    if not content:
        return ""

    text = content.strip()

    if not text.startswith("```"):
        return text

    lines = text.splitlines()

    if lines and lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()


def extract_json_object(content: str) -> dict:
    """Extract the first JSON object from an LLM response."""
    if not content:
        raise ValueError("Empty LLM response.")

    text = strip_code_fences(strip_model_preamble(content))

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Model response did not contain a JSON object.")

    data = json.loads(text[start:end + 1])

    if not isinstance(data, dict):
        raise ValueError("Model response was not a JSON object.")

    return data


def extract_json_array(content: str) -> list:
    """Extract the first JSON array from an LLM response."""
    if not content:
        raise ValueError("Empty LLM response.")

    text = strip_code_fences(strip_model_preamble(content))

    start = text.find("[")
    end = text.rfind("]")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Model response did not contain a JSON array.")

    data = json.loads(text[start:end + 1])

    if not isinstance(data, list):
        raise ValueError("Model response was not a JSON array.")

    return data


# ---------------------------------------------------------------------------
# Content trimming (token efficiency)
# ---------------------------------------------------------------------------

_NOISE_LINE_RE = re.compile(
    r"^\s*(cookie|cookies|privacy policy|terms (of|and)|all rights reserved|"
    r"accept all|manage preferences|subscribe|newsletter|sign in|log in|"
    r"follow us|share this|advertisement|skip to content|menu|home\s*$|"
    r"copyright|\u00a9)",
    re.IGNORECASE,
)

_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def trim_web_content(content: str, limit: int = 4000, line_limit: int = 400) -> str:
    """Strip navigation/footer/legal junk and cap length before any LLM call.

    Keeps source URLs and titles intact because Tavily result headers are
    formatted as 'URL: ...' lines, which are not treated as noise.
    """
    if not content:
        return ""

    if len(content) > 60000:
        content = content[:60000]

    kept: list[str] = []

    for index, line in enumerate(content.splitlines()):
        stripped = line.strip()

        if not stripped:
            kept.append("")
            continue

        # Always keep the source header lines emitted by the search formatter.
        if index and stripped.startswith(("URL:", "SOURCE:", "TITLE:")):
            kept.append(stripped)
            continue

        if len(stripped) < 3:
            continue

        if _NOISE_LINE_RE.match(stripped):
            continue

        # Drop very long unbroken token blobs (base64/JS bundles).
        if " " not in stripped and len(stripped) > 120:
            continue

        kept.append(_WHITESPACE_RE.sub(" ", stripped))

        if len(kept) >= line_limit:
            break

    text = _BLANK_LINES_RE.sub("\n\n", "\n".join(kept)).strip()

    if len(text) > limit:
        text = text[:limit]

    return text


def dedupe_urls(urls: list[str]) -> list[str]:
    """Order-preserving URL dedupe."""
    seen: set[str] = set()
    result: list[str] = []

    for url in urls:
        if not url:
            continue

        key = str(url).strip().rstrip("/")

        if not key or key in seen:
            continue

        seen.add(key)
        result.append(str(url).strip())

    return result
