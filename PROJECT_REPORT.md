# AI-Powered Opportunity Discovery Platform — Full Project Report

**Generated:** 19 August 2026  
**Repository:** `https://github.com/SakshamMangla1204/AI-powered-Oppurtunity-Discovery-platform-.git`  
**Language:** Python  
**Architecture:** Agentic research pipeline orchestrated with LangGraph

---

## 1. Executive Summary

This project is a **Python-based agentic research pipeline** that:

1. Takes a user query (e.g., `"AI startups India"`)
2. Discovers relevant companies from the web using **Tavily** search + an LLM
3. Researches each company (website, LinkedIn, description)
4. Extracts career/HR contact information (apply links, emails)
5. Writes structured results to a **Google Sheet** for persistent storage

The system turns ad-hoc manual research into a repeatable, automated pipeline.

---

## 2. Project Structure (Complete File Map)

```text
company-research-agent/
│
├── .gitignore                          # Git ignore rules
├── README.md                           # Project documentation
├── requirements.txt                    # ⚠️ EMPTY — dependencies not yet pinned
├── main.py                             # Main runtime entry point
├── worker.py                           # Row-by-row worker loop (research + contact)
│
├── agents/                             # Agent modules
│   ├── contact.py                      # Contact extraction agent (ACTIVE)
│   ├── discovery.py                    # Company discovery agent (ACTIVE)
│   ├── enrichment.py                   # ⚠️ EMPTY placeholder
│   ├── memory.py                       # ⚠️ EMPTY placeholder
│   ├── qc.py                           # ⚠️ EMPTY placeholder
│   ├── research.py                     # Company research agent (ACTIVE)
│   ├── scoring.py                      # Lead scoring agent (NOT in active graph)
│   └── verification.py                 # ⚠️ EMPTY placeholder
│
├── graph/                              # LangGraph orchestration
│   ├── discovery_graph.py              # ⚠️ EMPTY placeholder
│   └── research_graph.py               # ACTIVE LangGraph pipeline
│
├── services/                           # External integrations
│   └── sheets_writer.py                # Google Sheets writer service
│
├── state/                              # LangGraph state definitions
│   ├── discovery_state.py              # ⚠️ EMPTY placeholder
│   └── research_state.py               # ResearchState TypedDict
│
└── test_*.py                           # Manual test scripts (6 files)
    ├── test_contact.py
    ├── test_discovery.py
    ├── test_ollama.py
    ├── test_research.py
    ├── test_sheet.py
    └── test_tavily.py
```

---

## 3. File-by-File Detailed Description

### 3.1 `main.py` — Main Entry Point

**Purpose:** Orchestrates the full pipeline from query → discovery → enqueue → worker.

**Flow:**
1. Sets a hardcoded query: `"AI startups India"`
2. Calls `discover_companies(query)` from `agents/discovery.py`
3. Prints the total number of companies found
4. Calls `enqueue_companies(companies)` to add new companies to Google Sheets (deduplicated)
5. Calls `run_worker()` to process each `NEW` row through research + contact agents

**Key imports:**
```python
from agents.discovery import discover_companies
from services.sheets_writer import enqueue_companies
from worker import run_worker
```

---

### 3.2 `worker.py` — Row Processing Worker

**Purpose:** Processes companies row-by-row from the Google Sheet, updating status at each stage.

**Functions:**

| Function | Description |
|---|---|
| `build_state(row_data)` | Converts a Google Sheet row dict into a `ResearchState`-compatible dict |
| `run_worker()` | Infinite loop that: finds next `NEW` row → sets `RESEARCHING` → runs `research_agent` → sets `CONTACTING` → runs `contact_agent` → sets `COMPLETED`; on exception sets `FAILED` |

**Status lifecycle:**
```text
NEW → RESEARCHING → CONTACTING → COMPLETED
                        ↓ (on error)
                      FAILED
```

**Note:** The worker does **not** use the LangGraph `graph` object from `graph/research_graph.py` — it calls the agents directly in sequence. The LangGraph graph exists but is not invoked by the current runtime.

---

### 3.3 `agents/discovery.py` — Discovery Agent

