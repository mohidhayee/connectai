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

import contextlib
import json
import sys

import providers
from agent import Agent
from manager import parse_decision, DecisionParseError, run_manager_collect

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


# ── A deterministic, offline stand-in for the providers module ─────────────────--
# So the guardrail tests force each failure mode with ZERO network calls and ZERO
# spend. We swap in fake versions of providers.ask and providers.total_cost, then
# script exactly what the "manager" and "workers" say.

class FakeProvider:
    """Scripted replacement for providers.ask / providers.total_cost.

    It tells apart the three kinds of call by the system prompt:
      - manager decision  → system contains "LEAD of a small AI team"
      - final synthesis    → system contains "delivering the FINAL answer"
      - otherwise          → a worker call
    """

    def __init__(self, manager_replies, *, worker_reply="WORKER OUTPUT",
                 synth_reply="SYNTHESISED ANSWER", fail_workers=False,
                 cost_per_call=0.0, start_cost=0.0,
                 critic_reply='{"accept": true, "feedback": "fine"}'):
        # manager_replies may be a list (consumed in order, last repeats) or a
        # callable taking the 1-based call number and returning a reply string.
        self.manager_replies = manager_replies
        self.worker_reply = worker_reply
        self.synth_reply = synth_reply
        self.critic_reply = critic_reply
        self.fail_workers = fail_workers
        self.cost_per_call = cost_per_call
        self.cost = start_cost
        self.calls = {"manager": 0, "worker": 0, "synth": 0, "critic": 0}

    def ask(self, prompt=None, *, model, system=None, messages=None, api_key=None):
        self.cost += self.cost_per_call
        if system and "LEAD of a small AI team" in system:
            self.calls["manager"] += 1
            n = self.calls["manager"]
            if callable(self.manager_replies):
                return self.manager_replies(n)
            seq = self.manager_replies
            return seq[n - 1] if n - 1 < len(seq) else seq[-1]
        if system and "delivering the FINAL answer" in system:
            self.calls["synth"] += 1
            return self.synth_reply
        if system and "quality checker" in system:
            self.calls["critic"] += 1
            return self.critic_reply(prompt) if callable(self.critic_reply) else self.critic_reply
        self.calls["worker"] += 1
        if self.fail_workers:
            raise providers.ProviderError("simulated worker failure")
        return self.worker_reply(prompt) if callable(self.worker_reply) else self.worker_reply

    def total_cost(self):
        return self.cost


@contextlib.contextmanager
def patched(fp):
    """Temporarily route providers.ask / providers.total_cost through the fake."""
    real_ask, real_cost = providers.ask, providers.total_cost
    providers.ask, providers.total_cost = fp.ask, fp.total_cost
    try:
        yield
    finally:
        providers.ask, providers.total_cost = real_ask, real_cost


def _team(worker_names=("Writer",)):
    """A Lead + workers. The model id is irrelevant — providers.ask is faked."""
    model = "groq/llama-3.3-70b-versatile"
    manager = Agent("Lead", model, role="(set by manager mode)")
    workers = [Agent(n, model, role=f"You are {n}. Do your job.") for n in worker_names]
    return manager, workers


def _delegate(to, instruction, reason="needed"):
    return json.dumps({"action": "delegate", "to": to,
                       "instruction": instruction, "reason": reason})


def _finish(answer):
    return json.dumps({"action": "finish", "final_answer": answer})


def _guardrail_names(events):
    return [e["name"] for e in events if e["type"] == "guardrail"]


def _final(events):
    return next((e for e in reversed(events) if e["type"] == "final"), None)


# ── GUARDRAILS: force each failure mode and prove graceful termination ─────────--

