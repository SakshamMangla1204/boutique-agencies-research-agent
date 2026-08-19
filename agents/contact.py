import json
import os

from dotenv import load_dotenv
from tavily import TavilyClient

from services.llm import get_llm
from state.research_state import ResearchState

load_dotenv()

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

llm = get_llm("contact")


def _parse_contact_json(content: str) -> dict:
    text = content.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Gemini response did not contain JSON.")

    data = json.loads(text[start:end + 1])

    if not isinstance(data, dict):
        raise ValueError("Gemini response was not a JSON object.")

    return {
        "apply_link": data.get("apply_link", "") or "",
        "careers_email": data.get("careers_email", "") or "",
        "hr_email": data.get("hr_email", "") or "",
    }


def contact_agent(state: ResearchState):
    print("\n===== CONTACT AGENT =====")

    company_name = state["company_name"]
    print(f"Company: {company_name}")
    print("Searching contacts...")

    try:
        response = tavily.search(
            query=f"{company_name} careers jobs internship contact",
            max_results=10
        )
    except Exception:
        return state

    combined_content = ""

    for result in response.get("results", []):
        combined_content += f"""
TITLE: {result.get('title')}

URL: {result.get('url')}

CONTENT:
{result.get('content')}

----------------------------------
"""

    prompt = f"""
You are a contact extraction agent.

Extract the following fields from the search results:
1. apply_link
2. careers_email
3. hr_email

Return JSON only in exactly this format:
{{
  "apply_link": "",
  "careers_email": "",
  "hr_email": ""
}}

Rules:
- Never invent emails.
- Never invent URLs.
- If not found, return an empty string.
- Use only information found in the Tavily results.
- Prefer application links in this order:
  1. Official careers page
  2. Official jobs page
  3. Greenhouse
  4. Lever
  5. Wellfound
  6. LinkedIn Jobs
- Do not use the company homepage unless no better application link exists.

TEXT:
{combined_content}
"""

    try:
        result = llm.invoke(prompt)
    except Exception:
        return state

    try:
        contact_data = _parse_contact_json(result.content)
    except Exception:
        return state

    state["apply_link"] = contact_data["apply_link"]
    state["careers_email"] = contact_data["careers_email"]
    state["hr_email"] = contact_data["hr_email"]

    if state["apply_link"]:
        state["status"] = "CONTACT_FOUND"
    else:
        state["status"] = "RESEARCHED"

    print("Contact extraction complete")

    return state
