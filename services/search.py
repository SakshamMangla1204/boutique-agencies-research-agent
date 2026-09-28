"""Tavily search wrapper for the AI agency research pipeline.

Differences from the existing `agents/research.py` helper:
  * returns structured results (url/title/content) instead of one blob, so
    source URLs can be stored in `research_sources` and deduplicated;
  * trims content before it ever reaches an LLM (token efficiency);
  * tracks every query used so the same source is not re-fetched.
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from tavily import TavilyClient

from utils.json_parse import trim_web_content

load_dotenv()

MAX_RESULTS_PER_QUERY = 8
# Content kept per individual result before formatting.
MAX_CONTENT_PER_RESULT = 2500

_client: Optional[TavilyClient] = None

# Queries already executed in this process - avoids repeating the same search
# across nodes (discovery, demand research, job research).
_SEARCH_CACHE: dict[str, list[dict]] = {}


def get_tavily() -> TavilyClient:
    """Lazily build the Tavily client so importing this module never fails."""
    global _client

    if _client is None:
        api_key = os.getenv("TAVILY_API_KEY", "").strip()

        if not api_key:
            raise ValueError("TAVILY_API_KEY is missing from .env")

        _client = TavilyClient(api_key=api_key)

    return _client


def search(
    query: str,
    max_results: int = MAX_RESULTS_PER_QUERY,
    search_depth: str = "basic",
    use_cache: bool = True,
) -> list[dict]:
    """Run one Tavily search and return trimmed, structured results.

    Returns a list of {url, title, content, score}.  On failure returns [] so a
    single bad query cannot abort a whole pipeline run.
    """
    if not query or not query.strip():
        return []

    cache_key = f"{query.strip().lower()}|{max_results}|{search_depth}"

    if use_cache and cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key]

    try:
        response = get_tavily().search(
            query=query.strip(),
            max_results=max_results,
            search_depth=search_depth,
        )
    except Exception as exc:
        print(f"    [search] failed for {query!r}: {exc}")
        return []

    results: list[dict] = []

    for result in response.get("results", []) or []:
        url = (result.get("url") or "").strip()
        title = (result.get("title") or "").strip()
        content = trim_web_content(
            result.get("content") or "",
            limit=MAX_CONTENT_PER_RESULT,
        )

        if not url:
            continue

        results.append(
            {
                "url": url,
                "title": title,
                "content": content,
                "score": result.get("score"),
            }
        )

    if use_cache:
        _SEARCH_CACHE[cache_key] = results

    return results


def format_results(results: list[dict], max_chars: int = 9000) -> str:
    """Format search results into a compact, source-attributed block for the LLM.

    Every entry keeps its URL so the model can cite a source, and the total
    length is capped to control token usage.
    """
    blocks: list[str] = []
    total = 0

    for result in results:
        block = (
            f"SOURCE URL: {result.get('url', '')}\n"
            f"TITLE: {result.get('title', '')}\n"
            f"CONTENT:\n{result.get('content', '')}\n"
            "---"
        )

        if total + len(block) > max_chars:
            break

        blocks.append(block)
        total += len(block)

    return "\n".join(blocks)


def source_urls(results: list[dict]) -> list[str]:
    """Extract deduped source URLs from search results."""
    seen: set[str] = set()
    urls: list[str] = []

    for result in results:
        url = (result.get("url") or "").strip().rstrip("/")

        if not url or url in seen:
            continue

        seen.add(url)
        urls.append(url)

    return urls


def clear_cache() -> None:
    """Clear the in-process search cache (used between test runs)."""
    _SEARCH_CACHE.clear()
