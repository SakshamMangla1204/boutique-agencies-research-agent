"""Unit tests for the AI Engineer roadmap taxonomy (deterministic, no network).

Run:
    .venv/bin/python test_ai_roadmap.py
"""

from agents.ai_jobs import roadmap as R

CASES = [
    # (title, jd_text, expected_relevance)
    ("AI Engineer",
     "Build LLM applications using LangChain, RAG with vector databases, "
     "prompt engineering, Python, OpenAI APIs",
     R.TARGET_AI_ENGINEER),
    ("Generative AI Engineer",
     "Design and deploy GenAI solutions; RAG pipelines, embeddings, agents, "
     "GPT-4, fine-tuning",
     R.TARGET_AI_ENGINEER),
    ("RAG Engineer",
     "Own retrieval augmented generation pipelines, Pinecone, LangGraph agents, "
     "evaluation",
     R.TARGET_AI_ENGINEER),
    ("Applied AI Engineer",
     "Ship production AI features, model serving, inference, FastAPI, "
     "Hugging Face transformers",
     R.TARGET_AI_ENGINEER),
    ("LLM Engineer",
     "Build LLM applications, prompt engineering, embeddings, guardrails, evals",
     R.TARGET_AI_ENGINEER),
    ("Agentic AI Engineer",
     "Design multi-agent systems with LangGraph, tool calling, MCP, guardrails",
     R.TARGET_AI_ENGINEER),
    ("AI Solutions Engineer",
     "Integrate OpenAI and Gemini APIs into customer workflows, chatbot "
     "automation, Python",
     R.TARGET_AI_ENGINEER),
    # Conditional ML title WITH practical AI engineering -> TARGET
    ("Machine Learning Engineer",
     "Work on LLMs, RAG, vector DBs, LangChain and agentic workflows to ship "
     "GenAI products",
     R.TARGET_AI_ENGINEER),
    # Conditional ML title WITHOUT practical AI engineering -> RELATED
    ("Machine Learning Engineer",
     "Train CNN models, tune hyperparameters, classical ML, scikit-learn, "
     "feature engineering",
     R.RELATED_AI_ENGINEERING),
    # Target title but empty JD -> RELATED (title alone is not enough)
    ("AI Engineer",
     "Manage stakeholder communication and write documentation",
     R.RELATED_AI_ENGINEERING),
    # Excluded titles -> NOT_RELEVANT
    ("Data Engineer",
     "Build ETL pipelines in Spark and Airflow, data warehouse modeling",
     R.NOT_RELEVANT),
    ("AI Research Scientist",
     "Publish novel architectures, conduct fundamental deep learning research",
     R.NOT_RELEVANT),
    ("Business Analyst",
     "Gather requirements, create dashboards in Power BI",
     R.NOT_RELEVANT),
]

EXPECTED_BUCKETS = {
    "2-4 years experience": "3+",
    "0-2 years": "0-2",
    "3+ years": "3+",
    "Freshers welcome": "0 years",
    "5 years": "3+",
    "1 year": "0-1",
    "": "not specified",
}


def main() -> int:
    failures = 0

    print("=" * 110)
    print("ROADMAP RELEVANCE CLASSIFICATION")
    print("=" * 110)

    for title, jd, expected in CASES:
        relevance, score, reason = R.classify_job_relevance(title, jd)
        bucket, _ = R.title_strength(title)
        status = "PASS" if relevance == expected else "FAIL"

        if relevance != expected:
            failures += 1

        print(f"[{status}] {title:32s} title_bucket={bucket:11s} "
              f"-> {relevance:22s} ({score:3d})")
        print(f"        reason: {reason}")

    print()
    print("=" * 110)
    print("EXPERIENCE BUCKETS")
    print("=" * 110)

    for text, expected in EXPECTED_BUCKETS.items():
        actual = R.detect_experience_bucket(text)
        status = "PASS" if actual == expected else "FAIL"

        if actual != expected:
            failures += 1

        print(f"[{status}] {text!r:26s} -> {actual!r} (expected {expected!r})")

    print()
    print("=" * 110)
    print("FRESHER FRIENDLINESS")
    print("=" * 110)

    for text, expected in [
        ("0-1 years", "YES"),
        ("0-2 years", "YES"),
        ("1-2 years", "POSSIBLY"),
        ("3+ years", "NO"),
        ("", "UNKNOWN"),
    ]:
        actual = R.classify_fresher(text)
        status = "PASS" if actual == expected else "FAIL"

        if actual != expected:
            failures += 1

        print(f"[{status}] {text!r:14s} -> {actual} (expected {expected})")

    print()
    print("=" * 110)
    print("TECHNOLOGY / DOMAIN EXTRACTION")
    print("=" * 110)

    sample = "Python, RAG, LangGraph, Pinecone, prompt engineering, GPT-4, embeddings"
    print("technologies :", R.extract_technologies(sample))
    print("ai_domain    :", R.detect_ai_domain(sample))
    print("flags        :", R.technology_flags(sample))
    print("signal score :", R.technology_signal_score(sample))

    print()
    print(f"RESULT: {'ALL CHECKS PASSED' if failures == 0 else f'{failures} CHECK(S) FAILED'}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
