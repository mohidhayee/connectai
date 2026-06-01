"""
config.py — which AI model to use for each provider.

This is the ONE place to change models. Everything else reads from here, so
you never have to hunt through the code to swap a model or add a provider.

Each provider maps to:
  - model:   the litellm model id
  - key_env: the environment variable (in .env) that holds its API key

Models are chosen to be cheap, to keep development costs near zero.
"""

PROVIDERS = {
    "groq": {
        "model": "groq/llama-3.3-70b-versatile",  # free tier, fast
        "key_env": "GROQ_API_KEY",
    },
    "gemini": {
        "model": "gemini/gemini-2.5-flash",        # cheap; gemini-2.0-flash is dead for new users
        "key_env": "GEMINI_API_KEY",
    },
    # Added in Phase 4 (before public launch), once an OpenAI key + spend cap are set:
    # "openai": {"model": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"},
}

# The provider used by default for everyday dev/testing (free).
DEFAULT_PROVIDER = "groq"
