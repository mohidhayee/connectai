"""
test_app.py — Streamlit UI smoke tests for app.py (both collaboration modes).

Run with:  python test_app.py

These use Streamlit's AppTest to actually execute app.py and drive the widgets,
but they run OFFLINE and FREE: we swap in a fake model caller (no network), so the
test exercises the real UI wiring — Team-tab mode switch, Lead picker, the Run-tab
round-robin loop, and the Manager-mode timeline — without spending anything.

We assert the page renders with no exception and that the expected output and
metrics appear, in both Round-robin and Manager modes.
"""

import json
import sys

import providers
import agent
from streamlit.testing.v1 import AppTest

# ── A fake model caller (no network) ────────────────────────────────────────────

def make_fake_ask(worker_name="Writer"):
    """Returns an ask() stand-in. It tells the call types apart by the prompt:
    manager decision / synthesis / critic (by system text) vs round-robin replies
    (agent.reply passes messages=, no system) vs worker calls."""
    state = {"mgr": 0}

    def fake(prompt=None, *, model, system=None, messages=None, api_key=None):
        if system and "LEAD of a small AI team" in system:
            state["mgr"] += 1
            if state["mgr"] == 1:                       # first: delegate once
                return json.dumps({"action": "delegate", "to": worker_name,
                                   "instruction": "Write a tiny bit", "reason": "fit"})
            return json.dumps({"action": "finish",       # then: finish
                               "final_answer": "FINAL MANAGER ANSWER"})
        if system and "delivering the FINAL answer" in system:
            return "SYNTHESISED ANSWER"
        if system and "quality checker" in system:
            return '{"accept": true, "feedback": "ok"}'
        if messages is not None and system is None:      # round-robin agent.reply
            return "Round-robin reply text."
        return "Worker output text."                     # a worker subtask

    return fake


def install_fakes(worker_name="Writer"):
    """Patch every place a model could be called, with a fresh fake each test."""
    fake = make_fake_ask(worker_name)
    providers.ask = fake            # manager + workers (manager.py uses providers.ask)
    providers.total_cost = lambda: 0.0
    providers.reset_cost = lambda: None
    agent.ask = fake               # round-robin (agent.py bound `ask` at import)


# ── Shared AppTest setup ────────────────────────────────────────────────────────

def _two_groq_agents():
    """Two agents on a free Groq model (so no key/provider blocks the run)."""
    return [
        {"id": 0, "name": "Planner", "model": "groq/llama-3.3-70b-versatile",
         "custom_model": "", "custom_key": "", "role": "You are Planner."},
        {"id": 1, "name": "Writer", "model": "groq/llama-3.3-70b-versatile",
         "custom_model": "", "custom_key": "", "role": "You are Writer."},
    ]


def _new_app(mode, task="Write a haiku about studying."):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["key_groq"] = "x"          # satisfy provider_ready("groq")
    at.session_state["agents"] = _two_groq_agents()
    at.session_state["next_id"] = 2
    at.session_state["mode_choice"] = mode
    if mode == "Manager":
        at.session_state["lead_choice"] = 0     # Planner leads; Writer is the worker
    at.session_state["task"] = task
    return at


def _click_run(at):
    run_btn = next(b for b in at.button if "Run collaboration" in b.label)
    run_btn.click().run()


def _all_markdown(at):
    return "\n".join(m.value for m in at.markdown)


# ── Tiny harness (matches test_manager.py style) ───────────────────────────────--
_passed = _failed = 0


def check(name, fn):
    global _passed, _failed
    try:
        fn()
    except AssertionError as e:
        _failed += 1
        print(f"  ❌ {name} — {e}")
    except Exception as e:
        _failed += 1
        print(f"  ❌ {name} — unexpected {type(e).__name__}: {e}")
    else:
        _passed += 1
        print(f"  ✅ {name}")


# ── Tests ───────────────────────────────────────────────────────────────────────

def test_round_robin():
    print("\nROUND-ROBIN mode (must keep working):")

    def runs_clean():
        install_fakes()
        at = _new_app("Round-robin")
        at.run()
        _click_run(at)
        assert not at.exception, at.exception
        assert "Round-robin reply text." in _all_markdown(at), "no round-robin output rendered"
        assert any("Final result" in m.value for m in at.markdown) \
            or any(m.value == "📄 Final result" for m in at.subheader), "no final result"
        assert len(at.metric) > 0, "no metrics rendered"
    check("round-robin renders turns, final result, and metrics, no exception", runs_clean)


def test_manager_mode():
    print("\nMANAGER mode (the new feature):")

    def runs_clean():
        install_fakes("Writer")
        at = _new_app("Manager")
        at.run()
        # The Lead picker should appear in Manager mode.
        assert any("Lead" in (s.label or "") for s in at.selectbox), "no Lead picker shown"
        _click_run(at)
        assert not at.exception, at.exception
        md = _all_markdown(at)
        assert "FINAL MANAGER ANSWER" in md, "manager's final answer not rendered"
        assert "Delegates to Writer" in md, "delegation not shown in the timeline"
        assert "Worker output text." in md, "worker reply not shown in the timeline"
        assert len(at.metric) > 0, "no steps/cost metrics rendered"
    check("manager timeline shows delegation, worker reply, final answer, metrics", runs_clean)

    def lead_picker_switches_workers():
        # With Writer as lead, the worker becomes Planner; delegate must target it.
        install_fakes("Planner")
        at = _new_app("Manager")
        at.session_state["lead_choice"] = 1     # Writer leads now
        at.run()
        _click_run(at)
        assert not at.exception, at.exception
        md = _all_markdown(at)
        assert "Delegates to Planner" in md, "lead change didn't reassign the worker"
    check("changing the Lead reassigns who the workers are", lead_picker_switches_workers)


def main():
    print("=" * 62)
    print("ConnectAI UI tests (AppTest, offline + free)")
    print("=" * 62)

    test_round_robin()
    test_manager_mode()

    print("\n" + "=" * 62)
    total = _passed + _failed
    print(f"RESULT: {_passed}/{total} checks passed.")
    print("=" * 62)
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
