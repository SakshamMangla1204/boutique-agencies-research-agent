# AI-Powered Opportunity Discovery Platform — Full Project Report

**Generated:** 21 August 2026  
**Repository:** `https://github.com/SakshamMangla1204/AI-powered-Oppurtunity-Discovery-platform-.git`  
**Language:** Python + JavaScript (React)  
**Architecture:** Agentic research pipeline + FastAPI backend + React frontend

---

## 1. Executive Summary

This project is a **full-stack agentic research platform** that:

1. Takes a user query (e.g., `"AI startups India"`)
2. Discovers relevant companies from the web using **Tavily** search + **Mistral** LLM
3. Researches each company (website, LinkedIn, description) using **Groq** LLM
4. Extracts structured fields via a dedicated extraction agent
5. Writes structured results to a **Google Sheet** for persistent storage
6. Exposes a **FastAPI backend** with live logging and a **React/Vite frontend**

The system turns ad-hoc manual research into a repeatable, automated pipeline deployed on Render + Vercel.

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| **Language** | Python 3 + JavaScript (React) |
| **Orchestration** | LangGraph |
| **Web Search** | Tavily API |
| **LLM (Discovery)** | Mistral — `mistral-large-latest` |
| **LLM (Research / Contact / Extraction)** | Groq — `openai/gpt-oss-120b` |
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | React + Vite |
| **Storage** | Google Sheets (`gspread` + service account) |
| **Config** | `.env` (via `python-dotenv`) |
| **Deployment** | Render (backend) + Vercel (frontend) |

**Note:** No Ollama is used anywhere in the codebase. All LLM calls go to Groq and Mistral.

---

## 3. Project Structure

```text
company-research-agent/
├── .env.example                      # Template for required env vars
├── .gitignore
├── README.md
├── PROJECT_REPORT.md
├── requirements.txt                  # Pinned dependencies
├── main.py                           # Research pipeline entry point
├── worker.py                         # Legacy row-by-row worker
├── render.yaml                       # Render deployment config
│
├── agents/
│   ├── contact.py                    # Contact extraction agent
│   ├── discovery.py                  # Discovery agent (batched, dedup)
│   ├── enrichment.py                 # Placeholder
│   ├── extraction.py                 # Structured field extractor
│   ├── memory.py                     # Placeholder
│   ├── qc.py                         # Placeholder
│   ├── research.py                   # Entity research agent
│   ├── scoring.py                    # Lead scoring (rule-based)
│   └── verification.py               # Placeholder
│
├── api/
│   └── server.py                     # FastAPI backend with live logs
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vercel.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx                   # Main UI with live backend logs
│       ├── index.css
│       └── main.jsx
│
├── graph/
│   ├── discovery_graph.py            # Placeholder
│   └── research_graph.py             # LangGraph pipeline
│
├── services/
│   ├── llm.py                        # Central LLM factory (Groq + Mistral)
│   └── sheets_writer.py              # Google Sheets writer
│
├── state/
│   ├── discovery_state.py            # Placeholder
│   ├── research_config.py            # ResearchConfig TypedDict
│   └── research_state.py             # ResearchState TypedDict
│
└── test_*.py                         # Manual test scripts
```

---

## 4. LLM Configuration (`services/llm.py`)

The central LLM factory routes each task to its provider. Instances are cached per task; missing API keys raise at startup.

| Task | Provider | Model | Env Key |
|---|---|---|---|
| `discovery` | Mistral | `mistral-large-latest` | `MISTRAL_API_KEY` |
| `research` | Groq | `openai/gpt-oss-120b` | `GROQ_API_KEY` |
| `contact` | Groq | `openai/gpt-oss-120b` | `GROQ_API_KEY` |
| `extraction` | Groq | `openai/gpt-oss-120b` | `GROQ_API_KEY` |

---

## 5. Agents Overview

### Discovery (`agents/discovery.py`)

Batched discovery of up to 100 unique entities:

- Generates 10 fresh search queries via Mistral, avoiding the dedup memory file `state/discovery_queries.json`
- Fallback query templates if generation fails
- Tavily searches with per-batch variation of `search_depth`, `topic`, `country`
- Extracts JSON entity lists via Mistral
- Key functions: `discover_entity_batch`, `discover_entities`, `discover_companies`

### Research (`agents/research.py`)

