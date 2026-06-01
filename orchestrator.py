"""
orchestrator.py — drives two agents on a shared task.

How it works:
  1. Agent A gets the task and writes the first contribution.
  2. Agent B sees the task + everything written so far, then contributes.
  3. They keep alternating until one says DONE or the turn limit is reached.

Everything each agent writes is added to a shared "scratchpad" — a
running text document that both agents read and add to, like a shared
Google Doc. This is how they collaborate without talking directly.
"""

import providers

# An agent ends the session early by starting their reply with this word.
_DONE_SIGNAL = "DONE"


def run(agent_a, agent_b, task, max_turns=8):
    """Run two agents on a task and return the final scratchpad.

    Args:
        agent_a, agent_b:  Agent instances — should use different providers.
        task:              Plain-text description of what to accomplish.
        max_turns:         Hard cap on total turns (each agent reply = 1 turn).

    Returns:
        The final scratchpad as a string.
    """
    scratchpad = ""
    agents = [agent_a, agent_b]

    _print_header(task, agent_a, agent_b, max_turns)

    for turn in range(1, max_turns + 1):
        agent = agents[(turn - 1) % 2]  # agent_a on odd turns, agent_b on even

        user_msg = _build_prompt(task, scratchpad, turn)

        print(
            f"\n[Turn {turn}/{max_turns}]  {agent.name} ({agent.provider})"
            f"  |  cost so far: ${providers.total_cost():.4f}"
        )

        reply = agent.reply(user_msg)

        # Show a short preview (first 160 chars) so the terminal doesn't flood.
        preview = reply[:160] + ("…" if len(reply) > 160 else "")
        print(f"  → {preview}")

        scratchpad += f"\n--- {agent.name} (turn {turn}) ---\n{reply}\n"

        if reply.strip().upper().startswith(_DONE_SIGNAL):
            print(f"\n  ✓ {agent.name} signalled DONE.")
            break
    else:
        print(f"\n  ⚠  Turn limit reached ({max_turns} turns).")

    _print_footer()
    return scratchpad


# ── helpers ────────────────────────────────────────────────────────────────────

def _build_prompt(task, scratchpad, turn):
    """Build the user message the current agent receives."""
    if scratchpad:
        return (
            f"TASK: {task}\n\n"
            f"SCRATCHPAD — work done so far:\n{scratchpad}\n\n"
            "It's your turn. Read the scratchpad, then continue the work. "
            "Build on what's already there — don't repeat it. "
            "When the task is fully complete, start your reply with the single word DONE "
            "(on its own line, in capitals)."
        )
    else:
        return (
            f"TASK: {task}\n\n"
            "You're going first. Start working on the task. "
            "When the task is fully complete, start your reply with the single word DONE "
            "(on its own line, in capitals)."
        )


def _print_header(task, agent_a, agent_b, max_turns):
    print(f"\n{'='*62}")
    print(f"TASK : {task}")
    print(f"AGENTS: {agent_a.name} ({agent_a.provider})  ↔  {agent_b.name} ({agent_b.provider})")
    print(f"MAX TURNS: {max_turns}")
    print('='*62)


def _print_footer():
    print(f"\n{'='*62}")
    print(f"TOTAL COST: ${providers.total_cost():.4f}")
    print('='*62)