**Purpose:** Discovers up to 100 unique company names from a base query.

**Constants:**
```python
MAX_QUERY_COUNT = 10          # Max search queries generated
MAX_RESULTS_PER_QUERY = 10    # Tavily results per query
MAX_COMPANY_COUNT = 100       # Max companies to extract
QUERY_MEMORY_FILE = Path("state/discovery_queries.json")  # Query dedup memory
```

**Models used:**
- `ChatOllama` — model `qwen3:8b`, temperature `0` (local LLM)
- `TavilyClient` — web search

**Functions:**

| Function | Description |
|---|---|
| `_extract_json_array(content, limit)` | Strips markdown fences, extracts JSON array from model output, deduplicates, returns up to `limit` items |
| `_load_used_queries()` | Loads previously used search queries from `state/discovery_queries.json` |
| `_save_used_queries(queries)` | Persists used queries to JSON file |
| `_fallback_queries(base_query)` | Hardcoded fallback query templates (e.g., `"top {query}"`, `"y combinator {query}"`) |
| `_generate_search_queries(base_query, used_queries)` | Uses Ollama to generate 10 diverse search queries, avoiding previously used ones |
| `_search_query(query)` | Calls Tavily, combines title/URL/content into a single text block |
| `_extract_companies(base_query, combined_content)` | Uses Ollama to extract a JSON array of company names from combined search content |
| `discover_companies(query)` | **Main entry:** generates queries → searches Tavily → extracts companies → saves used queries → returns company list |

**Dedup memory file:** `state/discovery_queries.json` (auto-created at runtime)

---

### 3.4 `agents/research.py` — Research Agent

**Purpose:** Researches a single company to find its official website, LinkedIn page, and a short description.

**Models used:**
- `ChatOllama` — model `qwen3:8b`, temperature `0`
- `TavilyClient` — web search

**Function:** `research_agent(state: ResearchState)`

**Flow:**
1. Searches Tavily: `"{company_name} official website linkedin company overview"` (max 5 results)
2. Combines title/URL/content into a text block
3. Sends to Ollama with a prompt requesting:
   - `Website: ...`
   - `LinkedIn: ...`
   - `Description: ...`
4. Parses the plain-text response line-by-line (prefix matching) and updates state fields:
   - `state["website"]`
   - `state["linkedin"]`
   - `state["description"]`

**Output format (plain text, not JSON):**
```text
Website: https://...
LinkedIn: https://linkedin.com/company/...
Description: ...
```

---

### 3.5 `agents/contact.py` — Contact Agent

**Purpose:** Extracts career/HR contact information for a company.

**Models used:**
- `ChatOllama` — model `qwen3:8b`, temperature `0`
- `TavilyClient` — web search

**Functions:**

| Function | Description |
|---|---|
| `_parse_contact_json(content)` | Strips markdown fences, extracts JSON object, returns `{apply_link, careers_email, hr_email}` |
| `contact_agent(state)` | **Main entry:** searches Tavily → sends to Ollama → parses JSON → updates state |

**Flow:**
1. Searches Tavily: `"{company_name} careers jobs internship contact"` (max 10 results)
2. Combines results into a text block
3. Sends to Ollama with strict JSON-output prompt:
   ```json
   {
     "apply_link": "",
     "careers_email": "",
     "hr_email": ""
   }
   ```
4. Parses JSON and updates state fields
5. Sets status logic:
   - `CONTACT_FOUND` if `apply_link` is non-empty
   - `RESEARCHED` otherwise

**Prompt rules for the LLM:**
- Never invent emails or URLs
- Return empty strings if not found
- Prefer application links in order: official careers page → jobs page → Greenhouse → Lever → Wellfound → LinkedIn Jobs
- Do not use company homepage unless no better link exists

---

### 3.6 `agents/scoring.py` — Scoring Agent (NOT in active graph)

**Purpose:** Computes a lead score based on available data.

**Logic:**
```python
if state["website"]:    score += 30
if state["linkedin"]:   score += 30
if state["apply_link"]: score += 40
```

**Max possible score:** 100

**Status:** Exists in the repo but is **not** wired into the active LangGraph pipeline or the worker.

