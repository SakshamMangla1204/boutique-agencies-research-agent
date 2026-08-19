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

# Contact model (Groq)
llm = get_llm("contact")

# Test Company
company_name = "Krutrim"

print(f"\nSearching contact information for {company_name}...\n")

# Search
response = tavily.search(
    query=f"{company_name} careers jobs contact email hr email apply internship",
    max_results=10
)

# Combine search results
combined_content = ""

for result in response["results"]:
    combined_content += f"""
TITLE: {result.get('title')}

URL: {result.get('url')}

CONTENT:
{result.get('content')}

----------------------------------------
"""

print("Search completed.")
print("Sending to LLM...\n")

prompt = f"""
You are a recruitment research agent.

Find the following information if available:

1. HR Email
2. Founder Email
3. Careers Email
4. Apply Email
5. Apply Link
6. LinkedIn Page

If something is not found, write:

NOT FOUND

Return exactly in this format:

HR Email:
Founder Email:
Careers Email:
Apply Email:
Apply Link:
LinkedIn:

TEXT:

{combined_content}
"""

result = llm.invoke(prompt)

print("\nCONTACT RESULT\n")
print("=" * 60)
print(result.content)
print("=" * 60)
