import gspread
from google.oauth2.service_account import Credentials

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

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=SCOPES
)

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
        row[0].strip().lower()
        for row in existing_rows
        if row and row[0].strip()
    }

    new_rows = []

    for company in companies:
        name = company.strip()

        if not name or name.lower() in existing_names:
            continue

        existing_names.add(name.lower())
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
    worksheet = get_sheet()
    rows = worksheet.get_all_values()

    if not rows:
        return set()

    headers = rows[0]
    name_index = _column_index(headers, name_field)

    return {
        row[name_index].strip().lower()
        for row in rows[1:]
        if len(row) > name_index and row[name_index].strip()
    }


def write_research_row(headers: list[str], data: dict, name_field: str = "company_name"):
    worksheet = get_sheet()
    ensure_research_headers(headers)

    existing_names = get_existing_entity_names(name_field)
    entity_name = str(data.get(name_field, "") or "").strip()

    if entity_name and entity_name.lower() in existing_names:
        print(f"Skipping duplicate entity: {entity_name}")
        return False

    worksheet.append_row(build_dynamic_row(headers, data))
    return True