def test_guardrails():
    print("\nGUARDRAILS (each failure mode forced on purpose; offline + free):")

    def assert_answered(events, why):
        """The universal guarantee: a run ALWAYS ends with a non-empty answer."""
        f = _final(events)
        assert f is not None, f"{why}: no final event"
        assert isinstance(f["answer"], str) and f["answer"].strip(), f"{why}: empty answer"
        return f

    # (a) Infinite delegation is stopped by the step cap (then we still answer).
    def step_cap():
        manager, workers = _team(["Writer"])
        fp = FakeProvider(lambda n: _delegate("Writer", f"do part {n}"))
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task",
                                            max_steps=3, max_calls_per_worker=99,
                                            stall_limit=99)
        f = assert_answered(events, "step_cap")
        assert f["finish_reason"] == "max_steps", f["finish_reason"]
        assert f["steps"] == 3, f["steps"]
        assert fp.calls["worker"] == 3, fp.calls
        assert f["answer"] == "SYNTHESISED ANSWER", f["answer"]
    check("infinite delegation → stopped by step cap, still answers", step_cap)

    # (b) Always-malformed Manager JSON → retries exhausted → graceful synth.
    def parse_failures():
        manager, workers = _team(["Writer"])
        fp = FakeProvider(lambda n: "this is not json at all")
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task", max_retries=3)
        f = assert_answered(events, "parse_failures")
        assert f["finish_reason"] == "parse_failures", f["finish_reason"]
        assert f["steps"] == 1, f["steps"]
        assert fp.calls["manager"] == 3, fp.calls   # retried exactly max_retries
        dec = next(e for e in events if e["type"] == "manager_decision")
        assert dec["attempts"] == 3 and dec["decision"] is None, dec
    check("always-malformed JSON → retries exhausted → graceful answer", parse_failures)

    # (c) A worker crash is captured; the loop survives and the Manager finishes.
    def worker_error():
        manager, workers = _team(["Writer"])
        fp = FakeProvider([_delegate("Writer", "do x"), _finish("FINAL FROM MANAGER")],
                          fail_workers=True)
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task")
        f = assert_answered(events, "worker_error")
        wr = next(e for e in events if e["type"] == "worker_result")
        assert wr["error"], "worker error not recorded"
        assert wr["output"] == "", wr["output"]
        assert f["answer"] == "FINAL FROM MANAGER", f["answer"]
        assert f["finish_reason"] == "manager_finished", f["finish_reason"]
    check("worker crash → captured, loop survives, Manager still finishes", worker_error)

    # (d) Repeating the same subtask is caught as no-progress and stops.
    def duplicate_stall():
        manager, workers = _team(["Writer"])
        fp = FakeProvider(lambda n: _delegate("Writer", "same exact task"))
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task", max_steps=10,
                                            stall_limit=2, max_calls_per_worker=10)
        f = assert_answered(events, "duplicate_stall")
        assert f["finish_reason"] == "stalled", f["finish_reason"]
        assert "duplicate" in _guardrail_names(events), _guardrail_names(events)
        assert fp.calls["worker"] == 1, fp.calls    # only the first one ran
    check("duplicate subtask → no-progress stall → graceful answer", duplicate_stall)

    # (e) Hammering one worker is capped.
    def worker_cap():
        manager, workers = _team(["Writer", "Reader"])
        fp = FakeProvider(lambda n: _delegate("Writer", f"unique {n}"))
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task", max_steps=10,
                                            max_calls_per_worker=2, stall_limit=2)
        assert_answered(events, "worker_cap")
        assert "worker_cap" in _guardrail_names(events), _guardrail_names(events)
        assert fp.calls["worker"] == 2, fp.calls    # capped at 2 real calls
    check("per-worker cap → lead can't hammer one worker, still answers", worker_cap)

    # (f) Cost cap already exceeded before we start → stop immediately, no calls.
    def cost_cap_upfront():
        manager, workers = _team(["Writer"])
        fp = FakeProvider(lambda n: _delegate("Writer", "x"), start_cost=1.0)
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task", max_cost_usd=0.10)
        f = assert_answered(events, "cost_cap_upfront")
        assert f["finish_reason"] == "cost_cap", f["finish_reason"]
        assert fp.calls["manager"] == 0 and fp.calls["synth"] == 0, fp.calls
        assert "cost_cap" in _guardrail_names(events), _guardrail_names(events)
    check("cost cap (already over) → stop before spending, still answers", cost_cap_upfront)

    # (g) Cost cap crossed mid-run → stop, assemble from work done, NO paid synth.
    def cost_cap_midrun():
        manager, workers = _team(["Writer"])
        fp = FakeProvider(lambda n: _delegate("Writer", f"part {n}"),
                          worker_reply="WORKER SAYS HELLO", cost_per_call=0.06)
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task", max_cost_usd=0.10)
        f = assert_answered(events, "cost_cap_midrun")
        assert f["finish_reason"] == "cost_cap", f["finish_reason"]
        assert "WORKER SAYS HELLO" in f["answer"], f["answer"]   # built from transcript
        assert fp.calls["synth"] == 0, "made a paid synth call while over budget!"
        assert fp.calls["worker"] == 1, fp.calls
    check("cost cap (mid-run) → stop, assemble from work, no extra paid call", cost_cap_midrun)


# ── OPTIONAL CRITIC: one bounded pass, default off, fails open ─────────────────--

def test_critic():
    print("\nOPTIONAL CRITIC (one bounded pass; default off; fails open):")

    def critic_off():
        manager, workers = _team(["Writer"])
        fp = FakeProvider([_delegate("Writer", "do x"), _finish("DONE")])
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task")
        assert fp.calls["critic"] == 0, fp.calls
        assert not any(e["type"] == "critique" for e in events)
    check("critic off by default → no quality-check call", critic_off)

    def critic_on():
        manager, workers = _team(["Writer"])
        fp = FakeProvider([_delegate("Writer", "do x"), _finish("DONE")],
                          critic_reply='{"accept": false, "feedback": "needs citations"}')
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task", use_critic=True)
        assert fp.calls["critic"] == 1, fp.calls
        crit = next((e for e in events if e["type"] == "critique"), None)
        assert crit is not None, "no critique event emitted"
        assert crit["accept"] is False and crit["feedback"] == "needs citations", crit
        assert _final(events)["answer"] == "DONE"
    check("critic on → one verdict per output, fed back, run still finishes", critic_on)

    def critic_fails_open():
        manager, workers = _team(["Writer"])
        fp = FakeProvider([_delegate("Writer", "do x"), _finish("DONE")],
                          critic_reply="totally not json")
        with patched(fp):
            _, events = run_manager_collect(manager, workers, "task", use_critic=True)
        crit = next((e for e in events if e["type"] == "critique"), None)
        assert crit is not None and crit["accept"] is True, crit   # failed open
        assert _final(events)["answer"] == "DONE"
    check("malformed critic verdict → fails open (accept), run unaffected", critic_fails_open)


# ── Run everything ──────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("Manager Mode tests — parser + loop guardrails (all offline)")
    print("=" * 62)

    test_valid_inputs()
    test_malformed_inputs()
    test_guardrails()
    test_critic()

    print("\n" + "=" * 62)
    total = _passed + _failed
    print(f"RESULT: {_passed}/{total} checks passed.")
    print("=" * 62)

    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
