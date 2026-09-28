"""Tests for the JSON parsing / content trimming utilities (no network).

Run:
    .venv/bin/python test_ai_utils.py
"""
from utils.json_parse import (
    extract_json_array,
    extract_json_object,
    strip_code_fences,
    strip_model_preamble,
    trim_web_content,
)

FIXTURES = [
    # (label, raw, expected_keys)
    ("plain json", '{"job_relevance": "TARGET_AI_ENGINEER", "score": 80}', {"job_relevance", "score"}),
    ("fenced json", '```json\n{"a": 1}\n```', {"a"}),
    ("fenced no lang", '```\n{"a": 1}\n```', {"a"}),
    ("with think block", '<think>reasoning here</think>\n{"a": 1}', {"a"}),
    ("prose around json", 'Here is the result:\n{"a": 1}\nHope that helps!', {"a"}),
    ("nested json", '{"job": {"title": "AI Engineer", "flags": {"llm": true}}}', {"job"}),
]

ARRAY_FIXTURES = [
    ("plain array", '["A", "B", "C"]'),
    ("fenced array", '```json\n["A"]\n```'),
    ("prose array", 'Result:\n["A", "B"]\nDone'),
]


def main() -> int:
    failures = 0

    print("=" * 100)
    print("JSON OBJECT EXTRACTION")
    print("=" * 100)

    for label, raw, expected_keys in FIXTURES:
        try:
            data = extract_json_object(raw)

            if set(data.keys()) != expected_keys:
                failures += 1
                print(f"[FAIL] {label}: keys {set(data.keys())} != {expected_keys}")
            else:
                print(f"[PASS] {label}: {data}")
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {label}: raised {type(exc).__name__}: {exc}")

    print()
    print("=" * 100)
    print("JSON ARRAY EXTRACTION")
    print("=" * 100)

    for label, raw in ARRAY_FIXTURES:
        try:
            data = extract_json_array(raw)

            if not isinstance(data, list) or not data:
                failures += 1
                print(f"[FAIL] {label}: {data!r}")
            else:
                print(f"[PASS] {label}: {data}")
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {label}: raised {type(exc).__name__}: {exc}")

    print()
    print("=" * 100)
    print("INVALID INPUT HANDLING (must raise, never silently return junk)")
    print("=" * 100)

    for label, raw in [("empty", ""), ("no json", "nothing here")]:
        try:
            extract_json_object(raw)
            failures += 1
            print(f"[FAIL] {label}: expected an exception")
        except ValueError as exc:
            print(f"[PASS] {label}: ValueError({exc})")

    print()
    print("=" * 100)
    print("CONTENT TRIMMING (token efficiency)")
    print("=" * 100)

    noisy = "\n".join(
        [
            "Accept all cookies",
            "Privacy Policy",
            "Skip to content",
            "Menu",
            "Home",
            "TalentBridge is an AI recruitment agency in Gurugram specialising in LLM, RAG",
            "and generative AI hiring for product companies.",
            "Our services include contract staffing and executive search.",
            "Follow us",
            "Subscribe to our newsletter",
            "Copyright 2026 TalentBridge",
            "All rights reserved",
        ]
    )

    trimmed = trim_web_content(noisy, limit=1000)
    print("--- trimmed output ---")
    print(trimmed)
    print("--- end ---")

    for noise in ["Accept all cookies", "Privacy Policy", "Subscribe to our newsletter", "All rights reserved"]:
        if noise in trimmed:
            failures += 1
            print(f"[FAIL] noise line survived: {noise!r}")
        else:
            print(f"[PASS] removed noise: {noise!r}")

    if "AI recruitment agency in Gurugram" not in trimmed:
        failures += 1
        print("[FAIL] real content was removed")
    else:
        print("[PASS] real content preserved")

    # URL headers must survive so sources stay attributable.
    with_url = "URL: https://example.com/about\nTalentBridge AI recruitment Gurugram LLM RAG"
    trimmed_url = trim_web_content(with_url, limit=1000)

    if "URL: https://example.com/about" not in trimmed_url:
        failures += 1
        print("[FAIL] source URL header was stripped")
    else:
        print("[PASS] source URL header preserved")

    if len(trimmed) >= len(noisy):
        failures += 1
        print(f"[FAIL] trimming did not reduce size ({len(noisy)} -> {len(trimmed)})")
    else:
        print(f"[PASS] size reduced {len(noisy)} -> {len(trimmed)} chars")

    print()
    print("=" * 100)
    print(f"RESULT: {'ALL CHECKS PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
