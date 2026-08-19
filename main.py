from typing import Optional

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
    "query": "AI startups India",
    "entity_type": "company",
    "fields": [
        "company_name",
        "website",
        "linkedin",
        "description",
    ],
    "max_results": 3,
}

# Safeguards for the controlled discovery loop.
MAX_DISCOVERY_BATCHES = 5
MAX_EMPTY_BATCHES = 2
DISCOVERY_BATCH_SIZE = 10

# Execution stop reasons.
STOP_TARGET_REACHED = "TARGET_REACHED"
STOP_MAX_BATCHES_REACHED = "MAX_BATCHES_REACHED"
STOP_MAX_EMPTY_BATCHES_REACHED = "MAX_EMPTY_BATCHES_REACHED"
STOP_DISCOVERY_FAILED = "DISCOVERY_FAILED"
STOP_STARTUP_FAILED = "STARTUP_FAILED"

DEFAULT_NAME_FIELD = "company_name"


def _validate_config(config: ResearchConfig) -> Optional[str]:
    """Validate ResearchConfig. Returns an error message, or None if valid."""
    query = config.get("query")
    entity_type = config.get("entity_type")
    fields = config.get("fields")
    max_results = config.get("max_results")

    if not query or not str(query).strip():
        return "Config error: 'query' must be a non-empty string."

    if not entity_type or not str(entity_type).strip():
        return "Config error: 'entity_type' must be a non-empty string."

    if not isinstance(fields, list) or not fields:
        return "Config error: 'fields' must be a non-empty list."

    if not all(isinstance(field, str) and field.strip() for field in fields):
        return "Config error: 'fields' must contain only non-empty strings."

    if not isinstance(max_results, int) or max_results <= 0:
        return "Config error: 'max_results' must be a positive integer."

    return None


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


def _print_summary(
    stop_reason: str,
    max_results: int,
    total_discovered: int,
    duplicates_skipped_level1: int,
    duplicates_skipped_level2: int,
    entities_processed: int,
    collected: int,
    failed_entities: list[tuple[str, str]],
    batches_used: int,
    discovered_entities: list[str],
):
    print(f"\n{'=' * 60}")
    print("PIPELINE COMPLETE")
    print(f"{'=' * 60}")
    print(f"Stop reason: {stop_reason}")

    if stop_reason == STOP_TARGET_REACHED:
        print(f"  Target of {max_results} new entities was reached.")
    elif stop_reason == STOP_MAX_BATCHES_REACHED:
        print(f"  Maximum discovery batches ({MAX_DISCOVERY_BATCHES}) exhausted before reaching the target.")
    elif stop_reason == STOP_MAX_EMPTY_BATCHES_REACHED:
        print(f"  {MAX_EMPTY_BATCHES} consecutive discovery batches returned no new entities.")
    elif stop_reason == STOP_DISCOVERY_FAILED:
        print("  A discovery batch failed before the target was reached.")

    print(f"\nEntities discovered: {total_discovered}")
    print(f"Duplicates skipped (Level-1, in-memory): {duplicates_skipped_level1}")
    print(f"Duplicates skipped (Level-2, sheet writer): {duplicates_skipped_level2}")
    print(f"Entities processed (research + extraction): {entities_processed}")
    print(f"Successful rows written: {collected}")
    print(f"Failed entities: {len(failed_entities)}")
    print(f"Discovery batches used: {batches_used}")

    if discovered_entities:
        print(f"\nDiscovered entities ({len(discovered_entities)}):")
        for entity in discovered_entities:
            print(f"  - {entity}")

    if failed_entities:
        print(f"\nFailed entities:")
        for entity, reason in failed_entities:
            print(f"  - {entity}: {reason}")


