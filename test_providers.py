"""
test_providers.py — confirm each provider works through ask().

Tests the first curated model of every provider that has an API key set.
Providers without a key are skipped (so this stays free with just Groq/Gemini).

Run with:  python test_providers.py
"""

from config import PROVIDERS, MODELS
from providers import ask, total_cost, is_configured

QUESTION = "In one short sentence, say hello and name which AI model you are."

print("Testing the first model of every configured provider...\n")

for provider, cfg in PROVIDERS.items():
    label = cfg["label"]
    model = MODELS[provider][0]["id"]  # first curated model for this provider

    print(f"=== {label} ({model}) ===")
    if not is_configured(provider):
        print(f"  ⚠️  Skipped — {cfg['key_env']} is not set in .env\n")
        continue
    try:
        reply = ask(QUESTION, model=model)
        print(f"  ✅ {reply}\n")
    except Exception as e:
        print(f"  ❌ {e}\n")

print(f"💸 Total estimated cost this run: ${total_cost():.6f}")
