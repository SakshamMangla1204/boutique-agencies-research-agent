from typing import TypedDict


class ResearchConfig(TypedDict):
    query: str
    entity_type: str
    fields: list[str]
    max_results: int
