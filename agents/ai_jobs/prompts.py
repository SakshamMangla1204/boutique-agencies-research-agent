"""Prompt templates for the AI agency research agents.

Kept in one module so token usage is easy to audit and the "never invent
information" contract is stated identically everywhere.

Every agent receives ONLY trimmed search snippets (never a full webpage) and
must return strict JSON.  Unknown values must be null/"" - the prompts forbid
guessing so that missing data is stored as unknown rather than fabricated.
"""
from __future__ import annotations

ROADMAP_URL = "https://roadmap.sh/ai-engineer"

# Shared rule block repeated in every prompt.
NO_FABRICATION_RULES = """
RULES (strict):
- Use ONLY the information present in the SEARCH RESULTS below.
- Never invent a company name, URL, email, phone number, headcount, salary,
  job count, or job URL.
- If a value is not present in the search results, return null (or "" for
  strings). Do not guess or extrapolate.
- Return JSON only. No markdown, no commentary outside the JSON.
""".strip()


AGENCY_RESEARCH_PROMPT = """
You are a research analyst profiling recruitment/staffing agencies in India.

Agency: {agency_name}
Known domain: {domain}
Target market: {city}

Extract the agency's profile from the search results.

Return JSON exactly in this shape:
{{
  "agency_name": "",
  "domain": "",
  "country": "India",
  "primary_city": "",
  "state": "",
  "service_area": "",
  "ncr_presence": "YES | POSSIBLY | NO | UNKNOWN",
  "agency_type": "AI recruitment | IT staffing | technology recruitment | contract staffing | executive search | general HR | unknown",
  "linkedin": "",
  "description": "",
  "source_url": ""
}}

Field guidance:
- primary_city: the city the agency is actually based in (not the city it serves).
- ncr_presence: YES only if the agency clearly operates in Delhi NCR
  (Gurugram/Gurgaon, Noida, Delhi, Greater Noida, Faridabad, Ghaziabad).
- agency_type: pick the single best label from the list above.
- description: at most 2 sentences, factual, based only on the search results.
- Treat Gurgaon and Gurugram as the same city.
- source_url: the single best URL that supports this profile.

{rules}

SEARCH RESULTS:
{content}
""".strip()


DEMAND_RESEARCH_PROMPT = """
You are analysing whether a recruitment agency has REAL AI/technology hiring demand.

Agency: {agency_name}
Domain: {domain}

Determine, from the search results only, whether this agency recruits for AI,
GenAI, ML, LLM, RAG or other technology roles, and whether there is evidence of
active or bulk hiring.

Return JSON exactly in this shape:
{{
  "technical_recruitment": null,
  "ai_recruitment": null,
  "genai_recruitment": null,
  "contract_staffing": null,
  "bulk_hiring": null,
  "active_ai_roles": null,
  "estimated_ai_positions": null,
  "ai_roles": "",
  "technologies": "",
  "client_industries": "",
  "bulk_hiring_evidence": "",
  "evidence_date": ""
}}

Field guidance:
- technical_recruitment: true only if the agency recruits for software/IT/engineering roles.
- ai_recruitment: true only if AI/ML/AI-engineering roles are explicitly mentioned.
- genai_recruitment: true only if Generative AI / GenAI / LLM roles are explicitly mentioned.
- contract_staffing: true if they offer contract/temporary/contract-to-hire staffing.
- bulk_hiring: true only if the source explicitly describes multiple or bulk openings,
  a hiring drive, or many simultaneous roles.
- active_ai_roles: an INTEGER count only when the sources state a number.
  Otherwise null. NEVER estimate or invent a count.
- estimated_ai_positions: same rule - integer only with explicit evidence, else null.
- ai_roles: comma-separated AI/tech role titles actually mentioned (else "").
- technologies: comma-separated technologies actually mentioned (else "").
- bulk_hiring_evidence: quote or precisely paraphrase the evidence, else "".
- evidence_date: the date stated in the source (YYYY-MM-DD) if present, else "".

{rules}

SEARCH RESULTS:
{content}
""".strip()


JOB_RESEARCH_PROMPT = """
You are extracting AI Engineer job openings.

CRITICAL: The target role family is defined by the AI Engineer roadmap:
{roadmap_url}
We want practical AI-engineering roles (LLMs, GenAI, RAG, agents, AI
applications, model integration, AI APIs) - NOT generic ML/data/analytics jobs.

Agency: {agency_name}
Location focus: {city}

Extract every DISTINCT job opening described in the search results and return
JSON exactly in this shape:
{{
  "jobs": [
    {{
      "job_title": "",
      "company_or_client": "",
      "location": "",
      "remote_status": "Remote | Hybrid | Onsite | Not specified",
      "employment_type": "Full-time | Contract | Internship | Not specified",
      "experience_required": "",
      "salary": "",
      "job_url": "",
      "source_url": "",
      "posted_date": "",
      "required_skills": "",
      "preferred_skills": "",
      "jd_summary": ""
    }}
  ]
}}

Field guidance:
- Only include real, distinct openings found in the results. If none are found,
  return {{"jobs": []}}. Do NOT invent openings.
- job_title: exactly as written in the source.
- company_or_client: the hiring company/end client if stated (this may differ
  from the agency). Use "" when the agency is hiring for itself or it is unclear.
- experience_required: copy the stated experience range (e.g. "2-5 years") or "".
- salary: only if explicitly stated, else "".
- required_skills / preferred_skills: comma-separated skills actually listed, or "".
- jd_summary: at most 3 sentences describing the ACTUAL work (responsibilities),
  used later for roadmap relevance classification.
- posted_date: YYYY-MM-DD if stated, else "".
- Treat Gurgaon and Gurugram as the same location.

{rules}

SEARCH RESULTS:
{content}
""".strip()