---

### 3.7 Empty Placeholder Files

The following files exist but contain **no code** (0 bytes of logic):

| File | Intended Purpose (inferred) |
|---|---|
| `agents/enrichment.py` | Likely data enrichment (e.g., funding, employees) |
| `agents/memory.py` | Likely persistent memory / query history |
| `agents/qc.py` | Likely quality control / validation |
| `agents/verification.py` | Likely contact/email verification |
| `graph/discovery_graph.py` | Likely a LangGraph for the discovery phase |
| `state/discovery_state.py` | Likely a TypedDict for discovery state |

---

### 3.8 `graph/research_graph.py` — LangGraph Pipeline

**Purpose:** Defines the LangGraph state machine for the research pipeline.

**Graph definition:**
```python
builder = StateGraph(ResearchState)
builder.add_node("research", research_agent)
builder.add_node("contact", contact_agent)
builder.set_entry_point("research")
builder.add_edge("research", "contact")
builder.add_edge("contact", END)
graph = builder.compile()
```

**Graph topology:**
```text
START → research → contact → END
```

**Important:** This compiled `graph` object is **not imported or invoked** by `main.py` or `worker.py`. The worker calls the agents directly. The graph is currently a standalone definition.

---

### 3.9 `state/research_state.py` — State Definition

**Purpose:** Defines the shared state passed between agents using Python's `TypedDict`.

```python
class ResearchState(TypedDict):
    query: str
    companies: list
    company_name: str
    website: str
    linkedin: str
    description: str
    hr_email: str
    founder_email: str
    careers_email: str
    apply_email: str
    apply_link: str
    lead_score: int
    status: str
```

**Field usage matrix:**

| Field | Populated by Research Agent | Populated by Contact Agent | Populated by Scoring Agent | Used in Sheets |
|---|---|---|---|---|
| `query` | ❌ | ❌ | ❌ | ❌ |
| `companies` | ❌ | ❌ | ❌ | ❌ |
| `company_name` | ✅ (pre-set) | ✅ | ❌ | ✅ |
| `website` | ✅ | ❌ | ✅ (read) | ✅ |
| `linkedin` | ✅ | ❌ | ✅ (read) | ✅ |
| `description` | ✅ | ❌ | ❌ | ✅ |
| `hr_email` | ❌ | ✅ | ❌ | ✅ |
| `founder_email` | ❌ | ❌ | ❌ | ✅ |
| `careers_email` | ❌ | ✅ | ❌ | ✅ |
| `apply_email` | ❌ | ❌ | ❌ | ✅ |
| `apply_link` | ❌ | ✅ | ✅ (read) | ✅ |
| `lead_score` | ❌ | ❌ | ✅ | ✅ |
| `status` | ❌ | ✅ (sets) | ❌ | ✅ |

---

### 3.10 `services/sheets_writer.py` — Google Sheets Integration

**Purpose:** Persistent storage layer using Google Sheets as a lightweight database/queue.

**Google API scopes:**
```python
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
```

**Authentication:** Google service account via `credentials.json` (local file, gitignored).

**Spreadsheet name:** `company-research-agent` (first worksheet / `sheet1`)

**Column headers (11 columns, A–K):**
```python
HEADERS = [
    "company_name",   # A
    "website",        # B
    "linkedin",       # C
    "description",    # D
    "hr_email",       # E
    "founder_email",  # F
    "careers_email",  # G
    "apply_email",    # H
    "apply_link",     # I
    "lead_score",     # J
    "status"          # K
]
```

**Functions:**

| Function | Description |
|---|---|
| `get_sheet()` | Lazily opens and caches the worksheet |
| `ensure_headers()` | Writes header row if sheet is empty |
| `build_row(data)` | Maps a dict to a row list in HEADERS order |
| `row_to_data(row)` | Maps a row list back to a dict (pads missing values) |
| `write_company(data)` | Appends a single row |
| `enqueue_companies(companies)` | Deduplicates against existing rows, appends new companies with `status="NEW"`, returns count added |
| `get_next_new_row()` | Returns the first row with `status == "NEW"` as `{row_number, data}` or `None` |
| `update_company_row(row_number, data)` | Updates columns A–K for a given row number |

