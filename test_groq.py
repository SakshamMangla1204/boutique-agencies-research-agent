from services.llm import get_llm

# Minimal Groq connection test — ONE tiny call, no large prompts.
llm = get_llm("research")

response = llm.invoke("Say hello")

print(response.content[:200])