- Searches Tavily for website / LinkedIn / description
- Fixes prompt into Groq; parses `Website:`, `LinkedIn:`, `Description:` lines
- Also used for contact fields via `research_entity(entity, fields)`

### Contact (`agents/contact.py`)

- Searches Tavily for careers/jobs/contact results
- Sends strict JSON prompt to Groq: `{apply_link, careers_email, hr_email}`
- Sets status: `CONTACT_FOUND` or `RESEARCHED`

### Extraction (`agents/extraction.py`)

- `extract_fields(entity, source_content, fields)` returns JSON for exactly the requested fields
- Strict JSON schema, no fabricated data, missing fields = `""`

### Scoring (`agents/scoring.py`)

- Rule-based: website +30, linkedin +30, apply_link +40 (max 100)
- Not wired into active pipeline

---

## 6. Main Pipeline (`main.py`)

`run_research_pipeline(config, progress_callback=None)`:

1. Validate config
2. Read persistent memory from Google Sheets (fails fast on startup errors)
3. Run discovery batches (max 5) with two-level dedup
4. For each new entity: `research_entity()` → `extract_fields()` → `write_research_row()`
5. Emit progress events for API layer
6. Print a structured summary (stop reason, discovered, skipped, written, failed)

**Stop reasons:** `TARGET_REACHED`, `MAX_BATCHES_REACHED`, `MAX_EMPTY_BATCHES_REACHED`, `DISCOVERY_FAILED`, `STARTUP_FAILED`

---

## 7. Backend & Frontend

### API (`api/server.py`)
- FastAPI app wrapping the pipeline
- Live backend logging console via SSE for the frontend

### Frontend (`frontend/`)
- React + Vite SPA
- Renders live pipeline logs and results
- Deployed to Vercel (`vercel.json`)

---

## 8. Google Sheets Integration (`services/sheets_writer.py`)

- Scopes: `spreadsheets`, `drive`; auth via service account `credentials.json`
- Spreadsheet name: `company-research-agent`
- Functions: `ensure_research_headers`, `get_existing_entity_names`, `write_research_row`, `normalize_entity_name`, `enqueue_companies`

---

## 9. Requirements (`requirements.txt`)

```
langgraph==0.6.11
tavily-python==0.7.26
python-dotenv==1.2.1
langchain-groq==0.3.8
langchain-mistralai==0.2.12
gspread==6.2.1
google-auth==2.49.0
fastapi==0.141.1
uvicorn==0.52.4
```

---

## 10. Environment Variables

`.env` (gitignored; `.env.example` committed):

```
TAVILY_API_KEY=...
GROQ_API_KEY=...
MISTRAL_API_KEY=...
```

Also requires `credentials.json` (Google service account, gitignored).

---

## 11. Test Scripts

Manual runnable scripts:

- `test_discovery.py`
- `test_research.py`
- `test_contact.py`
- `test_extraction.py`
- `test_groq.py`
- `test_mistral.py`
- `test_sheet.py`
- `test_tavily.py`

---

## 12. Data Flow

```text
Config query
  ↓
Google Sheets memory read (known entities)
  ↓
Discovery batch (Mistral queries → Tavily → Mistral extract)
  ↓
New-entity filter (dedup)
  ↓
For each entity:
  Research (Tavily + Groq) → source content
  Extraction (Groq → JSON fields)
  Write row to Google Sheets
  ↓
Summary: stop reason / discovered / skipped / written / failed
```

---

## 13. Deployment

- **Backend:** `render.yaml` → Render (FastAPI + Uvicorn)
- **Frontend:** `vercel.json` → Vercel (React static)

---

## 14. Current Limitations

1. Placeholder files: `enrichment.py`, `memory.py`, `qc.py`, `verification.py`, `discovery_graph.py`, `discovery_state.py`
2. No automated pytest/unittest suite
3. Query configurable but defaulted hardcoded in `main.py`
4. Uses `print()` + optional progress_callback (no structured logging)
5. No rate-limit/retry on Tavily/LLM calls
6. Legacy `worker.py` not part of active flow

---

## 15. Conclusion

A **modern, deployable agentic research platform** — cloud-based LLM architecture (Groq + Mistral, **no Ollama**), controlled discovery loop with Google Sheets as persistent memory, a clean extraction agent, an API layer, and a React frontend with live logging. The architecture is production-ready; remaining work is testing, logging, and wiring legacy placeholders.