**Deduplication logic:** Compares `company_name` (lowercased, stripped) against all existing rows.

---

## 4. APIs and External Services Used

### 4.1 Tavily Search API

| Detail | Value |
|---|---|
| **Package** | `tavily-python` |
| **Client class** | `TavilyClient` |
| **Auth** | `TAVILY_API_KEY` environment variable |
| **Method used** | `tavily.search(query, max_results=N)` |
| **Response fields used** | `results[].title`, `results[].url`, `results[].content`, `results[].score` |
| **Purpose** | Web search for discovery, research, and contact extraction |

### 4.2 Ollama (Local LLM)

| Detail | Value |
|---|---|
| **Package** | `langchain-ollama` |
| **Client class** | `ChatOllama` |
| **Model** | `qwen3:8b` |
| **Temperature** | `0` (deterministic) |
| **Auth** | None (local server, default `http://localhost:11434`) |
| **Purpose** | Company extraction, search query generation, research parsing, contact extraction |

### 4.3 Groq API (Documented in README, not in current code)

| Detail | Value |
|---|---|
| **Package** | `langchain-groq` |
| **Client class** | `ChatGroq` |
| **Model** | `llama-3.3-70b-versatile` |
| **Auth** | `GROQ_API_KEY` environment variable |
| **Status** | Mentioned in README as the model for Discovery and Contact agents, but the **actual code** uses `ChatOllama` for both. The README is out of date with the code. |

### 4.4 Google Sheets API

| Detail | Value |
|---|---|
| **Packages** | `gspread`, `google-auth` |
| **Auth** | Service account JSON file: `credentials.json` |
| **Scopes** | `spreadsheets`, `drive` |
| **Spreadsheet** | `company-research-agent` |
| **Operations** | `open`, `sheet1`, `append_row`, `append_rows`, `get_all_values`, `row_values`, `update` |

### 4.5 LangGraph

| Detail | Value |
|---|---|
| **Package** | `langgraph` |
| **Usage** | `StateGraph`, `add_node`, `add_edge`, `set_entry_point`, `compile` |
| **Graph** | `research → contact → END` |
| **Status** | Defined but not invoked by the current runtime |

---

## 5. Complete Dependency List

### 5.1 Direct Dependencies (used in code)

| Package | Used in |
|---|---|
| `langgraph` | `graph/research_graph.py` |
| `tavily-python` | `agents/discovery.py`, `agents/research.py`, `agents/contact.py`, all test files |
| `python-dotenv` | All agent files, test files |
| `langchain-ollama` | `agents/discovery.py`, `agents/research.py`, `agents/contact.py`, test files |
| `langchain-groq` | README only (not in code) |
| `gspread` | `services/sheets_writer.py` |
| `google-auth` | `services/sheets_writer.py` |

### 5.2 Standard Library Modules Used

| Module | Used in |
|---|---|
| `json` | `agents/discovery.py`, `agents/contact.py` |
| `os` | All agent files, `services/sheets_writer.py` |
| `pathlib.Path` | `agents/discovery.py` |
| `typing.TypedDict` | `state/research_state.py` |

### 5.3 `requirements.txt` Status

**⚠️ EMPTY.** The file exists but contains no pinned dependencies. The README instructs users to install manually:

```bash
pip install langgraph tavily-python python-dotenv langchain-groq langchain-ollama gspread google-auth
```

---

## 6. Environment Variables & Configuration

### 6.1 `.env` File (gitignored)

```env
TAVILY_API_KEY=your_tavily_key
GROQ_API_KEY=your_groq_key
```

### 6.2 `credentials.json` (gitignored)

Google service account JSON file placed in the project root.

### 6.3 `.gitignore` Contents

```text
.env
credentials.json
__pycache__/
*.pyc
.DS_Store
```

### 6.4 Runtime-Generated Files

| File | Purpose |
|---|---|
| `state/discovery_queries.json` | Persists used search queries for deduplication across runs |

---

## 7. Data Flow (End-to-End)

