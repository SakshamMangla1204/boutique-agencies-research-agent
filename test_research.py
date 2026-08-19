from tavily import TavilyClient
from dotenv import load_dotenv

import os

from services.llm import get_llm

# Load environment variables
load_dotenv()

# Tavily
tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

# Research model (Groq)
llm = get_llm("research")

# Test Company
company_name = "Krutrim"

print(f"\nResearching {company_name}...\n")

# Search the company
response = tavily.search(
    query=f"{company_name} official website linkedin company overview",
    max_results=5
)

# Collect search content
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

print("\nRESEARCH RESULT\n")
print("=" * 60)
print(result.content)
print("=" * 60)
