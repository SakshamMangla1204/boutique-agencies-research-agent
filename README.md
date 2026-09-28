# AI-powered Opportunity Discovery Platform

A Python-based agentic research pipeline that discovers companies from a user query, researches each company, extracts hiring/contact information, and stores the results in Google Sheets.

## What This Project Does

Given a search query such as:

```text
AI startups India
```

the project:

1. discovers relevant companies from the web
2. researches each company
3. extracts career and HR contact information
4. writes the final result to a Google Sheet

This turns ad-hoc research into a repeatable pipeline.

## Current Architecture

```text
User Query
↓
Discovery Agent
    Tavily + Mistral
↓
Companies List
↓
For each company
    Research Agent
        Tavily + Groq
    Contact Agent
        Tavily + Groq
↓
Google Sheets
```

## Active Flow

The main runtime entry point is [main.py](./main.py).

It currently:

1. sets a query
2. **pre-seeds the curated prestigious-boutiques list** (see [Boutique Add-on](#4-boutique-add-on)) as priority application targets
3. runs discovery to find more companies from the web
4. loops through the boutique + discovered companies
5. invokes the LangGraph research pipeline for each company
6. writes every final result to Google Sheets

### Prestigious-boutiques add-on

By default the pipeline seeds a curated list of prestigious **boutique AI companies /
firms** (startups and small consultancies that hire directly) *before* any web
discovery runs. These are processed first, and only the remaining slot capacity
is filled by web-discovered companies.

- Curated list: [agents/boutiques.py](./agents/boutiques.py)
- Toggle it off per job via `include_boutiques: false` (defaults to `true`).
- Already-known boutiques (already in the sheet) are automatically skipped.

## LangGraph Pipeline

The active graph is defined in [graph/research_graph.py](./graph/research_graph.py).

Current graph:

```text
Research → Contact → END
```

The scoring agent file still exists in the repo, but it is not part of the active graph right now.

## Agents

### 1. Discovery Agent

File: [agents/discovery.py](./agents/discovery.py)

Responsibilities:

- take a query string
- search Tavily for relevant web results
- send the combined search content to Mistral
- extract a clean JSON array of company names
- return up to 10 companies

Current model:

- `ChatMistralAI`
- model: `mistral-large-latest`

### 2. Research Agent

File: [agents/research.py](./agents/research.py)

Responsibilities:

- search for the official website
- search for the LinkedIn page
- generate a short company description

Fields filled:

- `company_name`
- `website`
- `linkedin`
- `description`

Current model:

- `ChatGroq`
- model: `openai/gpt-oss-120b`

### 3. Contact Agent

File: [agents/contact.py](./agents/contact.py)

Responsibilities:

- search for careers and job links
- extract HR-related contact details
- return structured JSON

Fields filled:

- `apply_link`
- `careers_email`
- `hr_email`

Current model:

- `ChatGroq`
- model: `openai/gpt-oss-120b`

Status logic:

- sets `status = "CONTACT_FOUND"` if `apply_link` exists
- otherwise sets `status = "RESEARCHED"`

### 4. Boutique Add-on

File: [agents/boutiques.py](./agents/boutiques.py)

A curated, deterministic list of prestigious **boutique AI companies / firms**
(startups and small consultancies that hire directly). This is an *add-on* to
the overall list of companies the pipeline targets for applications.

Responsibilities:

- holds the curated `PRESTIGIOUS_BOUTIQUES` list (in priority order)
- `load_boutique_targets()` returns the names, deduped against the sheet
- no LLM or web search is involved (fast, deterministic, always available)

How it integrates:

- processed **before** any web discovery so boutique targets get priority
- only remaining slot capacity is filled by web-discovered companies
- toggle per job with `include_boutiques` (defaults to `true`)

## State Object

The shared state is defined in [state/research_state.py](./state/research_state.py).

Main fields:

- `query`
- `companies`
- `company_name`
- `website`
- `linkedin`
- `description`
- `hr_email`
- `founder_email`
- `careers_email`
- `apply_email`
- `apply_link`
- `lead_score`
- `status`

Not every field is actively populated by the current pipeline. Some are placeholders for future expansion.

## Google Sheets Integration

File: [services/sheets_writer.py](./services/sheets_writer.py)

The project writes one row per company into a Google Sheet named:

```text
company-research-agent
```

The writer uses:

- `gspread`
- a Google service account
- a local `credentials.json` file

Each row currently includes:

- company name
- website
- LinkedIn
- description
- HR email
- founder email
- careers email
- apply email
- apply link
- lead score
- status

## Project Structure

```text
.
├── agents/
│   ├── contact.py
│   ├── discovery.py
│   ├── enrichment.py
│   ├── extraction.py
│   ├── memory.py
│   ├── qc.py
│   ├── research.py
│   ├── scoring.py
│   └── verification.py
├── api/
│   └── server.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   ├── vercel.json
│   └── vite.config.js
├── graph/
│   ├── discovery_graph.py
│   └── research_graph.py
├── services/
│   ├── llm.py
│   └── sheets_writer.py
├── state/
│   ├── discovery_state.py
│   ├── research_config.py
│   └── research_state.py
├── main.py
├── worker.py
├── render.yaml
├── requirements.txt
├── test_contact.py
├── test_discovery.py
├── test_extraction.py
├── test_groq.py
├── test_mistral.py
├── test_research.py
├── test_sheet.py
└── test_tavily.py
```

## Setup

### 1. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `.env`

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required keys:

- `TAVILY_API_KEY`
- `GROQ_API_KEY`
- `MISTRAL_API_KEY`

### 4. Add Google Sheets credentials

Place your Google service account JSON file in the project root as:

```text
credentials.json
```

## How To Run

Run the full pipeline:

```bash
python3 main.py
```

Run the API server:

```bash
python3 api/server.py
```

Run the frontend (from the `frontend/` directory):

```bash
npm install
npm run dev
```

## Test Scripts

The repo includes small manual test files:

- [test_discovery.py](./test_discovery.py)
- [test_research.py](./test_research.py)
- [test_contact.py](./test_contact.py)
- [test_extraction.py](./test_extraction.py)
- [test_groq.py](./test_groq.py)
- [test_mistral.py](./test_mistral.py)
- [test_tavily.py](./test_tavily.py)
- [test_sheet.py](./test_sheet.py)

These are simple runnable scripts for checking individual parts of the system.

## Current Strengths


---

# AI Engineer Recruitment & Job Research Agent (Add-on Pipeline)

A specialized research pipeline targeting **boutique and mid-size Indian recruitment/staffing agencies** hiring **AI Engineers** (aligned with the [roadmap.sh/ai-engineer](https://roadmap.sh/ai-engineer) profile), prioritizing **Delhi-NCR**, scoring AI demand, and persisting structured intelligence to **PostgreSQL** and **Google Sheets**.

## Overview

Unlike generic company research, this agent specifically uncovers:
1. **Recruitment Agencies**: Boutique/mid-size technical staffing firms operating in Delhi-NCR (Gurugram, Noida, Delhi, Greater Noida, Faridabad, Ghaziabad) and expansion tech hubs.
2. **AI Engineer Hiring Demand**: Evidence of dedicated AI/LLM practices, contract staffing, bulk mandates, and active AI roles.
3. **Structured Job Openings**: Specific client mandates classified strictly against the AI Engineer roadmap (`TARGET_AI_ENGINEER`, `RELATED_AI_ENGINEERING`, `NOT_RELEVANT`).
4. **Decision-Maker Contacts**: Founders, Managing Directors, Recruitment Heads, and AI Practice Leads with verified business emails and LinkedIn URLs.

## Roadmap.sh/ai-engineer Alignment

Job postings are evaluated through a two-tier evaluation system (deterministic heuristics + LLM classification):

- **`TARGET_AI_ENGINEER` (High Priority)**: Practical LLM, RAG, and AI system engineering roles:
  - Titles: AI Engineer, Generative AI Engineer, RAG Engineer, LLM Engineer, Agentic AI Engineer, Applied AI Engineer.
  - Core requirements: Model integration (OpenAI, Anthropic, open-source via vLLM/Ollama), RAG systems (vector DBs, chunking, embeddings), Agent frameworks (LangGraph, CrewAI, AutoGen), prompt engineering, LLM evaluation, and production deployment.
  - ML titles qualify as `TARGET_AI_ENGINEER` **only** if the JD explicitly focuses on LLM/GenAI/RAG/Agents.
- **`RELATED_AI_ENGINEERING` (Secondary)**: Traditional ML or data science roles without modern LLM/agent components (classical NLP, computer vision pipelines, scikit-learn/PyTorch predictive models).
- **`NOT_RELEVANT` (Excluded)**: Generic software, full-stack, DevOps, academic research, hardware/robotics AI, or pure BI/data engineering roles without practical application of modern AI stacks.
- **Fresher-Friendliness**: Structured classification (`YES`, `POSSIBLY`, `NO`, `UNKNOWN`) based on experience requirement bounds (e.g. `0-1`, `0-2` years).

## Scoring Architecture

To ensure high data integrity, **AI Demand Score** and **Geographic Priority Score** are kept strictly independent:

### 1. AI Demand Score (0–100 Rubric)
Measures the depth of an agency's AI recruitment mandate:
- **Specialization (25 pts)**: GenAI/LLM recruitment (25 pts) or broad AI/technical recruitment (12–15 pts).
- **Active AI Hiring (25 pts)**: Confirmed active roles (25 pts) or estimated active roles (10–15 pts).
- **Multiple Mandates / Bulk Hiring (20 pts)**: Verified bulk AI mandates or ≥3 extracted relevant openings (20 pts).
- **Contract Staffing (10 pts)**: Provides contract/fractional AI engineer deployment.
- **Decision-Maker Discovered (10 pts)**: Founder, MD, or Recruitment Head identified.
- **Verified Business Email (10 pts)**: Non-freemail corporate contact found.
- **Demand Levels**: `VERY_HIGH` (80–100), `HIGH` (60–79), `MEDIUM` (40–59), `LOW` (20–39), `VERY_LOW` (0–19).

### 2. Geographic Priority Score (Isolated Dimension)
- **NCR Tier 1 (100)**: Gurugram / Gurgaon
- **NCR Tier 1 (95)**: Noida
- **NCR Tier 2 (90)**: Delhi / New Delhi
- **NCR Tier 3 (85)**: Greater Noida
- **NCR Tier 4 (75)**: Faridabad, Ghaziabad
- **Expansion Tier (60)**: Chandigarh, Mohali, Jaipur
- **Tech Hubs (40–50)**: Bengaluru, Hyderabad, Pune, Mumbai, Chennai, Kochi

## Dual Storage Architecture

### 1. PostgreSQL (Relational Intelligence)
Schema with full cascade foreign keys and deduplication indexes:
- `agencies`: Deduplicated by `normalized_domain` (primary) and `normalized_name` (fallback). Stores geographic tier, priority score, and metadata.
- `hiring_demand`: 1-to-1 with agency, storing AI demand score (/100), demand level, role counts, and evidence flags.
- `job_openings`: 1-to-many, deduplicated by `normalized_job_url` or `(agency_id, title, client, location)`. Stores roadmap classifications, tech stack, and fresher friendliness.
- `contacts`: Decision-makers with role classifications, email types (`business` vs `freemail`), and LinkedIn.
- `research_sources`: Complete audit log of every URL consulted.

### 2. Google Sheets
Dedicated writer (`services/sheets_agency_writer.py`) that accesses the spreadsheet via `GOOGLE_SHEET_ID` and appends only to two custom worksheets without altering the original sheet:
- `AI_RECRUITMENT_AGENCIES`: 41-column master registry of agencies, demand breakdowns, decision makers, and metadata.
- `AI_ENGINEER_JOB_OPENINGS`: 33-column tabular log of AI engineer jobs, roadmap relevance scores, reasons, and URLs.

## LangGraph Workflow

Compiled graph in `graph/ai_agency_graph.py`:

```text
discover_node
  ↓ (Tavily search across NCR queries, regex title/domain deduplication)
normalize_dedupe_node
  ↓ (Domain normalization & internal candidate deduplication)
db_existence_check_node
  ↓ (PostgreSQL existence lookup to avoid re-researching existing records)
filter_agencies_node
  ↓ (Caps candidates to requested limit)
[Agency Research Loop]
  ├── agency_research_node   (Agency profile, headquarters, service areas)
  ├── demand_research_node   (Specialization, contract staffing, bulk mandates)
  ├── job_research_node      (Structured client mandates & AI openings)
  ├── job_relevance_node     (Roadmap classification: TARGET / RELATED / NOT_RELEVANT)
  ├── contact_research_node  (Founders, MDs, Practice Heads, business emails)
  ├── scoring_node           (Calculates AI demand score /100 and confidence)
  ├── persist_node           (Upserts to PostgreSQL & appends to Google Sheets)
  └── next_agency_node       (Loops until queue empty)
  ↓
END
```

## Running the Pipeline

Ensure dependencies are installed and database is running:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run research for Delhi-NCR (default: 8 agencies across NCR)
python3 run_ai_agency_research.py

# Run for a specific city with a custom batch size
python3 run_ai_agency_research.py --city Gurugram --max 5

# Include expansion hubs (Chandigarh, Mohali, Jaipur, Bengaluru, etc.)
python3 run_ai_agency_research.py --expansion --max 10

# Run in deterministic relevance mode (skip LLM for job scoring)
python3 run_ai_agency_research.py --no-llm

# Skip PostgreSQL or Sheets writes if desired
python3 run_ai_agency_research.py --no-db
python3 run_ai_agency_research.py --no-sheets
```

## Verification Suite

Unit tests and verification scripts:
- `test_ai_foundation.py`: Validates domain normalization, name deduplication, tracking URL stripping, email classification, and scoring rubric.
- `test_ai_roadmap.py`: Tests 13 job titles/descriptions against roadmap rules, experience extraction, and technology detection.
- `test_ai_utils.py`: Verifies JSON parsing resilience, Markdown code block extraction, and web noise trimming.


- clear agent separation
- query-to-sheet automation
- practical use of Tavily for web search
- LangGraph orchestration for multi-step research
- cloud-based LLM architecture (Groq + Mistral) — no local model required

## Current Limitations

- some files in the repo are placeholders or not part of the active runtime
- discovery and contact quality still depend heavily on search result quality
- the Google Sheet schema still includes some fields that the current pipeline does not fully use

## Future Improvements

- add better parsing validation for model outputs
- add structured logging
- improve contact extraction accuracy
- clean unused placeholder files
- add real automated tests
- support configurable queries from CLI or UI

## Summary

This project is an agentic company research pipeline for opportunity discovery.

It combines:

- Tavily for web search
- Groq for high-quality company research and contact extraction
- Mistral for company discovery
- LangGraph for orchestration
- Google Sheets for persistent storage

The result is a practical workflow for finding companies, researching them, and storing structured opportunity data automatically.