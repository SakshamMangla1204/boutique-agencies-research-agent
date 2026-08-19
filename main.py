from agents.discovery import discover_entity_batch
from agents.extraction import extract_fields
from agents.research import research_entity
from services.sheets_writer import (
    ensure_research_headers,
    get_existing_entity_names,
    normalize_entity_name,
    write_research_row,
)
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
    "max_results": 5,
}

# Safeguards for the controlled discovery loop.
MAX_DISCOVERY_BATCHES = 5
MAX_EMPTY_BATCHES = 2
DISCOVERY_BATCH_SIZE = 10


def _filter_new_entities(
    entities: list[str],
    known_names: set[str],
) -> list[str]:
    """Return entities not already known in the sheet (Level-1 filter)."""
    new_entities = []
    seen_in_batch = set()

    for entity in entities:
        name = entity.strip()

        if not name:
            continue

        key = normalize_entity_name(name)

        if not key or key in known_names or key in seen_in_batch:
            continue

        seen_in_batch.add(key)
        new_entities.append(name)

    return new_entities


def run_research_pipeline(config: ResearchConfig):
    query = config["query"]
    entity_type = config["entity_type"]
    fields = config["fields"]
    max_results = config["max_results"]
    name_field = "company_name" if "company_name" in fields else fields[0]

    print("\n===== RESEARCH PIPELINE =====")
    print(f"Query: {query}")
    print(f"Entity type: {entity_type}")
    print(f"Fields: {', '.join(fields)}")
    print(f"Target NEW entities: {max_results}")

    ensure_research_headers(fields)

    known_names = get_existing_entity_names(name_field)
    print(f"Entities already in sheet: {len(known_names)}")

    collected = 0
    empty_batches = 0
    used_queries = None

    for batch_number in range(1, MAX_DISCOVERY_BATCHES + 1):
        if collected >= max_results:
            break

        remaining = max_results - collected
        batch_size = min(DISCOVERY_BATCH_SIZE, remaining)

        print(f"\n{'=' * 60}")
        print(f"DISCOVERY BATCH {batch_number}")
        print(f"{'=' * 60}")

        batch_entities, used_queries = discover_entity_batch(
            query,
            entity_type,
            batch_size=batch_size,
            batch_number=batch_number,
            used_queries=used_queries,
        )

        print(f"Found: {len(batch_entities)}")

        new_entities = _filter_new_entities(batch_entities, known_names)
        existing_count = len(batch_entities) - len(new_entities)

        print(f"New: {len(new_entities)}")
        print(f"Existing: {existing_count}")

        if not new_entities:
            empty_batches += 1
            print(f"No new entities in this batch. Empty batches: {empty_batches}")

            if empty_batches >= MAX_EMPTY_BATCHES:
                print("\nNO NEW ENTITIES FOUND AFTER MAXIMUM DISCOVERY ATTEMPTS")
                break

            continue

        empty_batches = 0

        for index, entity in enumerate(new_entities, start=1):
            if collected >= max_results:
                break

            print(f"\nPROCESSING {collected + 1}/{max_results}: {entity}")

            try:
                source_content = research_entity(entity, fields)
            except Exception as exc:
                print(f"Research failed for {entity}: {exc}")
                continue

            try:
                extracted = extract_fields(entity, source_content, fields)
            except Exception as exc:
                print(f"Extraction failed for {entity}: {exc}")
                continue

            if name_field not in extracted or not extracted.get(name_field):
                extracted[name_field] = entity

            try:
                if write_research_row(fields, extracted, name_field=name_field):
                    collected += 1
                    known_names.add(normalize_entity_name(entity))
                    print(f"Wrote row for: {entity}")
                else:
                    print(f"Skipped duplicate: {entity}")
            except Exception as exc:
                print(f"Sheet write failed for {entity}: {exc}")
                continue

        if collected >= max_results:
            print(f"\nTARGET REACHED: {max_results} NEW ENTITIES")
            break

    print(f"\n===== PIPELINE COMPLETE =====")
    print(f"New rows added to sheet: {collected}")
    print(f"Target: {max_results}")


if __name__ == "__main__":
    run_research_pipeline(RESEARCH_CONFIG)