"""
providers.py — one simple way to talk to any AI model.

Everything in ConnectAI calls `ask(...)` instead of talking to litellm directly.
That keeps all provider-specific detail in one place and tracks cost automatically.

You pass a `model` (any litellm model id, e.g. "groq/llama-3.3-70b-versatile").
The provider (Groq, Gemini, OpenAI, Anthropic, ...) is figured out from the model
name. The API key can be passed in directly (bring-your-own-key) or, if omitted,
is read from the matching environment variable in .env.
"""

import os
import time
from dotenv import load_dotenv
import litellm

from config import PROVIDERS

litellm.suppress_debug_info = True  # hide litellm's noisy AWS warnings
# override=True so values in .env win over any empty/placeholder vars already in
# the shell environment (some tools pre-set e.g. ANTHROPIC_API_KEY to empty).
load_dotenv(override=True)          # load API keys from .env

# Running total of estimated USD spent since the program started.
_total_cost = 0.0

# Some failures are transient — rate limits (e.g. Groq's free tokens-per-minute
# cap), brief outages, timeouts — and clear if we wait a moment. We retry those a
# couple of times with a short backoff before giving up. Persistent errors (bad
# key, bad request) aren't in this set, so they fail fast. We match on the
# exception's class NAME to stay robust across litellm versions.
_RETRYABLE_ERRORS = {"RateLimitError", "ServiceUnavailableError", "Timeout",
                     "APIConnectionError", "InternalServerError"}
_RETRY_BACKOFF = (2, 6)   # seconds to wait before each retry; length = max retries


class ProviderError(Exception):
    """Raised when a model/provider isn't configured correctly or a call fails."""


def _is_retryable(exc):
    """True if this looks like a transient error worth retrying after a wait."""
    return type(exc).__name__ in _RETRYABLE_ERRORS


def provider_for(model):
    """Figure out which provider a model belongs to, e.g. 'anthropic'.

    Uses litellm's own detection (so bare ids like 'gpt-4o-mini' → 'openai'),
    and falls back to the part before the first '/' if detection fails.
    """
    try:
        return litellm.get_llm_provider(model)[1]
    except Exception:
        return model.split("/")[0] if "/" in model else model


def key_env_for(model):
    """The environment-variable name that holds this model's API key, or None."""
    cfg = PROVIDERS.get(provider_for(model))
    return cfg["key_env"] if cfg else None


def _resolve_key(model, api_key):
    """Pick the API key to use: an explicit one wins, else read it from .env."""
    if api_key:
        return api_key
    env_name = key_env_for(model)
    return os.getenv(env_name) if env_name else None


def ask(prompt=None, *, model, system=None, messages=None, api_key=None):
    """Send a prompt to a model and return its text reply.

    Args:
        prompt:   what you want to ask (a plain string).
        model:    a litellm model id, e.g. "groq/llama-3.3-70b-versatile".
        system:   optional system instruction that sets the AI's role/behaviour.
        messages: advanced — a full message list to continue a conversation.
                  If given, `prompt` and `system` are ignored.
        api_key:  optional — bring your own key. If omitted, read from .env.

    Returns:
        The AI's reply as a string.
    """
    global _total_cost

    key = _resolve_key(model, api_key)
    if not key:
        env_name = key_env_for(model) or "the matching API key"
        raise ProviderError(
            f"No API key for model '{model}'. Set {env_name} in .env, or pass your own key."
        )

    # Build the conversation if the caller only gave a simple prompt.
    if messages is None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

    # Call the model, retrying transient errors (rate limits, brief outages) with a
    # short backoff. Anything non-transient — or a transient error that won't clear
    # within our retries — is wrapped as a ProviderError for callers to handle.
    response = None
    for attempt in range(len(_RETRY_BACKOFF) + 1):
        try:
            response = litellm.completion(model=model, messages=messages, api_key=key)
            break
        except Exception as e:
            if attempt < len(_RETRY_BACKOFF) and _is_retryable(e):
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            raise ProviderError(f"'{model}' call failed: {str(e).splitlines()[0]}")

    # litellm attaches an estimated USD cost to most responses (may be 0 for
    # models it has no pricing data for).
    _total_cost += response._hidden_params.get("response_cost") or 0.0

    return response.choices[0].message.content.strip()


def is_configured(provider):
    """True if this provider exists in config AND its API key is set in .env."""
    cfg = PROVIDERS.get(provider)
    return bool(cfg and os.getenv(cfg["key_env"]))


def available_providers():
    """List of provider names that are ready to use (have their key set in .env)."""
    return [name for name in PROVIDERS if is_configured(name)]


def total_cost():
    """Total estimated USD spent across all ask() calls so far."""
    return _total_cost


def reset_cost():
    """Reset the running cost counter back to zero."""
    global _total_cost
    _total_cost = 0.0
