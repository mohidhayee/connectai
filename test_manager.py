"""
test_manager.py — tests for Manager Mode (manager.py).

Run with:  python test_manager.py

This repo keeps tests as plain runnable scripts (like test_providers.py), so this
file uses a tiny home-grown harness — no pytest needed. It prints a ✅/❌ per
check and exits non-zero if anything fails.

STEP 1 covers the linchpin: the decision parser. These tests are 100% offline and
free (no model calls) because parsing is pure logic. We deliberately throw the
messy, malformed things a real model might say at the parser and prove it either
(a) recovers a valid decision from the mess, or (b) raises a clean
DecisionParseError — never an unexpected crash that would derail the control loop.
"""

import sys

from manager import parse_decision, DecisionParseError

# ── Tiny test harness ─────────────────────────────────────────────────────────--
_passed = 0
_failed = 0


def check(name, fn):
    """Run one check; record and print pass/fail. Never stops the whole run."""
    global _passed, _failed
    try:
        fn()
    except AssertionError as e:
        _failed += 1
        print(f"  ❌ {name} — {e}")
    except Exception as e:  # an unexpected crash is itself a failure
        _failed += 1
        print(f"  ❌ {name} — unexpected {type(e).__name__}: {e}")
    else:
        _passed += 1
        print(f"  ✅ {name}")


def expect_error(raw, **kwargs):
    """Assert that parsing `raw` raises DecisionParseError (a clean rejection),
    not some other exception and not a silent success."""
    try:
        parse_decision(raw, **kwargs)
    except DecisionParseError:
        return  # exactly what we want
    except Exception as e:
        raise AssertionError(f"raised {type(e).__name__} instead of DecisionParseError: {e}")
    raise AssertionError("parsing succeeded, but we expected DecisionParseError")


# ── VALID inputs: the parser should recover a correct decision ─────────────────--

def test_valid_inputs():
    print("\nVALID inputs (parser should recover a clean decision):")

    def plain_finish():
        d = parse_decision('{"action": "finish", "final_answer": "All done."}')
        assert d == {"action": "finish", "final_answer": "All done."}, d
    check("plain finish JSON", plain_finish)

    def plain_delegate():
        d = parse_decision(
            '{"action": "delegate", "to": "Writer", '
            '"instruction": "Draft the intro", "reason": "needs prose"}'
        )
        assert d["action"] == "delegate", d
        assert d["to"] == "Writer", d
        assert d["instruction"] == "Draft the intro", d
        assert d["reason"] == "needs prose", d
    check("plain delegate JSON", plain_delegate)

    def worker_name_normalised():
        # Model wrote "writer" (lowercase); we should normalise to "Writer".
        d = parse_decision(
            '{"action": "delegate", "to": "writer", "instruction": "x"}',
            valid_workers=["Writer", "Researcher"],
        )
        assert d["to"] == "Writer", d
    check("worker name matched case-insensitively + normalised", worker_name_normalised)

    def json_fence():
        raw = '```json\n{"action": "finish", "final_answer": "Hi"}\n```'
        d = parse_decision(raw)
        assert d == {"action": "finish", "final_answer": "Hi"}, d
    check("JSON wrapped in ```json fence", json_fence)

    def bare_fence():
        raw = '```\n{"action": "finish", "final_answer": "Hi"}\n```'
        d = parse_decision(raw)
        assert d["final_answer"] == "Hi", d
    check("JSON wrapped in a bare ``` fence", bare_fence)

    def leading_prose():
        raw = 'Sure! Here is my decision: {"action": "finish", "final_answer": "Hi"}'
        d = parse_decision(raw)
        assert d["final_answer"] == "Hi", d
    check("JSON with leading prose", leading_prose)

    def trailing_prose():
        raw = '{"action": "finish", "final_answer": "Hi"}  Hope that helps!'
        d = parse_decision(raw)
        assert d["final_answer"] == "Hi", d
    check("JSON with trailing prose", trailing_prose)

    def fence_and_prose():
        raw = "Here you go:\n```json\n{\"action\": \"finish\", \"final_answer\": \"Hi\"}\n```\nThanks!"
        d = parse_decision(raw)
        assert d["final_answer"] == "Hi", d
    check("JSON inside a fence with prose around it", fence_and_prose)

    def reason_optional():
        d = parse_decision(
            '{"action": "delegate", "to": "Writer", "instruction": "x"}',
            valid_workers=["Writer"],
        )
        assert d["reason"] == "", d  # missing reason → empty string, not a crash
    check("delegate without optional 'reason' defaults to ''", reason_optional)

    def whitespace_trimmed():
        d = parse_decision('{"action": "finish", "final_answer": "  spaced out  "}')
        assert d["final_answer"] == "spaced out", d
    check("final_answer is whitespace-trimmed", whitespace_trimmed)


# ── MALFORMED inputs: the parser should reject cleanly (DecisionParseError) ─────--

def test_malformed_inputs():
    print("\nMALFORMED inputs (parser should reject cleanly, never crash):")

    check("empty string", lambda: expect_error(""))
    check("whitespace only", lambda: expect_error("   \n  "))
    check("no JSON at all", lambda: expect_error("I think Writer should do it."))
    check("truncated JSON (no closing brace)",
          lambda: expect_error('{"action": "delegate", "to": "Writer"'))
    check("missing 'action' key", lambda: expect_error('{"foo": 1}'))
    check("unknown action value", lambda: expect_error('{"action": "dance"}'))
    check("finish without final_answer",
          lambda: expect_error('{"action": "finish"}'))
    check("finish with empty final_answer",
          lambda: expect_error('{"action": "finish", "final_answer": "   "}'))
    check("delegate without 'to'",
          lambda: expect_error('{"action": "delegate", "instruction": "x"}'))
    check("delegate without 'instruction'",
          lambda: expect_error('{"action": "delegate", "to": "Writer"}'))
    check("delegate with empty instruction",
          lambda: expect_error('{"action": "delegate", "to": "Writer", "instruction": ""}'))
    check("delegate to an unknown worker",
          lambda: expect_error(
              '{"action": "delegate", "to": "Ghost", "instruction": "x"}',
              valid_workers=["Writer", "Researcher"]))
    check("JSON is a list, not an object", lambda: expect_error("[1, 2, 3]"))
    check("JSON is a bare string", lambda: expect_error('"just a string"'))
    # Single quotes aren't valid JSON. We DON'T try to "fix" them (that would
    # corrupt apostrophes inside the content); the loop just retries instead.
    check("single-quoted pseudo-JSON is rejected",
          lambda: expect_error("{'action': 'finish', 'final_answer': 'hi'}"))


# ── Run everything ──────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("Manager Mode tests — Step 1: the decision parser")
    print("=" * 62)

    test_valid_inputs()
    test_malformed_inputs()

    print("\n" + "=" * 62)
    total = _passed + _failed
    print(f"RESULT: {_passed}/{total} checks passed.")
    print("=" * 62)

    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
