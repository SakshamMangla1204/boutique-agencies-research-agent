import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from tavily import TavilyClient

load_dotenv()

MAX_QUERY_COUNT = 10
MAX_RESULTS_PER_QUERY = 10
MAX_COMPANY_COUNT = 100
QUERY_MEMORY_FILE = Path("state/discovery_queries.json")

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

llm = ChatOllama(
    model="qwen3:8b",
    temperature=0
)


def _extract_json_array(content: str, limit: int) -> list[str]:
    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    start = content.find("[")
    end = content.rfind("]")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Model response did not contain a JSON array.")

    items = json.loads(content[start:end + 1])

    if not isinstance(items, list):
        raise ValueError("Model response was not a list.")

    unique_items = []
    seen = set()

    for item in items:
        if not isinstance(item, str):
            continue

        value = item.strip()
        key = value.lower()

        if not value or key in seen:
            continue

        seen.add(key)
        unique_items.append(value)

        if len(unique_items) == limit:
            break

    return unique_items


def _load_used_queries() -> list[str]:
    if not QUERY_MEMORY_FILE.exists():
        return []

    try:
        data = json.loads(QUERY_MEMORY_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(data, list):
        return []

    return [query for query in data if isinstance(query, str) and query.strip()]


def _save_used_queries(queries: list[str]) -> None:
    QUERY_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUERY_MEMORY_FILE.write_text(json.dumps(queries, indent=2))


def _fallback_queries(base_query: str) -> list[str]:
    return [
        base_query,
        f"top {base_query}",
        f"generative {base_query}",
        f"seed funded {base_query}",
        f"{base_query} hiring interns",
        f"fast growing {base_query}",
        f"{base_query} funding 2025",
        f"y combinator {base_query}",
        f"machine learning startups related to {base_query}",
        f"{base_query} nasscom"
    ]


def _generate_search_queries(base_query: str, used_queries: list[str]) -> list[str]:
    prompt = f"""
You are a search query generation agent.

Generate 10 diverse web search queries that can uncover different companies related to the base topic.

Return ONLY valid JSON in this format:
[
  "query 1",
  "query 2",
  "query 3"
]

Rules:
- Queries must be diverse and low-overlap.
- Queries must be focused on finding companies, startups, hiring companies, funding lists, accelerators, and industry roundups.
- Do not repeat any previously used query.
- Keep every query short and practical for a web search engine.

BASE QUERY:
{base_query}

PREVIOUSLY USED QUERIES:
{json.dumps(used_queries)}
"""

    result = llm.invoke(prompt)
    generated_queries = _extract_json_array(result.content, MAX_QUERY_COUNT)

    used_keys = {query.strip().lower() for query in used_queries}
    fresh_queries = []

    for query in generated_queries:
        key = query.lower()

        if key in used_keys:
            continue

        used_keys.add(key)
        fresh_queries.append(query)

    return fresh_queries[:MAX_QUERY_COUNT]


def _search_query(query: str) -> str:
    response = tavily.search(
        query=query,
        max_results=MAX_RESULTS_PER_QUERY
    )

    combined_content = f"\nSEARCH QUERY: {query}\n"

    for result in response["results"]:
        combined_content += f"""
TITLE: {result.get('title')}

URL: {result.get('url')}

CONTENT:
{result.get('content')}

----------------------------------
"""

    return combined_content


def _extract_companies(base_query: str, combined_content: str) -> list[str]:
    prompt = f"""
You are a company extraction agent.

Extract only real company or startup names related to the base query.

Return ONLY valid JSON.

Format:
[
  "Company 1",
  "Company 2",
  "Company 3"
]

Rules:
- Only company names.
- Remove duplicates.
- No explanations.
- No markdown.
- No numbering.
- Exclude media companies, generic websites, and investors unless they are actual operating companies relevant to the base query.
- Return as many relevant unique companies as possible, up to {MAX_COMPANY_COUNT}.

BASE QUERY:
{base_query}

TEXT:
{combined_content}
"""

    result = llm.invoke(prompt)
    return _extract_json_array(result.content, MAX_COMPANY_COUNT)


def discover_companies(query: str) -> list[str]:
    print("\n===== DISCOVERY =====")
    print("Query:", query)

    used_queries = _load_used_queries()

    try:
        search_queries = _generate_search_queries(query, used_queries)
    except Exception:
        search_queries = []

    if not search_queries:
        search_queries = [
            item for item in _fallback_queries(query)
            if item.lower() not in {used.lower() for used in used_queries}
        ][:MAX_QUERY_COUNT]

    if not search_queries:
        search_queries = [query]

    print("\nDISCOVERY SEARCH QUERIES:")
    for search_query in search_queries:
        print("-", search_query)

    combined_content = ""

    for search_query in search_queries:
        try:
            combined_content += _search_query(search_query)
        except Exception:
            continue

    if not combined_content.strip():
        print("\nNo Tavily results collected.")
        return []

    companies = _extract_companies(query, combined_content)
    _save_used_queries(used_queries + search_queries)

    print(f"\nTOTAL SEARCH QUERIES USED: {len(search_queries)}")
    print("Discovered companies:", companies)

    return companies