JOB_RELEVANCE_PROMPT = """
You are classifying a job posting against the AI Engineer roadmap:
{roadmap_url}

Job title: {job_title}
Location: {location}
Job description / summary:
{jd_text}

Required skills: {required_skills}
Preferred skills: {preferred_skills}

Classify using BOTH the title and the actual work described:

- TARGET_AI_ENGINEER: practical AI engineering is the main job - building with
  LLMs/GenAI, RAG, embeddings, vector DBs, LangChain/LangGraph, agents, prompt
  engineering, AI APIs, pretrained-model integration, inference/model serving,
  Python AI applications, production AI systems.
  These titles qualify outright: AI Engineer, Artificial Intelligence Engineer,
  Generative AI / GenAI Engineer, LLM Engineer, AI Application Engineer,
  LLM Application Engineer, RAG Engineer, Agentic AI / AI Agent Engineer,
  Applied AI Engineer, AI Developer / GenAI Developer / LLM Developer,
  AI Solutions Engineer, AI Integration Engineer, AI Automation Engineer.
  ML Engineer / NLP Engineer / CV Engineer / MLOps Engineer / AI Platform
  Engineer qualify ONLY when the described work is practical AI engineering.

- RELATED_AI_ENGINEERING: adjacent to AI engineering but not primarily an
  AI application-engineering role, OR the title qualifies but the description
  shows no concrete AI engineering work.

- NOT_RELEVANT: research/analytics/data-plumbing roles - Research Scientist,
  ML/AI Researcher, research-focused Research Engineer, Data Analyst, Business
  Analyst, BI Analyst, Data Engineer, Analytics Engineer, Statistician, pure
  DevOps/Cloud/SRE, Embedded AI, FPGA/hardware/semiconductor AI, academic roles.

Weigh: responsibilities > required skills > technologies > title.
Do NOT classify on the title alone.

Return JSON exactly:
{{
  "job_relevance": "TARGET_AI_ENGINEER | RELATED_AI_ENGINEERING | NOT_RELEVANT",
  "job_relevance_score": 0,
  "relevance_reason": "",
  "ai_domain": "",
  "llm": false,
  "genai": false,
  "rag": false,
  "agents": false,
  "nlp": false,
  "computer_vision": false,
  "model_integration": false,
  "ai_application_development": false,
  "fresher_friendly": "YES | POSSIBLY | NO | UNKNOWN"
}}

Field guidance:
- job_relevance_score: 0-100, higher = closer to the AI Engineer roadmap.
- relevance_reason: 1-2 sentences citing the evidence you used.
- ai_domain: one of GenAI/LLM, RAG/Retrieval, Agentic AI, NLP, Computer Vision,
  Speech/Audio, MLOps/Platform, Conversational AI, Recommendation, or "".
- The boolean flags: true only when the JD provides evidence for that signal.
- fresher_friendly: YES if 0-2 years or freshers are welcome; POSSIBLY for 1-2
  years; NO for 3+ years; UNKNOWN when experience is not stated.

{rules}
""".strip()


CONTACT_RESEARCH_PROMPT = """
You are extracting publicly available business contacts for a recruitment agency.

Agency: {agency_name}
Domain: {domain}

Find decision makers who are relevant for hiring the agency's services:
Recruitment Head, Talent Acquisition Head, AI Practice Lead, Delivery Head,
Managing Director, Founder/Co-founder, Director, Partner.

Return JSON exactly:
{{
  "contacts": [
    {{
      "name": "",
      "role": "",
      "linkedin": "",
      "email": "",
      "email_type": "business | freemail | unknown",
      "source_url": ""
    }}
  ],
  "agency_email": "",
  "recruitment_email": ""
}}

STRICT RULES:
- Only include a person whose name AND role appear in the search results.
- Only include an email that is literally present in the search results.
  If no email is published, use "" - NEVER guess or construct an address.
- email_type: "business" for a company-domain address, "freemail" for
  gmail/yahoo/outlook etc., "unknown" when the email is "".
- source_url: the exact URL where the name/email was found. Required when an
  email or person is reported.
- If nothing is found, return {{"contacts": [], "agency_email": "", "recruitment_email": ""}}.

{rules}

SEARCH RESULTS:
{content}
""".strip()
