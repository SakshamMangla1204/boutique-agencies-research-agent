import os

from dotenv import load_dotenv
from langchain_ollama import ChatOllama

load_dotenv()

llm = ChatOllama(
    model="qwen3:8b",
    temperature=0
)

response = llm.invoke("Say hello")

print(response.content)
