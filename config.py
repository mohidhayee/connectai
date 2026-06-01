"""
config.py — the model catalog and provider list for ConnectAI.

This is the ONE place to add or retire models. Everything else reads from here.

Two pieces:
  - PROVIDERS: each AI company, its display name/icon, which API-key env var it
    uses, and a price tier.
  - MODELS:    for each provider, a short curated list of models you can pick in
    the UI, each with a friendly label and a one-line "what it's best at".

Users can also type a CUSTOM model id in the UI (any litellm model string),
so this list doesn't have to be exhaustive — it's just the friendly shortlist.
"""

# ── Providers (the companies) ─────────────────────────────────────────────────
# The keys ("groq", "gemini", ...) match the provider names litellm infers from
# a model string, so models resolve to the right key automatically.
PROVIDERS = {
    "groq": {
        "label": "Groq",
        "emoji": "⚡",
        "key_env": "GROQ_API_KEY",
        "tier": "free",
    },
    "gemini": {
        "label": "Gemini",
        "emoji": "✦",
        "key_env": "GEMINI_API_KEY",
        "tier": "cheap",
    },
    "openai": {
        "label": "ChatGPT",
        "emoji": "🤖",
        "key_env": "OPENAI_API_KEY",
        "tier": "paid",
    },
    "anthropic": {
        "label": "Claude",
        "emoji": "🧠",
        "key_env": "ANTHROPIC_API_KEY",
        "tier": "paid",
    },
    "perplexity": {
        "label": "Perplexity",
        "emoji": "🔎",
        "key_env": "PERPLEXITYAI_API_KEY",
        "tier": "paid",
    },
}

# ── Models (the curated shortlist per provider) ───────────────────────────────
# Each model: the litellm `id`, a friendly `label`, and its `strength` (what it's
# best at) — shown in the dropdown so people can match a model to the job.
MODELS = {
    "groq": [
        {"id": "groq/llama-3.3-70b-versatile",
         "label": "Llama 3.3 70B", "strength": "Free & fast — great default"},
        {"id": "groq/llama-3.1-8b-instant",
         "label": "Llama 3.1 8B", "strength": "Free & near-instant, lighter"},
    ],
    "gemini": [
        {"id": "gemini/gemini-2.5-flash",
         "label": "Gemini 2.5 Flash", "strength": "Cheap all-rounder, long context"},
        {"id": "gemini/gemini-2.5-flash-lite",
         "label": "Gemini 2.5 Flash Lite", "strength": "Near-zero cost, fastest"},
        {"id": "gemini/gemini-2.5-pro",
         "label": "Gemini 2.5 Pro", "strength": "Deep reasoning & math"},
    ],
    "openai": [
        {"id": "gpt-4o-mini",
         "label": "GPT-4o mini", "strength": "Cheap, reliable all-rounder"},
        {"id": "gpt-4o",
         "label": "GPT-4o", "strength": "Strong general intelligence"},
    ],
    "anthropic": [
        {"id": "anthropic/claude-haiku-4-5",
         "label": "Claude Haiku 4.5", "strength": "Fast & cheap"},
        {"id": "anthropic/claude-sonnet-4-6",
         "label": "Claude Sonnet 4.6", "strength": "Best-in-class writing & analysis"},
        {"id": "anthropic/claude-opus-4-8",
         "label": "Claude Opus 4.8", "strength": "Top-tier coding & agentic work"},
    ],
    "perplexity": [
        {"id": "perplexity/sonar",
         "label": "Sonar", "strength": "Live web search with citations"},
        {"id": "perplexity/sonar-pro",
         "label": "Sonar Pro", "strength": "Deeper web research, more sources"},
        {"id": "perplexity/sonar-reasoning",
         "label": "Sonar Reasoning", "strength": "Web search + step-by-step reasoning"},
    ],
}

# Sensible free/cheap defaults for the two starting agents.
DEFAULT_MODEL_A = "groq/llama-3.3-70b-versatile"   # free
DEFAULT_MODEL_B = "gemini/gemini-2.5-flash"        # cheap


def all_models():
    """Flat list of every curated model dict, across all providers."""
    return [m for models in MODELS.values() for m in models]


def find_model(model_id):
    """Return the curated model dict for an id, or None if it's a custom id."""
    for m in all_models():
        if m["id"] == model_id:
            return m
    return None
