import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from tavily import TavilyClient

load_dotenv()

MAX_QUERY_COUNT = 10
MAX_RESULTS_PER_QUERY = 10
MAX_COMPANY_COUNT = 100
MAX_EXTRACTION_CONTENT = 12000
QUERY_MEMORY_FILE = Path("state/discovery_queries.json")

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

llm = ChatOllama(
    model="qwen3:8b",
    temperature=0
)


def _truncate_content(content: str, limit: int = MAX_EXTRACTION_CONTENT) -> str:
    content = content.strip()

    if len(content) <= limit:
        return content

    return content[:limit]


def _strip_model_preamble(content: str) -> str:
    think_tag = "think"
    open_tag = "<" + think_tag + ">"
    close_tag = "</" + think_tag + ">"
    pattern = "(?si)" + re.escape(open_tag) + ".*?" + re.escape(close_tag)
    content = re.sub(pattern, "", content)
    return content.strip()


def _extract_json_array(content: str, limit: int) -> list[str]:
    content = _strip_model_preamble(content)

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


MAX_DISCOVERY_BATCHES = 5


def _extract_entities(
    base_query: str,
    entity_type: str,
    combined_content: str,
    limit: int,
) -> list[str]:
    prompt = f"""
You are an entity extraction agent.

Extract only real {entity_type} names related to the base query.

Return ONLY valid JSON.

Format:
[
  "Entity 1",
  "Entity 2",
  "Entity 3"
]

Rules:
- Only {entity_type} names.
- Remove duplicates.
- No explanations.
- No markdown.
- No numbering.
- Exclude media outlets, generic websites, and investors unless they are actual operating {entity_type}s relevant to the base query.
- Return as many relevant unique {entity_type}s as possible, up to {limit}.

BASE QUERY:
{base_query}

TEXT:
{combined_content}
"""

    result = llm.invoke(prompt)
    return _extract_json_array(result.content, limit)


def _extract_companies(base_query: str, combined_content: str) -> list[str]:
    return _extract_entities(
        base_query,
        "company",
        combined_content,
        MAX_COMPANY_COUNT,
    )


def _collect_search_queries(query: str, used_queries: list[str]) -> list[str]:
    try:
        search_queries = _generate_search_queries(query, used_queries)
    except Exception:
        search_queries = []

    if not search_queries:
        used_keys = {used.lower() for used in used_queries}
        search_queries = [
            item for item in _fallback_queries(query)
            if item.lower() not in used_keys
        ][:MAX_QUERY_COUNT]

    if not search_queries:
        if query.lower() not in {used.lower() for used in used_queries}:
            search_queries = [query]

    return search_queries


def _run_discovery_batch(
    query: str,
    entity_type: str,
    used_queries: list[str],
    remaining: int,
) -> tuple[list[str], list[str]]:
    search_queries = _collect_search_queries(query, used_queries)

    if not search_queries:
        return [], used_queries

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
        print("\nNo Tavily results collected in this batch.")
        return [], used_queries + search_queries

    try:
        entities = _extract_entities(
            query,
            entity_type,
            _truncate_content(combined_content),
            remaining,
        )
    except Exception as exc:
        print(f"\nEntity extraction failed in this batch: {exc}")
        entities = []

    return entities, used_queries + search_queries


def discover_entities(
    query: str,
    entity_type: str = "company",
    max_results: int = 20,
) -> list[str]:
    print("\n===== DISCOVERY =====")
    print("Query:", query)
    print("Entity type:", entity_type)
    print("Max results:", max_results)

    used_queries = _load_used_queries()
    discovered: list[str] = []
    seen: set[str] = set()

    for batch_number in range(1, MAX_DISCOVERY_BATCHES + 1):
        remaining = max_results - len(discovered)

        if remaining <= 0:
            break

        print(f"\nDISCOVERY BATCH {batch_number}")

        batch_entities, used_queries = _run_discovery_batch(
            query,
            entity_type,
            used_queries,
            remaining,
        )

        new_entities = 0

        for entity in batch_entities:
            key = entity.strip().lower()

            if not key or key in seen:
                continue

            seen.add(key)
            discovered.append(entity.strip())
            new_entities += 1

            if len(discovered) >= max_results:
                break

        _save_used_queries(used_queries)

        print(f"Batch entities found: {len(batch_entities)}")
        print(f"New unique entities this batch: {new_entities}")

        if len(discovered) >= max_results or new_entities == 0:
            break

    print(f"\nTOTAL SEARCH QUERIES USED: {len(used_queries)}")
    print("Discovered entities:", discovered)

    return discovered[:max_results]


def discover_companies(query: str) -> list[str]:
    return discover_entities(query, entity_type="company", max_results=MAX_COMPANY_COUNT)
