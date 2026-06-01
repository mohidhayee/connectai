"""
orchestrator.py — drives a team of agents (2–4) on a shared task.

How it works:
  1. Each agent takes a turn in order (round-robin): A, B, C, A, B, C, ...
  2. Every agent sees the task + everything written so far (the scratchpad),
     then adds its own contribution.
  3. They keep going until an agent signals DONE or the turn limit is reached.

The "scratchpad" is a running text document the whole team reads and adds to,
like a shared Google Doc. That's how they collaborate without talking directly.

To make sure everyone contributes before the work is closed out, an agent may
only signal DONE at the end of a full round (after every agent has had a turn).
"""

import providers

# An agent ends the session early by starting their reply with this word.
_DONE_SIGNAL = "DONE"


def run(agents, task, max_turns=8):
    """Run a team of agents on a task and return the final scratchpad.

    Args:
        agents:     list of 2–4 Agent instances (ideally different providers).
        task:       plain-text description of what to accomplish.
        max_turns:  hard cap on total turns (each agent reply = 1 turn).

    Returns:
        The final scratchpad as a string.
    """
    n = len(agents)
    scratchpad = ""

    _print_header(agents, task, max_turns)

    for turn in range(1, max_turns + 1):
        agent = agents[(turn - 1) % n]

        # An agent may only finish at the end of a full round, so everyone
        # contributes at least once before the work is closed out.
        can_stop = (turn >= n) and (turn % n == 0)

        user_msg = _build_prompt(agents, agent, task, scratchpad, can_stop)

        print(
            f"\n[Turn {turn}/{max_turns}]  {agent.name} ({agent.provider})"
            f"  |  cost so far: ${providers.total_cost():.4f}"
        )

        reply = agent.reply(user_msg)

        # "DONE" is a control signal, not content — strip it before showing or
        # storing, so it doesn't leak into output or the next agent's view.
        done_this_turn = reply.strip().upper().startswith(_DONE_SIGNAL)
        if done_this_turn:
            parts = reply.strip().split("\n", 1)
            reply = parts[1].strip() if len(parts) > 1 else ""

        preview = reply[:160] + ("…" if len(reply) > 160 else "")
        print(f"  → {preview}")

        scratchpad += f"\n--- {agent.name} (turn {turn}) ---\n{reply}\n"

        if done_this_turn:
            print(f"\n  ✓ {agent.name} signalled DONE.")
            break
    else:
        print(f"\n  ⚠  Turn limit reached ({max_turns} turns).")

    _print_footer()
    return scratchpad


# ── helpers ────────────────────────────────────────────────────────────────────

def _build_prompt(agents, current, task, scratchpad, can_stop):
    """Build the user message the current agent receives."""
    teammates = ", ".join(a.name for a in agents if a is not current)

    if scratchpad:
        msg = (
            f"TASK: {task}\n\n"
            f"Your teammates on this task: {teammates}.\n\n"
            f"SCRATCHPAD — work done so far:\n{scratchpad}\n\n"
            "It's your turn. Read the scratchpad, then continue the work. "
            "Build on what's already there — don't repeat it. "
        )
    else:
        msg = (
            f"TASK: {task}\n\n"
            f"Your teammates on this task: {teammates}.\n\n"
            "You're going first. Write your contribution — "
            "your teammates will build on it next. "
        )

    if can_stop:
        msg += (
            "If the task is now fully complete, start your reply with the single "
            "word DONE (on its own line, in capitals). Otherwise just continue the work."
        )
    else:
        msg += "Write your contribution, then your teammates will continue."

    return msg


def _print_header(agents, task, max_turns):
    team = "  ↔  ".join(f"{a.name} ({a.provider})" for a in agents)
    print(f"\n{'='*62}")
    print(f"TASK : {task}")
    print(f"TEAM : {team}")
    print(f"MAX TURNS: {max_turns}")
    print('='*62)


def _print_footer():
    print(f"\n{'='*62}")
    print(f"TOTAL COST: ${providers.total_cost():.4f}")
    print('='*62)
