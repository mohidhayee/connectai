"""
run.py — launch a two-agent collaboration from the command line.

Usage:
    python run.py                            # prompts you interactively
    python run.py "explain black holes"      # pass the task directly

The two agents are:
  Planner  (groq/llama)  — breaks the problem into structure
  Writer   (gemini)      — fills in the detail and polishes the writing
"""

import sys
from agent import Agent
from orchestrator import run as orchestrate


# ── Agent definitions ──────────────────────────────────────────────────────────
# Change the roles here to change how each agent behaves.

planner = Agent(
    name="Planner",
    provider="groq",
    role=(
        "You are Planner, a strategic thinker and organiser. "
        "Your job is to break the given task into a clear structure: "
        "sections, key points, and a logical order. "
        "Be concise. Use bullet points or numbered lists where helpful. "
        "When reviewing the scratchpad, check that the structure is solid "
        "and suggest any missing pieces."
    ),
)

writer = Agent(
    name="Writer",
    provider="gemini",
    role=(
        "You are Writer, a clear and engaging communicator. "
        "Your job is to take the Planner's structure and turn it into "
        "well-written, detailed content. "
        "Always build on what's already in the scratchpad — never repeat "
        "what's already there. "
        "When the scratchpad contains a complete, polished result, "
        "signal that the task is done."
    ),
)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = input("What should the agents work on?\n> ").strip()
        if not task:
            task = "Write a short beginner's guide to staying focused while studying"

    final_scratchpad = orchestrate(planner, writer, task, max_turns=6)

    print("\n\nFINAL OUTPUT (full scratchpad):")
    print("=" * 62)
    print(final_scratchpad)


if __name__ == "__main__":
    main()
