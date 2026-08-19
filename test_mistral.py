from services.llm import get_llm

# Minimal Mistral connection test — ONE tiny call, no large prompts.
# Fails cleanly if MISTRAL_API_KEY is missing from .env.
try:
    llm = get_llm("discovery")
except ValueError as exc:
    print(f"SKIP: {exc}")
    exit(0)

response = llm.invoke("Say hello")

print(response.content[:200])