```text
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                 │
│                                                                 │
│  query = "AI startups India"                                    │
│  companies = discover_companies(query)                          │
│  enqueue_companies(companies)  →  Google Sheets (status=NEW)    │
│  run_worker()                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  agents/discovery.py                            │
│                                                                 │
│  1. Load used queries from state/discovery_queries.json         │
│  2. Generate 10 diverse search queries (Ollama qwen3:8b)        │
│     └─ fallback to hardcoded templates if generation fails      │
│  3. For each query → Tavily.search(max_results=10)              │
│  4. Combine all results into one text block                     │
│  5. Extract company names as JSON array (Ollama)                │
│  6. Save used queries to JSON file                              │
│  7. Return up to 100 unique companies                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              services/sheets_writer.py                          │
│                                                                 │
│  enqueue_companies():                                           │
│  - Read all existing rows                                       │
│  - Deduplicate by company_name (case-insensitive)               │
│  - Append new rows with status="NEW"                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      worker.py                                  │
│                                                                 │
│  Loop:                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ get_next_new_row() → first row with status="NEW"        │    │
│  │                                                         │    │
│  │ status = "RESEARCHING" → update sheet                   │    │
│  │ research_agent(state)  → update sheet                   │    │
│  │ status = "CONTACTING"  → update sheet                   │    │
│  │ contact_agent(state)   → update sheet                   │    │
│  │ status = "COMPLETED"   → update sheet                   │    │
│  │                                                         │    │
│  │ On exception: status = "FAILED" → update sheet          │    │
│  └─────────────────────────────────────────────────────────┘    │
│  Exit when no NEW rows remain                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Agent Details Summary

| Agent | File | LLM | Search | Input | Output Fields | Status |
|---|---|---|---|---|---|---|
| Discovery | `agents/discovery.py` | Ollama `qwen3:8b` | Tavily | query string | list of company names | ✅ Active |
| Research | `agents/research.py` | Ollama `qwen3:8b` | Tavily | `ResearchState` | `website`, `linkedin`, `description` | ✅ Active |
| Contact | `agents/contact.py` | Ollama `qwen3:8b` | Tavily | `ResearchState` | `apply_link`, `careers_email`, `hr_email`, `status` | ✅ Active |
| Scoring | `agents/scoring.py` | None (rule-based) | None | `ResearchState` | `lead_score` | ⚠️ Not wired in |
| Enrichment | `agents/enrichment.py` | — | — | — | — | ❌ Empty |
| Memory | `agents/memory.py` | — | — | — | — | ❌ Empty |
| QC | `agents/qc.py` | — | — | — | — | ❌ Empty |
| Verification | `agents/verification.py` | — | — | — | — | ❌ Empty |

---

## 9. Test Scripts

All tests are **manual runnable scripts** (not pytest/unittest). They require live API keys and a running Ollama server.

| File | Purpose | Dependencies |
|---|---|---|
| `test_tavily.py` | Verifies Tavily search works; prints title/URL/content/score for each result | Tavily API key |
| `test_ollama.py` | Verifies Ollama responds (`"Say hello"`) | Local Ollama + `qwen3:8b` |
| `test_discovery.py` | Tests company extraction from Tavily results using Ollama | Tavily + Ollama |
| `test_research.py` | Tests research agent on hardcoded company `"Krutrim"` | Tavily + Ollama |
| `test_contact.py` | Tests contact extraction on hardcoded company `"Krutrim"` | Tavily + Ollama |
| `test_sheet.py` | Writes a `TEST COMPANY` row to Google Sheets | `credentials.json` + Google API |

---

## 10. Setup & Run Instructions

### 10.1 Prerequisites

- Python 3.x
- Ollama running locally with `qwen3:8b` pulled
- Tavily API key
- Google service account with Sheets + Drive access
- (README mentions Groq API key, though current code doesn't use it)

### 10.2 Setup Steps

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies (requirements.txt is empty)
pip install langgraph tavily-python python-dotenv langchain-groq langchain-ollama gspread google-auth

# 3. Create .env
# TAVILY_API_KEY=...
# GROQ_API_KEY=...

# 4. Place credentials.json in project root

# 5. Start Ollama
ollama serve
ollama pull qwen3:8b
```

