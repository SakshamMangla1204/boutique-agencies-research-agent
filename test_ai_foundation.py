"""Smoke test for the AI agency research foundation modules (no network).

Run:
    .venv/bin/python test_ai_foundation.py
"""
from agents.ai_jobs import demand_scoring as D
from services.db import dedupe, session
from state import agency_config as G
from state import search_queries as Q


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(label: str, actual, expected) -> None:
        checks.append((label, actual == expected, f"{actual!r} (expected {expected!r})"))

    print("=" * 100)
    print("DB LAYER")
    print("=" * 100)
    print("db status:", session.db_status())

    print()
    print("=" * 100)
    print("DEDUPE NORMALIZATION")
    print("=" * 100)
    check("normalize_domain",
          dedupe.normalize_domain("https://www.ABC-Staffing.com/jobs?utm_source=x"),
          "abc-staffing.com")
    check("normalize_domain (subdomain)",
          dedupe.normalize_domain("https://careers.talentbridge.in/jobs"),
          "talentbridge.in")
    check("normalize_agency_name",
          dedupe.normalize_agency_name("ABC Staffing Pvt Ltd"),
          "abcstaffing")
    check("normalize_agency_name (suffixes stripped)",
          dedupe.normalize_agency_name("ABC Staffing Private Limited"),
          "abcstaffing")
    check("normalize_agency_name (keeps descriptor words)",
          dedupe.normalize_agency_name("XYZ Technologies"),
          "xyztechnologies")
    check("normalize_agency_name (distinct agencies stay distinct)",
          dedupe.normalize_agency_name("ABC Staffing") == dedupe.normalize_agency_name("ABC Recruitment"),
          False)
    check("normalize_job_url (tracking stripped)",
          dedupe.normalize_job_url(
              "https://boards.greenhouse.io/acme/jobs/123?utm_source=li&gh_src=abc"),
          "https://boards.greenhouse.io/acme/jobs/123")
    check("normalize_job_url (same identity, diff tracking)",
          dedupe.normalize_job_url(
              "https://boards.greenhouse.io/acme/jobs/123/?utm_campaign=zzz"),
          "https://boards.greenhouse.io/acme/jobs/123")
    check("classify_email_type (business)",
          dedupe.classify_email_type("hr@acmestaffing.com"), "business")
    check("classify_email_type (freemail)",
          dedupe.classify_email_type("recruiter@gmail.com"), "freemail")

    print()
    print("=" * 100)
    print("JOB DEDUPE FALLBACK KEY")
    print("=" * 100)
    k1 = dedupe.job_dedupe_fallback_key(1, "AI Engineer", "Acme Corp", "Gurgaon")
    k2 = dedupe.job_dedupe_fallback_key(1, "  ai  engineer ", "acme corp", "GURGAON")
    k3 = dedupe.job_dedupe_fallback_key(2, "AI Engineer", "Acme Corp", "Gurgaon")
    check("fallback key stable across case/space", k1, k2)
    check("fallback key differs across agency", k1 == k3, False)
    print("key example:", k1)

    print()
    print("=" * 100)
    print("GEOGRAPHIC PRIORITY (separate from AI demand)")
    print("=" * 100)
    for city, expected_score in [
        ("Gurugram", 100), ("Gurgaon", 100), ("Noida", 95), ("Delhi", 90),
        ("New Delhi", 90), ("Greater Noida", 85), ("Sector 62, Noida, UP", 95),
        ("Faridabad", 75), ("Ghaziabad", 75), ("Chandigarh", 60),
        ("Mohali", 60), ("Jaipur", 60), ("Bengaluru", 50), ("Bangalore", 50),
        ("Kochi", 40),
    ]:
        tier, score = G.city_priority(city)
        check(f"priority {city}", score, expected_score)

    print()
    print("NCR presence:")
    for value in ["Gurugram", "Noida", "Delhi NCR", "Pan India", "London", ""]:
        print(f"  {value!r:14s} -> {G.has_ncr_presence(value)}")

    print()
    print("=" * 100)
    print("AI DEMAND SCORE RUBRIC")
    print("=" * 100)
    score, level, breakdown = D.compute_ai_demand_score(
        technical_recruitment=True,
        ai_recruitment=True,
        genai_recruitment=True,
        contract_staffing=True,
        bulk_hiring=True,
        active_ai_roles=5,
        contacts=[{"role": "Recruitment Head", "email": "hr@acmestaffing.com"}],
    )
    print("full-evidence breakdown:", breakdown)
    check("max score with full evidence", score, 100)
    check("level HIGH", level, "HIGH")

    score2, level2, breakdown2 = D.compute_ai_demand_score(
        ai_recruitment=True,
        contacts=[{"role": "Recruitment Head", "email": "recruiter@gmail.com"}],
    )
    print("partial breakdown      :", breakdown2)
    check("freemail earns no business-email points",
          breakdown2["business_email"], 0)
    check("decision maker scored", breakdown2["decision_maker"], 10)

    score3, level3, breakdown3 = D.compute_ai_demand_score()
    print("no-evidence breakdown  :", breakdown3)
    check("no evidence -> 0", score3, 0)
    check("no evidence -> VERY_LOW", level3, "VERY_LOW")

    print()
    print("=" * 100)
    print("SEARCH QUERY BUILDERS")
    print("=" * 100)
    print("agency queries for Noida:")
    for query in Q.agency_search_queries("Noida")[:4]:
        print("  ", query)
    print("job queries for Gurgaon:")
    for query in Q.job_search_queries("Gurgaon")[:4]:
        print("  ", query)
    print("NCR-first plan order:", [p["city"] for p in Q.ncr_first_search_plan()])

    print()
    print("=" * 100)
    failures = [c for c in checks if not c[1]]

    for label, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    print()
    print(f"RESULT: {'ALL CHECKS PASSED' if not failures else f'{len(failures)} CHECK(S) FAILED'}")
    return len(failures)


if __name__ == "__main__":
    raise SystemExit(main())
