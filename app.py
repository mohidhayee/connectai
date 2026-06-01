"""
app.py — Streamlit web UI for ConnectAI.

Run with:
    streamlit run app.py

What this gives you:
  - A text box to enter your task
  - Dropdowns to configure each agent (name, provider, role)
  - A "Run" button that kicks off the two-agent collaboration
  - Each agent's turn appears live in the browser as it completes
  - A running cost meter
  - The full scratchpad shown at the bottom
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
    a_name = st.text_input("Name", value="Planner", key="a_name")
    a_provider = st.selectbox("Provider", provider_names, index=0, key="a_provider")
    a_role = st.text_area(
        "Role",
        value=(
            "You are Planner, a strategic thinker. "
            "Break the task into a clear structure: sections, key points, and a logical order. "
            "Be concise. Use bullet points or numbered lists where helpful."
        ),
        height=130,
        key="a_role",
    )

    st.divider()

    st.subheader("Agent B")
    b_name = st.text_input("Name", value="Writer", key="b_name")
    b_default = 1 if len(provider_names) > 1 else 0
    b_provider = st.selectbox("Provider", provider_names, index=b_default, key="b_provider")
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
    )

    st.divider()
    max_turns = st.slider("Max turns", min_value=2, max_value=12, value=6)

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
    cost_display = st.empty()   # updated after each turn

# ── Collaboration loop ─────────────────────────────────────────────────────────
if run_btn and task.strip():
    if a_provider == b_provider:
        st.warning(
            f"Both agents are using **{a_provider}**. "
            "Consider different providers for a true cross-vendor collaboration."
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

        # Build what this agent sees
        if scratchpad:
            user_msg = (
                f"TASK: {task}\n\n"
                f"SCRATCHPAD — work done so far:\n{scratchpad}\n\n"
                "It's your turn. Build on what's there — don't repeat it. "
                "When the task is fully complete, start your reply with DONE."
            )
        else:
            user_msg = (
                f"TASK: {task}\n\n"
                "You're going first. Start working on the task. "
                "When complete, start your reply with DONE."
            )

        with st.status(
            f"Turn {turn}/{max_turns} — **{agent.name}** ({agent.provider}) thinking…",
            expanded=True,
        ) as status:
            try:
                reply = agent.reply(user_msg)
            except ProviderError as e:
                st.error(f"Provider error: {e}")
                break

            st.markdown(reply)
            status.update(
                label=f"Turn {turn}/{max_turns} — {agent.name} ({agent.provider}) ✓",
                state="complete",
                expanded=False,
            )

        scratchpad += f"\n--- {agent.name} (turn {turn}) ---\n{reply}\n"
        cost_display.metric("Cost", f"${total_cost():.4f}")

        if reply.strip().upper().startswith("DONE"):
            st.success(f"✓ {agent.name} signalled the task is complete.")
            break
    else:
        st.info(f"Reached the turn limit ({max_turns} turns).")

    # ── Final output ───────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Final output")
    st.markdown(scratchpad)
    st.metric("Total cost", f"${total_cost():.4f}")
