from agents.extraction import extract_fields
from agents.research import research_entity

# Minimal extraction test: research one small entity, then extract fields.
ENTITY = "Krutrim"
FIELDS = ["company_name", "website", "linkedin", "description"]

print(f"\n=== EXTRACTION TEST: {ENTITY} ===\n")

source_content = research_entity(ENTITY, FIELDS)

extracted = extract_fields(ENTITY, source_content, FIELDS)

print("\nEXTRACTED FIELDS:")
for field in FIELDS:
    print(f"  {field}: {extracted.get(field, '')}")