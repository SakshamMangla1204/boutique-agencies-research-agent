from agents.discovery import discover_entities
from agents.extraction import extract_fields
from agents.research import research_entity
from services.sheets_writer import ensure_research_headers, write_research_row
from state.research_config import ResearchConfig

# Legacy company-research pipeline (discover -> enqueue -> worker):
#   from agents.discovery import discover_companies
#   from services.sheets_writer import enqueue_companies
#   from worker import run_worker

RESEARCH_CONFIG: ResearchConfig = {
    "query": "AI startups in India",
    "entity_type": "company",
    "fields": [
        "company_name",
        "website",
        "linkedin",
        "description",
    ],
    "max_results": 3,
}


def run_research_pipeline(config: ResearchConfig):
    query = config["query"]
    entity_type = config["entity_type"]
    fields = config["fields"]
    max_results = config["max_results"]
    name_field = "company_name" if "company_name" in fields else fields[0]

    entities = discover_entities(query, entity_type, max_results)

    print(f"\nTOTAL ENTITIES FOUND: {len(entities)}")
    print(entities)

    ensure_research_headers(fields)

    written_count = 0

    for entity in entities:
        print(f"\n{'=' * 60}")
        print(f"PROCESSING: {entity}")
        print(f"{'=' * 60}")

        source_content = research_entity(entity, fields)

        extracted = extract_fields(entity, source_content, fields)

        if name_field not in extracted or not extracted.get(name_field):
            extracted[name_field] = entity

        if write_research_row(fields, extracted, name_field=name_field):
            written_count += 1
            print(f"Wrote row for: {entity}")
        else:
            print(f"Skipped duplicate: {entity}")

    print(f"\nNEW ROWS ADDED TO SHEET: {written_count}")


if __name__ == "__main__":
    run_research_pipeline(RESEARCH_CONFIG)
