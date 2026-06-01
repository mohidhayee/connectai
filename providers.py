"""
providers.py — one simple way to talk to any AI provider.

Everything in ConnectAI calls `ask(...)` instead of talking to litellm directly.
That keeps all provider-specific detail in one place and tracks cost automatically,
so we always know how much we've spent.
"""

import os
from dotenv import load_dotenv
import litellm

from config import PROVIDERS, DEFAULT_PROVIDER

litellm.suppress_debug_info = True  # hide litellm's noisy AWS warnings
load_dotenv()                       # load API keys from .env

# Running total of estimated USD spent since the program started.
_total_cost = 0.0


class ProviderError(Exception):
    """Raised when a provider isn't configured correctly or a call fails."""


def ask(prompt, provider=DEFAULT_PROVIDER, system=None, messages=None):
    """Send a prompt to an AI provider and return its text reply.

    Args:
        prompt:   what you want to ask (a plain string).
        provider: friendly name from config.PROVIDERS, e.g. "groq" or "gemini".
        system:   optional system instruction that sets the AI's role/behaviour.
        messages: advanced — pass a full message list to continue a conversation.
                  If given, `prompt` and `system` are ignored.

    Returns:
        The AI's reply as a string.
    """
    global _total_cost

    if provider not in PROVIDERS:
        raise ProviderError(f"Unknown provider '{provider}'. Known: {list(PROVIDERS)}")

    cfg = PROVIDERS[provider]
    if not os.getenv(cfg["key_env"]):
        raise ProviderError(
            f"{cfg['key_env']} is not set in .env — can't use provider '{provider}'."
        )

    # Build the conversation if the caller only gave a simple prompt.
    if messages is None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

    try:
        response = litellm.completion(model=cfg["model"], messages=messages)
    except Exception as e:
        raise ProviderError(f"'{provider}' call failed: {str(e).splitlines()[0]}")

    # litellm attaches an estimated USD cost to every response.
    _total_cost += response._hidden_params.get("response_cost") or 0.0

    return response.choices[0].message.content.strip()


def total_cost():
    """Total estimated USD spent across all ask() calls so far."""
    return _total_cost


def reset_cost():
    """Reset the running cost counter back to zero."""
    global _total_cost
    _total_cost = 0.0
