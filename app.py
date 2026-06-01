"""
app.py — Streamlit web UI for ConnectAI.

Run with:
    streamlit run app.py
"""

import streamlit as st
from agent import Agent
from providers import reset_cost, total_cost, ProviderError
from config import PROVIDERS

st.set_page_config(page_title="ConnectAI", page_icon="🤝", layout="centered")

st.title("🤝 ConnectAI")
st.caption("Two AI agents from different providers, collaborating on your task.")

# ── Sidebar: configure the two agents ─────────────────────────────────────────
provider_names = list(PROVIDERS.keys())

with st.sidebar:
    st.header("Configure agents")

    st.subheader("Agent A  (goes first)")
    a_name = st.text_input(
        "Name",
        value="Planner",
        key="a_name",
        help="The display name shown in the transcript. Pick anything you like.",
    )
    a_provider = st.selectbox(
        "Provider",
        provider_names,
        index=0,
        key="a_provider",
        format_func=str.title,
        help="Which AI service powers this agent. Groq is free; Gemini needs billing.",
    )
    a_role = st.text_area(
        "Role",
        value=(
            "You are Planner, a strategic thinker. "
            "Break the task into a clear structure: sections, key points, and a logical order. "
            "Be concise. Use bullet points or numbered lists where helpful."
        ),
        height=130,
        key="a_role",
        help="The system prompt — the instructions that tell this agent who it is and how to behave.",
    )

    st.divider()

    st.subheader("Agent B")
    b_name = st.text_input(
        "Name",
        value="Writer",
        key="b_name",
        help="The display name shown in the transcript.",
    )
    b_default = 1 if len(provider_names) > 1 else 0
    b_provider = st.selectbox(
        "Provider",
        provider_names,
        index=b_default,
        key="b_provider",
        format_func=str.title,
        help="Which AI service powers this agent. Use a different provider from Agent A for true cross-vendor collaboration.",
    )
    b_role = st.text_area(
        "Role",
        value=(
            "You are Writer, a clear and engaging communicator. "
            "Take the Planner's structure and turn it into well-written, detailed content. "
            "Build on what's already in the scratchpad — never repeat what's there. "
            "When the task is fully complete, signal DONE."
        ),
        height=130,
        key="b_role",
        help="The system prompt — the instructions that tell this agent who it is and how to behave.",
    )

    st.divider()
    max_turns = st.slider(
        "Max turns",
        min_value=2,
        max_value=12,
        value=6,
        help=(
            "The maximum number of replies across both agents combined. "
            "Each time an agent responds, that's 1 turn. "
            "6 turns = up to 3 replies each. "
            "The run stops early if an agent signals the task is done."
        ),
    )

# ── Main: task input + run button ─────────────────────────────────────────────
task = st.text_area(
    "What should the agents work on?",
    placeholder="e.g.  Write a short guide to staying focused while studying",
    height=110,
)

col_btn, col_cost = st.columns([2, 1])
with col_btn:
    run_btn = st.button("▶  Run", type="primary", use_container_width=True,
                        disabled=not task.strip())
with col_cost:
    cost_display = st.empty()

# ── Collaboration loop ─────────────────────────────────────────────────────────
if run_btn and task.strip():
    if a_provider == b_provider:
        st.warning(
            f"Both agents are using **{a_provider.title()}**. "
            "For true cross-vendor collaboration, pick different providers."
        )

    reset_cost()
    agent_a = Agent(name=a_name, provider=a_provider, role=a_role)
    agent_b = Agent(name=b_name, provider=b_provider, role=b_role)
    agents = [agent_a, agent_b]
    scratchpad = ""

    cost_display.metric("Cost", "$0.0000")
    st.divider()

    for turn in range(1, max_turns + 1):
        agent = agents[(turn - 1) % 2]

        # Only Agent B (even turns) can signal DONE.
        # Agent A always hands off — prevents Groq from finishing the whole
        # task solo on turn 1 and never involving Gemini.
        can_stop = (turn % 2 == 0)

        if scratchpad:
            user_msg = (
                f"TASK: {task}\n\n"
                f"SCRATCHPAD — work done so far:\n{scratchpad}\n\n"
                "It's your turn. Build on what's there — don't repeat it. "
            )
        else:
            user_msg = (
                f"TASK: {task}\n\n"
                "You're going first. Write your contribution — "
                "your collaborator will build on it next. "
            )

        if can_stop:
            user_msg += (
                "When the task is fully complete, start your reply with DONE."
            )
        else:
            user_msg += "Write your contribution, then your collaborator will continue."

        done_this_turn = False

        with st.status(
            f"Turn {turn}/{max_turns} — **{agent.name}** ({agent.provider.title()}) thinking…",
            expanded=True,
        ) as status:
            try:
                reply = agent.reply(user_msg)
            except ProviderError as e:
                st.error(f"Provider error: {e}")
                break

            # Strip the DONE signal word from the display — it's a control word,
            # not part of the actual content.
            display_reply = reply
            if reply.strip().upper().startswith("DONE"):
                done_this_turn = True
                parts = reply.strip().split("\n", 1)
                display_reply = parts[1].strip() if len(parts) > 1 else ""

            if display_reply:
                st.markdown(display_reply)

            status.update(
                label=f"Turn {turn}/{max_turns} — {agent.name} ({agent.provider.title()}) ✓",
                state="complete",
                expanded=True,   # stay open so the user can read the output
            )

        # Store clean content (without DONE) in the scratchpad
        scratchpad += f"\n--- {agent.name} (turn {turn}) ---\n{display_reply}\n"
        cost_display.metric("Cost", f"${total_cost():.4f}")

        if done_this_turn:
            st.success(f"✓ {agent.name} signalled the task is complete.")
            break
    else:
        st.info(f"Reached the turn limit ({max_turns} turns).")

    # ── Final output ───────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Final output")
    st.markdown(scratchpad)
    st.metric("Total cost", f"${total_cost():.4f}")
