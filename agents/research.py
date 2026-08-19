from tavily import TavilyClient
from dotenv import load_dotenv

import os

from services.llm import get_llm
from state.research_state import ResearchState

load_dotenv()

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

llm = get_llm("research")

BASIC_FIELDS = {"company_name", "website", "linkedin", "description"}
CONTACT_FIELDS = {
    "hr_email",
    "founder_email",
    "careers_email",
    "apply_email",
    "apply_link",
    "careers_page",
    "internship_available",
}
FOUNDER_FIELDS = {"founder"}


def _format_search_results(response: dict) -> str:
    combined_content = ""

    for result in response.get("results", []):
        combined_content += f"""
TITLE: {result.get('title')}

URL: {result.get('url')}

CONTENT:
{result.get('content')}

----------------------------------
"""

    return combined_content


def _tavily_search(query: str, max_results: int = 5) -> str:
    try:
        response = tavily.search(
            query=query,
            max_results=max_results
        )
    except Exception:
        return ""

    return _format_search_results(response)


def research_entity(entity_name: str, fields: list[str]) -> str:
    print("\n===== RESEARCH AGENT =====")
    print("Researching:", entity_name)
    print("Requested fields:", ", ".join(fields) if fields else "(none)")

    requested = set(fields)
    combined_content = ""

    needs_basic = bool(requested & (BASIC_FIELDS | FOUNDER_FIELDS)) or not fields
    needs_contact = bool(requested & CONTACT_FIELDS)

    if needs_basic:
        query_parts = [entity_name]

        if not fields or "website" in requested:
            query_parts.append("official website")
        if "linkedin" in requested:
            query_parts.append("linkedin")
        if "description" in requested:
            query_parts.append("company overview")
        if "founder" in requested:
            query_parts.append("founder CEO")

        combined_content += _tavily_search(" ".join(query_parts), max_results=5)

    if needs_contact:
        combined_content += _tavily_search(
            f"{entity_name} careers jobs internship contact",
            max_results=10,
        )

    print("Search completed.")
    return combined_content


def research_agent(state: ResearchState):
    print("\n===== RESEARCH AGENT =====")

    company = state["company_name"]

    print("Researching:", company)

    response = tavily.search(
        query=f"{company} official website linkedin company overview",
        max_results=5
    )

    combined_content = ""

    for result in response["results"]:
        combined_content += f"""
TITLE: {result.get('title')}

URL: {result.get('url')}

CONTENT:
{result.get('content')}

----------------------------------
"""

    print("Search completed.")
    print("Sending information to LLM...\n")

    prompt = f"""
You are a company research agent.

Find:

1. Official Website
2. LinkedIn URL
3. Short Description

Return exactly in this format:

Website: ...

LinkedIn: ...

Description: ...

TEXT:

{combined_content}
"""

    result = llm.invoke(prompt)

    for line in result.content.splitlines():
        if line.startswith("Website:"):
            state["website"] = line.replace("Website:", "", 1).strip()
        elif line.startswith("LinkedIn:"):
            state["linkedin"] = line.replace("LinkedIn:", "", 1).strip()
        elif line.startswith("Description:"):
            state["description"] = line.replace("Description:", "", 1).strip()

    return state
