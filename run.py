"""
run.py — launch a multi-agent collaboration from the command line.

Usage:
    python run.py                            # round-robin, prompts you for a task
    python run.py "explain black holes"      # round-robin on the given task
    python run.py --manager "plan a trip"    # MANAGER MODE on the given task

Two collaboration modes (same team, set below):
  • Round-robin (default) — agents take turns adding to a shared scratchpad.
  • Manager (--manager)   — the FIRST agent is the lead: it delegates subtasks to
    the others and synthesises the final answer. Reliable by design (JSON
    decisions, step + cost caps, always returns a best-effort answer).

Edit the `team` list below to add more agents (2–7) or swap their models. In
manager mode the first agent is the lead; the rest are workers.
"""

import sys

import providers
from agent import Agent
from orchestrator import run as orchestrate
from manager import run_manager
from config import DEFAULT_MODEL_A, DEFAULT_MODEL_B


# ── The team ───────────────────────────────────────────────────────────────────
# Add up to 7 agents here. Give each a different model to combine their strengths.
# In --manager mode, the FIRST agent is the lead (its role text is replaced by
# manager instructions; its model still matters), and the rest are workers.
team = [
    Agent(
        name="Planner",
        model=DEFAULT_MODEL_A,
        role=(
            "You are Planner, a strategic thinker and organiser. "
            "Break the given task into a clear structure: sections, key points, "
            "and a logical order. Be concise. Use bullet points or numbered lists."
        ),
    ),
    Agent(
        name="Writer",
        model=DEFAULT_MODEL_B,
        role=(
            "You are Writer, a clear and engaging communicator. "
            "Take the structure in the scratchpad and turn it into well-written, "
            "detailed content. Build on what's there — never repeat it. "
            "When the result is complete and polished, signal that it's done."
        ),
    ),
]


def _run_manager_cli(team, task):
    """Run Manager Mode and print the decision timeline to the console."""
    manager, workers = team[0], team[1:]
    bar = "=" * 62
    print(f"\n{bar}\nMANAGER MODE")
    print(f"LEAD    : {manager.name} ({manager.provider})")
    print("WORKERS : " + ", ".join(f"{w.name} ({w.provider})" for w in workers))
    print(f"TASK    : {task}\n{bar}")

    for ev in run_manager(manager, workers, task):
        t = ev["type"]
        if t == "manager_decision":
            d = ev["decision"]
            if d is None:
                print(f"\n[step {ev['step']}] {manager.name}: no valid decision "
                      f"({ev['error']}) — will synthesise.")
            elif d["action"] == "delegate":
                print(f"\n[step {ev['step']}] {manager.name} → delegates to {d['to']}")
                print(f"    instruction: {d['instruction']}")
                if d.get("reason"):
                    print(f"    reason: {d['reason']}")
            else:
                print(f"\n[step {ev['step']}] {manager.name} → finish")
        elif t == "worker_result":
            if ev["error"]:
                print(f"    ⚠ {ev['worker']} failed: {ev['error']}")
            else:
                preview = ev["output"][:220] + ("…" if len(ev["output"]) > 220 else "")
                print(f"    {ev['worker']} → {preview}")
        elif t == "critique":
            print(f"    🔎 quality check [{'OK' if ev['accept'] else 'NEEDS WORK'}]: "
                  f"{ev['feedback']}")
        elif t == "guardrail":
            print(f"    ⛔ guardrail [{ev['name']}]: {ev['detail']}")
        elif t == "synthesis":
            print(f"\n  …synthesising a best-effort answer (reason: {ev['reason']})")
        elif t == "final":
            print(f"\n{bar}\nFINAL ANSWER  (reason: {ev['finish_reason']}, "
                  f"steps: {ev['steps']}, cost: ${ev['cost']:.4f})\n{bar}")
            print(ev["answer"])

    print(f"\n{bar}\nTOTAL COST: ${providers.total_cost():.4f}\n{bar}")


def main():
    args = sys.argv[1:]

    # Tiny flag parse: --manager, or --mode manager / --mode round-robin.
    manager_mode = False
    if "--manager" in args:
        manager_mode = True
        args.remove("--manager")
    if "--mode" in args:
        i = args.index("--mode")
        if i + 1 < len(args):
            manager_mode = args[i + 1].lower().startswith("man")
            del args[i:i + 2]

    task = " ".join(args).strip()
    if not task:
        task = input("What should the agents work on?\n> ").strip()
        if not task:
            task = "Write a short beginner's guide to staying focused while studying"

    if manager_mode:
        _run_manager_cli(team, task)
    else:
        final_scratchpad = orchestrate(team, task, max_turns=6)
        print("\n\nFINAL OUTPUT (full scratchpad):")
        print("=" * 62)
        print(final_scratchpad)


if __name__ == "__main__":
    main()
