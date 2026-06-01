"""
run.py — launch a multi-agent collaboration from the command line.

Usage:
    python run.py                            # prompts you interactively
    python run.py "explain black holes"      # pass the task directly

The default team is two agents from different providers:
  Planner  (Groq llama)  — breaks the problem into structure
  Writer   (Gemini)      — fills in the detail and polishes the writing

Edit the `team` list below to add more agents (2–4) or swap their models.
"""

import sys
from agent import Agent
from orchestrator import run as orchestrate
from config import DEFAULT_MODEL_A, DEFAULT_MODEL_B


# ── The team ───────────────────────────────────────────────────────────────────
# Add up to 4 agents here. Give each a different model to combine their strengths.
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


def main():
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = input("What should the agents work on?\n> ").strip()
        if not task:
            task = "Write a short beginner's guide to staying focused while studying"

    final_scratchpad = orchestrate(team, task, max_turns=6)

    print("\n\nFINAL OUTPUT (full scratchpad):")
    print("=" * 62)
    print(final_scratchpad)


if __name__ == "__main__":
    main()