### 10.3 Run

```bash
python3 main.py
```

---

## 11. Current Architecture Strengths

1. **Clear agent separation** — each agent has a single responsibility
2. **Query-to-sheet automation** — full pipeline from natural language query to structured data
3. **Deduplication** — both at the company level (sheet) and query level (JSON memory file)
4. **Graceful degradation** — fallback queries if LLM generation fails; try/except around Tavily calls
5. **Status tracking** — every row tracks its lifecycle state in the sheet
6. **Mixed local/cloud model architecture** — uses local Ollama for cost-effective processing
7. **Resumable worker** — the sheet acts as a queue; re-running the worker continues from where it left off

---

## 12. Current Limitations & Issues

| # | Issue | Severity |
|---|---|---|
| 1 | `requirements.txt` is empty — no reproducible dependency pinning | High |
| 2 | README says Discovery/Contact use Groq (`llama-3.3-70b-versatile`) but code uses Ollama (`qwen3:8b`) — documentation drift | Medium |
| 3 | LangGraph graph is defined but never invoked by the runtime (`worker.py` calls agents directly) | Medium |
| 4 | `scoring.py` agent exists but is not wired into the pipeline | Medium |
| 5 | 6 placeholder files are empty (`enrichment.py`, `memory.py`, `qc.py`, `verification.py`, `discovery_graph.py`, `discovery_state.py`) | Low |
| 6 | `founder_email` and `apply_email` fields are in the sheet schema but never populated | Low |
| 7 | No structured logging — uses `print()` statements | Medium |
| 8 | No real automated tests (pytest/unittest) — only manual scripts | High |
| 9 | Query is hardcoded in `main.py` — no CLI/UI configurability | Medium |
| 10 | Contact agent error message references "Gemini" (stale from an earlier iteration) | Low |
| 11 | No rate limiting / retry logic for Tavily or Ollama calls | Medium |
| 12 | `state/discovery_queries.json` grows unboundedly | Low |
| 13 | No email validation or verification of extracted contacts | Medium |
| 14 | Research agent uses fragile line-prefix parsing (`Website:`, `LinkedIn:`, `Description:`) — model output format drift can silently fail | Medium |

---

## 13. Suggested Future Improvements

1. **Populate `requirements.txt`** with pinned versions
2. **Wire the LangGraph graph into the worker** (or remove it)
3. **Add the scoring agent** to the pipeline and populate `lead_score`
4. **Add structured logging** (e.g., `logging` module or `loguru`)
5. **Add real automated tests** with mocked Tavily/Ollama responses
6. **Add CLI argument parsing** (e.g., `argparse` or `click`) for configurable queries
7. **Add retry/backoff logic** for external API calls
8. **Add email validation** (regex + deliverability checks)
9. **Clean up stale references** (e.g., "Gemini" error message, Groq in README)
10. **Implement the placeholder agents** (enrichment, memory, QC, verification) or remove them
11. **Add a config file** (YAML/JSON) for model names, max results, sheet name, etc.
12. **Add Docker support** for reproducible local Ollama + app setup

---

## 14. Technology Stack Summary

| Layer | Technology |
|---|---|
| **Language** | Python 3 |
| **Orchestration** | LangGraph |
| **Web Search** | Tavily API |
| **LLM (local)** | Ollama — `qwen3:8b` |
| **LLM (cloud, documented)** | Groq — `llama-3.3-70b-versatile` |
| **Storage** | Google Sheets (via `gspread` + service account) |
| **Config** | `.env` (via `python-dotenv`) |
| **Auth** | Google service account (`credentials.json`) |
| **Version Control** | Git (GitHub) |

---

## 15. Conclusion

This project is a functional **agentic company research pipeline** that automates the workflow of discovering companies, researching them, extracting contact information, and persisting structured results to Google Sheets. The core architecture is sound — clear agent separation, a sheet-as-queue pattern, and a resumable worker loop. The main gaps are documentation drift (README vs. code), an empty `requirements.txt`, unwired components (LangGraph graph, scoring agent), and the absence of real automated tests. With those addressed, this is a solid foundation for a production-grade opportunity discovery platform.