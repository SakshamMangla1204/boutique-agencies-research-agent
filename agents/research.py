from tavily import TavilyClient
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

import os

from state.research_state import ResearchState

load_dotenv()

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

llm = ChatOllama(
    model="qwen3:8b",
    temperature=0
)


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
    print("Sending information to Ollama...\n")

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
