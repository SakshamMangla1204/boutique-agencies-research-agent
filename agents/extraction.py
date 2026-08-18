import json
import os
import re

from dotenv import load_dotenv
from langchain_ollama import ChatOllama

load_dotenv()

llm = ChatOllama(
    model="qwen3:8b",
    temperature=0
)

MAX_EXTRACTION_CONTENT = 12000


def _strip_model_preamble(content: str) -> str:
    think_tag = "think"
    open_tag = "<" + think_tag + ">"
    close_tag = "</" + think_tag + ">"
    pattern = "(?si)" + re.escape(open_tag) + ".*?" + re.escape(close_tag)
    content = re.sub(pattern, "", content)
    return content.strip()


def _parse_extraction_json(content: str, fields: list[str]) -> dict:
    text = _strip_model_preamble(content)

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
        raise ValueError("Model response did not contain JSON.")

    data = json.loads(text[start:end + 1])

    if not isinstance(data, dict):
        raise ValueError("Model response was not a JSON object.")

    return {field: str(data.get(field, "") or "").strip() for field in fields}


def extract_fields(entity_name: str, source_content: str, fields: list[str]) -> dict:
    print("\n===== EXTRACTION AGENT =====")
    print(f"Entity: {entity_name}")
    print(f"Fields: {', '.join(fields)}")

    if not fields:
        return {}

    field_lines = "\n".join(f'- "{field}"' for field in fields)
    example = ",\n  ".join(f'"{field}": ""' for field in fields)

    prompt = f"""
You are a data extraction agent.

Extract ONLY the requested fields for this entity from the source text.

Entity name: {entity_name}

Requested fields:
{field_lines}

Return JSON only in exactly this format:
{{
  {example}
}}

Rules:
- Return exactly the requested fields and nothing else.
- Never invent information.
- Never fabricate emails, URLs, or names.
- Use only information found in the source text.
- If a field is not found, return an empty string.
- Do not use markdown.

SOURCE TEXT:
{source_content[:MAX_EXTRACTION_CONTENT]}
"""

    try:
        result = llm.invoke(prompt)
        extracted = _parse_extraction_json(result.content, fields)
    except Exception:
        extracted = {field: "" for field in fields}

    for field in fields:
        extracted.setdefault(field, "")

    if "company_name" in extracted and not extracted["company_name"]:
        extracted["company_name"] = entity_name

    print("Extraction complete.")
    return extracted
