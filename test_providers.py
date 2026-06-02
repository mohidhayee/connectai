"""
test_providers.py — tests for the provider layer (providers.py).

Two parts:
  1. Offline retry tests — prove `ask()` retries transient errors (rate limits,
     brief outages) with a backoff and fails fast on everything else. No network,
     no spend.
  2. Live smoke test — calls the first model of each provider that has a key set,
     to confirm real calls work. Providers without a key are skipped (stays free
     with just Groq/Gemini).

Run with:  python test_providers.py
"""

import sys
import time

import litellm

import providers
from providers import ask, total_cost, is_configured, ProviderError
from config import PROVIDERS, MODELS


# ── Part 1: offline retry behaviour (no network, no spend) ─────────────────────--

class _FakeResp:
    """A minimal stand-in for a litellm response object."""
    choices = [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]
    _hidden_params = {"response_cost": 0.0}


def _err(name):
    """Make an exception whose class NAME is `name` (that's how providers.py
    decides whether an error is retryable)."""
    return type(name, (Exception,), {})("boom")


def _run_retry_tests():
    print("Offline retry tests (no network, free):\n")
    passed = failed = 0

    def check(name, ok):
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}")

    real_completion, real_sleep = litellm.completion, time.sleep
    slept = []
    time.sleep = lambda s: slept.append(s)   # never actually wait during tests
    try:
        # 1. A transient error, then success → it retries and returns the answer.
        calls = {"n": 0}
        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _err("RateLimitError")
            return _FakeResp()
        litellm.completion = flaky
        out = ask("hi", model="groq/llama-3.3-70b-versatile", api_key="x")
        check("retries a transient error, then succeeds",
              out == "ok" and calls["n"] == 2 and len(slept) == 1)

        # 2. A non-retryable error → raises immediately, no retry, no sleep.
        calls = {"n": 0}
        slept.clear()
        def auth_fail(*a, **k):
            calls["n"] += 1
            raise _err("AuthenticationError")
        litellm.completion = auth_fail
        try:
            ask("hi", model="groq/llama-3.3-70b-versatile", api_key="x")
            check("non-retryable error raises immediately", False)
        except ProviderError:
            check("non-retryable error raises immediately",
                  calls["n"] == 1 and len(slept) == 0)

        # 3. A transient error that never clears → retried, then raises ProviderError.
        calls = {"n": 0}
        slept.clear()
        def always(*a, **k):
            calls["n"] += 1
            raise _err("RateLimitError")
        litellm.completion = always
        try:
            ask("hi", model="groq/llama-3.3-70b-versatile", api_key="x")
            check("persistent transient error eventually raises", False)
        except ProviderError:
            expected = 1 + len(providers._RETRY_BACKOFF)   # initial try + retries
            check("persistent transient error eventually raises", calls["n"] == expected)
    finally:
        litellm.completion, time.sleep = real_completion, real_sleep

    print(f"\n  ({passed} passed, {failed} failed)\n")
    return failed == 0


# ── Part 2: live smoke test (uses keys; skips providers without one) ────────────--

def _run_live_smoke():
    question = "In one short sentence, say hello and name which AI model you are."
    print("Live smoke test (first model of each configured provider):\n")
    for provider, cfg in PROVIDERS.items():
        model = MODELS[provider][0]["id"]
        print(f"=== {cfg['label']} ({model}) ===")
        if not is_configured(provider):
            print(f"  ⚠️  Skipped — {cfg['key_env']} is not set in .env\n")
            continue
        try:
            print(f"  ✅ {ask(question, model=model)}\n")
        except Exception as e:
            print(f"  ❌ {e}\n")
    print(f"💸 Total estimated cost this run: ${total_cost():.6f}")


if __name__ == "__main__":
    ok = _run_retry_tests()
    _run_live_smoke()
    sys.exit(0 if ok else 1)