def run_research_pipeline(config: ResearchConfig, progress_callback=None):
    """Run the research pipeline.

    `progress_callback` is an optional callable(stage: str, data: dict) used by
    external callers (e.g. the API layer) to observe pipeline progress. When
    omitted, behavior is identical to the original implementation.
    """

    def _emit(stage: str, data: Optional[dict] = None):
        if progress_callback is not None:
            try:
                progress_callback(stage, data or {})
            except Exception:
                pass

    config_error = _validate_config(config)

    if config_error:
        _emit("startup_failed", {"error": config_error})
        print(f"\n{config_error}")
        print(f"STOP REASON: {STOP_STARTUP_FAILED}")
        return

    query = config["query"]
    entity_type = config["entity_type"]
    fields = config["fields"]
    max_results = config["max_results"]
    name_field = DEFAULT_NAME_FIELD if DEFAULT_NAME_FIELD in fields else fields[0]

    print("\n===== RESEARCH PIPELINE =====")
    print(f"Query: {query}")
    print(f"Entity type: {entity_type}")
    print(f"Fields: {', '.join(fields)}")
    print(f"Target NEW entities: {max_results}")

    # Read persistent memory (Google Sheets) before discovery. A failure here
    # is a startup failure, not an entity-level failure.
    try:
        ensure_research_headers(fields)
        known_names = get_existing_entity_names(name_field)
    except Exception as exc:
        print(f"\nStartup failed: could not access Google Sheets memory: {exc}")
        print(f"STOP REASON: {STOP_STARTUP_FAILED}")
        return

    print(f"Entities already in sheet: {len(known_names)}")
    _emit("startup", {"known_entities": len(known_names)})

    collected = 0
    total_discovered = 0
    duplicates_skipped_level1 = 0
    duplicates_skipped_level2 = 0
    entities_processed = 0
    failed_entities: list[tuple[str, str]] = []
    discovered_entities: list[str] = []
    batches_used = 0
    stop_reason = STOP_MAX_BATCHES_REACHED

    empty_batches = 0
    used_queries = None

    for batch_number in range(1, MAX_DISCOVERY_BATCHES + 1):
        if collected >= max_results:
            stop_reason = STOP_TARGET_REACHED
            break

        remaining = max_results - collected
        batch_size = min(DISCOVERY_BATCH_SIZE, remaining)

        print(f"\n{'=' * 60}")
        print(f"DISCOVERY BATCH {batch_number}")
        print(f"{'=' * 60}")

        batches_used = batch_number
        _emit("discovery_start", {"batch": batch_number})

        try:
            batch_entities, used_queries = discover_entity_batch(
                query,
                entity_type,
                batch_size=batch_size,
                batch_number=batch_number,
                used_queries=used_queries,
            )
        except Exception as exc:
            print(f"\nDiscovery batch {batch_number} failed: {exc}")
            stop_reason = STOP_DISCOVERY_FAILED
            _emit("pipeline_failed", {"error": str(exc), "stop_reason": stop_reason})
            break

        total_discovered += len(batch_entities)
        discovered_entities.extend(batch_entities)
        print(f"Found: {len(batch_entities)}")
        _emit("discovery", {"batch": batch_number, "found": len(batch_entities)})

        new_entities = _filter_new_entities(batch_entities, known_names)
        existing_count = len(batch_entities) - len(new_entities)
        duplicates_skipped_level1 += existing_count

        print(f"New: {len(new_entities)}")
        print(f"Existing (skip): {existing_count}")
        _emit("discovery_filter", {"new": len(new_entities), "existing": existing_count})

        # A batch containing only already-known entities is NOT a discovery
        # failure. Count it as an empty batch and allow another discovery
        # attempt until MAX_EMPTY_BATCHES is reached.
        if not new_entities:
            empty_batches += 1
            print(f"No new entities in this batch. Empty batches: {empty_batches}")

            if empty_batches >= MAX_EMPTY_BATCHES:
                print(f"\nNO NEW ENTITIES FOUND AFTER {MAX_EMPTY_BATCHES} CONSECUTIVE EMPTY BATCHES")
                stop_reason = STOP_MAX_EMPTY_BATCHES_REACHED
                break

            continue

        empty_batches = 0

        for entity in new_entities:
            if collected >= max_results:
                break

            print(f"\nPROCESSING {collected + 1}/{max_results}: {entity}")
            _emit("entity_start", {"entity": entity, "index": collected + 1, "total": max_results})

            try:
                source_content = research_entity(entity, fields)
            except Exception as exc:
                failed_entities.append((entity, f"research: {exc}"))
                _emit("entity_failed", {"entity": entity, "reason": f"research: {exc}"})
                print(f"Research failed for {entity}: {exc}")
                continue

            try:
                extracted = extract_fields(entity, source_content, fields)
            except Exception as exc:
                failed_entities.append((entity, f"extraction: {exc}"))
                _emit("entity_failed", {"entity": entity, "reason": f"extraction: {exc}"})
                print(f"Extraction failed for {entity}: {exc}")
                continue

            entities_processed += 1
            _emit("entity_processed", {"entity": entity})

            if name_field not in extracted or not extracted.get(name_field):
                extracted[name_field] = entity

            try:
                if write_research_row(fields, extracted, name_field=name_field):
                    collected += 1
                    known_names.add(normalize_entity_name(entity))
                    _emit("entity_written", {"entity": entity})
                    print(f"Wrote row for: {entity}")
                else:
                    # Level-2 duplicate protection in the sheet writer found
                    # this entity already present. Remember it so later
                    # discovery batches do not re-process it.
                    duplicates_skipped_level2 += 1
                    known_names.add(normalize_entity_name(entity))
                    _emit("entity_duplicate", {"entity": entity})
                    print(f"Skipped duplicate: {entity}")
            except Exception as exc:
                failed_entities.append((entity, f"sheet write: {exc}"))
                _emit("entity_failed", {"entity": entity, "reason": f"sheet write: {exc}"})
                print(f"Sheet write failed for {entity}: {exc}")
                continue

        if collected >= max_results:
            stop_reason = STOP_TARGET_REACHED
            break

    _emit("complete", {
        "stop_reason": stop_reason,
        "total_discovered": total_discovered,
        "duplicates_skipped_level1": duplicates_skipped_level1,
        "duplicates_skipped_level2": duplicates_skipped_level2,
        "entities_processed": entities_processed,
        "written": collected,
        "failed": len(failed_entities),
        "batches_used": batches_used,
        "discovered_entities": discovered_entities,
        "failed_entities": failed_entities,
    })

    _print_summary(
        stop_reason=stop_reason,
        max_results=max_results,
        total_discovered=total_discovered,
        duplicates_skipped_level1=duplicates_skipped_level1,
        duplicates_skipped_level2=duplicates_skipped_level2,
        entities_processed=entities_processed,
        collected=collected,
        failed_entities=failed_entities,
        batches_used=batches_used,
        discovered_entities=discovered_entities,
    )


if __name__ == "__main__":
    run_research_pipeline(RESEARCH_CONFIG)