"""
hello.py — the very first test.

Goal: prove we can talk to real AIs from two DIFFERENT companies (Groq and Google).
If both respond, the foundation of ConnectAI — talking to multiple providers — works.
"""

import os
from dotenv import load_dotenv  # loads keys from the .env file into the environment
import litellm  # one library that talks to Groq, Gemini, OpenAI, Anthropic, and ~100 others

# Quiet down litellm's noisy warnings about cloud providers we don't use.
litellm.suppress_debug_info = True

load_dotenv()  # read the secret keys from .env

# Each entry: a friendly name -> (litellm model id, which env var must be set)
PROVIDERS = {
    "groq":   ("groq/llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "gemini": ("gemini/gemini-2.5-flash",      "GEMINI_API_KEY"),
}

QUESTION = "In one short sentence, say hello and name which AI model you are."

for name, (model, key_var) in PROVIDERS.items():
    print(f"\n=== {name} ({model}) ===")
    if not os.getenv(key_var):
        print(f"  ⚠️  Skipped — {key_var} is not set in .env")
        continue
    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": QUESTION}],
        )
        answer = response.choices[0].message.content.strip()
        # litellm attaches an estimated USD cost to each response.
        cost = response._hidden_params.get("response_cost") or 0
        print(f"  ✅ {answer}")
        print(f"  💸 cost: ${cost:.6f}")
    except Exception as e:
        # Print just the first line so the error is readable, not a wall of text.
        print(f"  ❌ Failed: {str(e).splitlines()[0]}")

print("\nDone. Any provider showing ✅ is working.")
