import json
import os
import re
import time

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

HEADERS = [
    "company_name",
    "website",
    "linkedin",
    "description",
    "hr_email",
    "founder_email",
    "careers_email",
    "apply_email",
    "apply_link",
    "lead_score",
    "status"
]

# Tokens that are structural/legal descriptors and should not affect
# entity-identity comparison (e.g. "Yellow.AI Inc." == "Yellow AI").
SUFFIX_TOKENS = {
    "inc", "llc", "ltd", "limited", "pvt", "private", "corp",
    "corporation", "co", "company", "llp", "plc", "group",
    "technologies", "technology", "systems", "solutions", "labs",
    "ventures", "holdings",
}

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_SLUG_RE = re.compile(r"[-_/]+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")


def normalize_entity_name(name) -> str:
    """Deterministic entity-name normalization for deduplication.

    Handles case, whitespace, punctuation and common structural suffixes so
    that e.g. "Yellow.ai", "yellow ai" and "Yellow AI " all normalize to the
    same key.  Pure Python - no LLM involved.
    """
    if not name:
        return ""

    text = str(name).strip()

    if not text:
        return ""

    # If the value is a URL (e.g. a LinkedIn/company slug), use the last
    # meaningful path segment instead of the whole URL.
    if _URL_RE.match(text):
        path = text.split("?", 1)[0].rstrip("/")
        segment = path.rsplit("/", 1)[-1]

        if segment:
            text = _SLUG_RE.sub(" ", segment)

    text = text.lower().strip()
    text = _NON_ALNUM_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    tokens = [token for token in text.split() if token not in SUFFIX_TOKENS]

    # Compact removes the difference between "yellow ai", "yellow.ai",
    # "yellowai" and "Yellow AI ".
    return "".join(tokens)


def _load_credentials():
    """Load Google service-account credentials.

    Supports two mechanisms:
    1. Local file: `credentials.json` (development)
    2. Environment variable: `GOOGLE_CREDENTIALS_JSON` containing the
       full service-account JSON (production / Render)
    """
    env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()

    if env_creds:
        return Credentials.from_service_account_info(
            json.loads(env_creds),
            scopes=SCOPES,
        )

    return Credentials.from_service_account_file(
        "credentials.json",
        scopes=SCOPES,
    )


creds = _load_credentials()

client = gspread.authorize(creds)
sheet = None


def get_sheet():
    global sheet

    if sheet is None:
        sheet = client.open(
            "company-research-agent"
        ).sheet1

    return sheet


def ensure_headers():
    worksheet = get_sheet()
    first_row = worksheet.row_values(1)

    if not first_row:
        worksheet.append_row(HEADERS)


def build_row(data):
    return [data.get(header, "") for header in HEADERS]


def row_to_data(row):
    padded_row = list(row[:len(HEADERS)])

    while len(padded_row) < len(HEADERS):
        padded_row.append("")

    return dict(zip(HEADERS, padded_row))


def write_company(data):
    worksheet = get_sheet()
    ensure_headers()
    worksheet.append_row(build_row(data))


def enqueue_companies(companies):
    worksheet = get_sheet()
    ensure_headers()

    existing_rows = worksheet.get_all_values()[1:]
    existing_names = {
        normalize_entity_name(row[0])
        for row in existing_rows
        if row and row[0].strip()
    }

    new_rows = []

    for company in companies:
        name = company.strip()

        if not name or normalize_entity_name(name) in existing_names:
            continue

        existing_names.add(normalize_entity_name(name))
        new_rows.append(build_row({
            "company_name": name,
            "status": "NEW"
        }))

    if new_rows:
        worksheet.append_rows(new_rows)

    return len(new_rows)


def get_next_new_row():
    worksheet = get_sheet()
    ensure_headers()

    rows = worksheet.get_all_values()

    for index, row in enumerate(rows[1:], start=2):
        data = row_to_data(row)

        if data["status"] == "NEW" and data["company_name"]:
            return {
                "row_number": index,
                "data": data
            }

    return None


def update_company_row(row_number, data):
    worksheet = get_sheet()
    ensure_headers()
    worksheet.update(f"A{row_number}:K{row_number}", [build_row(data)])


def _column_index(headers_row, field_name: str) -> int:
    normalized = field_name.strip().lower()

    for index, header in enumerate(headers_row):
        if header.strip().lower() == normalized:
            return index

    return 0


def ensure_research_headers(headers: list[str]):
    worksheet = get_sheet()
    first_row = worksheet.row_values(1)

    if not first_row:
        worksheet.append_row(headers)


def build_dynamic_row(headers: list[str], data: dict):
    return [str(data.get(header, "") or "") for header in headers]


def get_existing_entity_names(name_field: str = "company_name") -> set[str]:
    """Return normalized known entity names already stored in the sheet."""
    worksheet = get_sheet()
    rows = worksheet.get_all_values()

    if not rows:
        return set()

    headers = rows[0]
    name_index = _column_index(headers, name_field)

    return {
        normalize_entity_name(row[name_index])
        for row in rows[1:]
        if len(row) > name_index and row[name_index].strip()
    }


def _with_retry(func, *args, retries: int = 3, delay: float = 2.0, **kwargs):
    """Retry a Google Sheets operation on transient connection errors."""
    last_exc = None

    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            print(f"  Sheet operation failed (attempt {attempt}/{retries}): {exc}")

            if attempt < retries:
                time.sleep(delay * attempt)

    raise last_exc


def write_research_row(headers: list[str], data: dict, name_field: str = "company_name"):
    """Append a row, skipping it if the entity is already known.

    This is the Level-2 duplicate protection: it runs again right before
    writing even though entities are normally filtered before research.
    """
    worksheet = get_sheet()
    ensure_research_headers(headers)

    existing_names = get_existing_entity_names(name_field)
    entity_name = str(data.get(name_field, "") or "").strip()

    if entity_name and normalize_entity_name(entity_name) in existing_names:
        print(f"Skipping duplicate entity: {entity_name}")
        return False

    _with_retry(worksheet.append_row, build_dynamic_row(headers, data))
    return True