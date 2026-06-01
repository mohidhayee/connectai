"""
test_providers.py — confirm every configured provider works through ask().

Run with:  python test_providers.py
"""

from config import PROVIDERS
from providers import ask, total_cost

QUESTION = "In one short sentence, say hello and name which AI model you are."

print("Testing every provider in config.py...\n")

for name in PROVIDERS:
    print(f"=== {name} ===")
    try:
        reply = ask(QUESTION, provider=name)
        print(f"  ✅ {reply}\n")
    except Exception as e:
        print(f"  ❌ {e}\n")

print(f"💸 Total estimated cost this run: ${total_cost():.6f}")
