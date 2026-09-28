"""End-to-end runner for the AI agency / AI Engineer job research agent.

Usage:
    .venv/bin/python run_ai_agency_research.py                 # small NCR batch (default 8)
    .venv/bin/python run_ai_agency_research.py --max 5         # explicit smaller batch
    .venv/bin/python run_ai_agency_research.py --city Noida    # single city
    .venv/bin/python run_ai_agency_research.py --no-sheets     # PostgreSQL only
    .venv/bin/python run_ai_agency_research.py --no-db         # Sheets only
    .venv/bin/python run_ai_agency_research.py --no-llm        # heuristic relevance only

Design notes
------------
* Cities are processed in strict geographic-priority order (Gurugram -> Noida ->
  Delhi -> Greater Noida -> Faridabad -> Ghaziabad), which is discovery priority
  only and never mixed into the AI-demand score.
* The graph is invoked with a bounded `max_agencies` cap so a run stays small.
* PostgreSQL and Google Sheets are each optional; a missing or unreachable
  dependency degrades gracefully with an explicit warning rather than a crash.
"""
from __future__ import annotations

import argparse
import sys

from graph.ai_agency_graph import graph
from services.db import session as db_session
from services import search as search_service
from state import agency_config

# NCR-first discovery order (discovery priority only).
NCR_CITY_ORDER = [
    "Gurugram",
    "Noida",
    "Delhi",
    "Greater Noida",
    "Faridabad",
    "Ghaziabad",
]

EXPANSION_CITY_ORDER = [
    "Chandigarh",
    "Mohali",
    "Jaipur",
    "Bengaluru",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Chennai",
]


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the AI agency / AI Engineer job research agent.",
    )
    parser.add_argument("--max", type=int, default=8,
                        help="Maximum agencies to deep-research (default: 8).")
    parser.add_argument("--city", type=str, default="",
                        help="Research a single city instead of the NCR order.")
    parser.add_argument("--expansion", action="store_true",
                        help="Include Chandigarh/Mohali/Jaipur/tech hubs after NCR.")
    parser.add_argument("--no-db", action="store_true",
                        help="Skip PostgreSQL writes.")
    parser.add_argument("--no-sheets", action="store_true",
                        help="Skip Google Sheets writes.")
    parser.add_argument("--no-llm", action="store_true",
                        help="Use deterministic relevance classification only.")
    return parser.parse_args(argv)


def build_city_plan(args) -> list:
    """Return the ordered list of cities to work, highest priority first."""
    if args.city:
        return [args.city]

    if args.expansion:
        return NCR_CITY_ORDER + EXPANSION_CITY_ORDER

    return list(NCR_CITY_ORDER)


def build_initial_state(city: str, slots: int, args, db_enabled: bool,
                        sheets_enabled: bool) -> dict:
    """Fresh graph state for one city."""
    return {
        "run_id": f"run-{city.lower().replace(' ', '-')}",
        "current_city": city,
        "max_agencies": slots,
        "target_cities": [city],
        "include_expansion": args.expansion,
        "enable_db": db_enabled,
        "enable_sheets": sheets_enabled,
        "db_enabled": db_enabled,
        "sheets_enabled": sheets_enabled,
        "candidates": [],
        "agencies": [],
        "jobs": [],
        "sources": [],
        "errors": [],
        "duplicates_skipped": 0,
        "existing_in_db": 0,
        "filtered_out": 0,
        "discovered_count": 0,
        "processed_count": 0,
        "written_db_count": 0,
        "written_sheet_count": 0,
        "job_count": 0,
        "target_job_count": 0,
        "stop_reason": "",
    }


def run(args) -> int:
    print("=" * 78)
    print("AI ENGINEER RECRUITMENT / JOB RESEARCH AGENT")
    print("=" * 78)
    print("Roadmap reference : https://roadmap.sh/ai-engineer")
    print(f"Max agencies      : {args.max}")
    print(f"Cities            : {', '.join(build_city_plan(args))}")

    db_enabled = not args.no_db and db_session.is_db_enabled()
    db_state = (
        "enabled"
        if db_enabled
        else ("disabled (--no-db)" if args.no_db else db_session.db_status())
    )

    sheets_enabled = not args.no_sheets
    print(f"PostgreSQL        : {db_state}")

    if sheets_enabled:
        from services import sheets_agency_writer as sheets

        print(f"Google Sheets     : {sheets.sheets_status()}")

    print(
        "LLM relevance     : "
        + ("heuristic only (--no-llm)" if args.no_llm else "heuristic + LLM")
    )

    totals = {
        "discovered": 0,
        "duplicates": 0,
        "processed": 0,
        "jobs_written": 0,
        "target_jobs": 0,
        "sheet_rows": 0,
        "db_rows": 0,
    }

    remaining_slots = args.max

    for city in build_city_plan(args):
        if remaining_slots <= 0:
            print(f"\nBatch cap reached ({args.max}); stopping before {city}.")
            break

        print(f"\n{'#' * 78}")
        print(f"# CITY: {city}  (geographic priority "
              f"{agency_config.geographic_priority_score(city)})")
        print(f"{'#' * 78}")

        initial_state = build_initial_state(
            city,
            remaining_slots,
            args,
            db_enabled,
            sheets_enabled,
        )

        try:
            # Each agency consumes ~9 supersteps, so the default limit of 25 is
            # too low for even a 3-agency batch. Scale the limit to the batch.
            final_state = graph.invoke(
                initial_state,
                config={"recursion_limit": max(50, remaining_slots * 15)},
            )
        except Exception as exc:
            print(f"\nCity run failed for {city}: {type(exc).__name__}: {exc}")
            continue

        city_processed = final_state.get("processed_count", 0)
        remaining_slots -= city_processed

        totals["discovered"] += final_state.get("discovered_count", 0)
        totals["duplicates"] += final_state.get("duplicates_skipped", 0)
        totals["processed"] += city_processed
        totals["jobs_written"] += final_state.get("job_count", 0)
        totals["target_jobs"] += final_state.get("target_job_count", 0)
        totals["sheet_rows"] += final_state.get("written_sheet_count", 0)
        totals["db_rows"] += final_state.get("written_db_count", 0)

        errors = final_state.get("errors") or []

        if errors:
            print(f"\nNon-fatal errors in {city}:")
            for error in errors:
                print(f"  - {error}")

        if city_processed == 0:
            print(f"\nNo agencies processed for {city}; continuing to the next city.")

    print_summary(totals, db_enabled, sheets_enabled, args)
    return 0


def print_summary(totals: dict, db_enabled: bool, sheets_enabled: bool, args) -> None:
    print(f"\n{'=' * 78}")
    print("SUMMARY")
    print(f"{'=' * 78}")
    print(f"Agency candidates discovered       : {totals['discovered']}")
    print(f"Duplicates removed                 : {totals['duplicates']}")
    print(f"Agencies deep-researched           : {totals['processed']}")
    print(f"Relevant AI jobs identified        : {totals['target_jobs']}")
    print(f"Job rows written to Sheets         : {totals['jobs_written']}")
    print(f"Agency rows written to Sheets      : {totals['sheet_rows']}")
    print(f"Agency rows written to PostgreSQL  : {totals['db_rows']}")

    if not db_enabled:
        print(
            "\nNOTE: PostgreSQL writes were skipped "
            "(set DATABASE_URL in .env to enable persistence)."
        )

    if args.no_sheets:
        print("NOTE: Google Sheets writes were skipped (--no-sheets).")

    print(f"\nDistinct search queries used this run: {len(search_service._SEARCH_CACHE)}")
    print("Done.")


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
