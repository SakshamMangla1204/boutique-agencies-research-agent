from tavily import TavilyClient
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
import json

import os 

load_dotenv()

tavily = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

# Ollama Model
llm = ChatOllama(
    model="qwen3:8b",
    temperature=0
)

query="Ai Startups in India "

print("Searching Tavily..")

response = tavily.search(
    query=query,
    max_results=5
)

combined_content= ""

for result in response["results"]:
    combined_content += result.get("content", "")
    combined_content += "\n\n"

print("the content is collected form tavilly is ")
print("sending to ollama ... ")

prompt = f"""
You are a company extraction agent.

Extract startup/company names from the text.

Return ONLY valid JSON.

Format:

[
  "Company 1",
  "Company 2",
  "Company 3"
]

Rules:
- Only startups/companies.
- Remove duplicates.
- No explanations.
- No markdown.
- No numbering.

TEXT:

{combined_content}
"""

result = llm.invoke(prompt)

companies = json.loads(result.content)

print(companies)
print(type(companies))
