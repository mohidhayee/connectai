"""
app.py — Streamlit web UI for ConnectAI.

Run with:
    streamlit run app.py

Three tabs:
  ▶️ Run       — write the task, run the team, watch them collaborate
  👥 Team      — configure your 2–4 agents (name, model, role)
  🔑 API keys  — paste your own keys (kept in this session only)
"""

import streamlit as st

from agent import Agent
from orchestrator import _build_prompt, _DONE_SIGNAL
from providers import (
    reset_cost, total_cost, is_configured, provider_for, ProviderError,
)
from config import (
    PROVIDERS, all_models, find_model,
    DEFAULT_MODEL_A, DEFAULT_MODEL_B,
)

CUSTOM = "__custom__"  # sentinel for "type your own model id"
MIN_AGENTS, MAX_AGENTS = 2, 4

DEFAULT_ROLE_A = (
    "You are Planner, a strategic thinker. "
    "Break the task into a clear structure: sections, key points, and a logical order. "
    "Be concise. Use bullet points or numbered lists where helpful."
)
DEFAULT_ROLE_B = (
    "You are Writer, a clear and engaging communicator. "
    "Take the structure in the scratchpad and turn it into well-written, detailed content. "
    "Build on what's already there — never repeat it. "
    "When the result is complete and polished, signal that it's done."
)

st.set_page_config(page_title="ConnectAI", page_icon="🤝", layout="wide")

# ── Helpers ───────────────────────────────────────────────────────────────────

def session_key(provider):
    """The key the user typed this session for a provider, or None."""
    return st.session_state.get(f"key_{provider}") or None


def provider_ready(provider):
    """True if we have a key for this provider — from the session or from .env."""
    return bool(session_key(provider)) or is_configured(provider)


def pmeta(provider):
    return PROVIDERS.get(provider, {"label": provider.title(), "emoji": "•", "tier": ""})


def resolved_model(cfg):
    """The actual model id for an agent config (handles the 'custom' choice)."""
    if cfg["model"] == CUSTOM:
        return cfg.get("custom_model", "").strip()
    return cfg["model"]


def agent_key(model, custom_key):
    """Which API key to hand this agent: session key for its provider, else its
    own typed key, else None (providers.ask will then try .env)."""
    return session_key(provider_for(model)) or (custom_key or None)


def model_ready(model, custom_key):
    if not model:
        return False
    if custom_key:
        return True
    return provider_ready(provider_for(model))


def model_option_label(val):
    """Label for one entry in the model dropdown."""
    if val == CUSTOM:
        return "✏️  Custom model id…"
    m = find_model(val)
    p = pmeta(provider_for(val))
    tail = "" if provider_ready(provider_for(val)) else "  · needs key"
    return f"{p['emoji']} {p['label']} · {m['label']} — {m['strength']}{tail}"


MODEL_OPTIONS = [m["id"] for m in all_models()] + [CUSTOM]

# ── CSS (modern look) ─────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
      .block-container { padding-top: 2.0rem; max-width: 1150px; }
      .cai-title {
        font-size: 2.6rem; font-weight: 800; letter-spacing: -0.02em;
        background: linear-gradient(90deg, #7c5cff 0%, #4dd6ff 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem;
      }
      .cai-sub { color: #9aa3b2; font-size: 1.02rem; margin-bottom: 0.8rem; }
      .cai-matchup {
        display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
        padding: 0.9rem 1.1rem; border: 1px solid #262c3a; border-radius: 14px;
        background: #131825; margin-bottom: 1.2rem;
      }
      .cai-agent { display: flex; flex-direction: column; line-height: 1.25; }
      .cai-agent .nm { font-weight: 700; font-size: 1.0rem; color: #e8eaed; }
      .cai-agent .pv { font-size: 0.82rem; color: #9aa3b2; }
      .cai-vs { font-size: 1.2rem; color: #7c5cff; font-weight: 700; padding: 0 0.2rem; }
      .cai-turnhead { font-weight: 700; font-size: 1.02rem; color: #e8eaed; }
      .cai-turnhead small { color: #9aa3b2; font-weight: 500; }
      .cai-cardlbl { font-weight: 700; color: #7c5cff; font-size: 0.9rem;
                     text-transform: uppercase; letter-spacing: 0.04em; }
      /* Bigger, clearer tab labels */
      .stTabs [data-baseweb="tab"] { font-size: 1.02rem; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state init ────────────────────────────────────────────────────────
if "agents" not in st.session_state:
    st.session_state.agents = [
        {"id": 0, "name": "Planner", "model": DEFAULT_MODEL_A,
         "custom_model": "", "custom_key": "", "role": DEFAULT_ROLE_A},
        {"id": 1, "name": "Writer", "model": DEFAULT_MODEL_B,
         "custom_model": "", "custom_key": "", "role": DEFAULT_ROLE_B},
    ]
    st.session_state.next_id = 2

# ── Header (always visible above the tabs) ────────────────────────────────────
st.markdown('<div class="cai-title">🤝 ConnectAI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="cai-sub">Build a team of AI agents from different providers — '
    'each on the model it does best — and watch them collaborate on one task.</div>',
    unsafe_allow_html=True,
)

tab_run, tab_team, tab_keys = st.tabs(["▶️  Run", "👥  Team", "🔑  API keys"])

# ── 🔑 API KEYS TAB (rendered first so its values exist for the other tabs) ────
with tab_keys:
    st.subheader("Your API keys")
    st.caption(
        "Bring your own keys. They stay in this browser session only — never saved "
        "to disk or logged. You pay your providers directly. Prefer full control? "
        "Run the app locally and put keys in a .env file instead."
    )
    kcols = st.columns(2)
    for i, (provider, cfg) in enumerate(PROVIDERS.items()):
        m = pmeta(provider)
        with kcols[i % 2]:
            st.text_input(
                f"{m['emoji']} {m['label']} key", type="password", key=f"key_{provider}",
                placeholder=cfg["key_env"],
                help=f"Your {m['label']} API key. Used only for this session.",
            )
            if is_configured(provider) and not session_key(provider):
                st.caption("✓ detected from your local .env")
            elif session_key(provider):
                st.caption("✓ set for this session")

# ── 👥 TEAM TAB ───────────────────────────────────────────────────────────────
with tab_team:
    st.subheader("Your team")
    st.caption(
        f"Add {MIN_AGENTS}–{MAX_AGENTS} agents. Give each a different model to "
        "combine their strengths — e.g. Claude to code, Gemini to reason, "
        "Perplexity to research live."
    )

    remove_id = None
    for i, cfg in enumerate(st.session_state.agents):
        aid = cfg["id"]
        with st.container(border=True):
            st.markdown(f'<span class="cai-cardlbl">Agent {i + 1}</span>',
                        unsafe_allow_html=True)
            top = st.columns([1, 2])
            with top[0]:
                cfg["name"] = st.text_input(
                    "Name", value=cfg["name"], key=f"name_{aid}",
                    help="Display name shown in the transcript.",
                )
            with top[1]:
                default_idx = (
                    MODEL_OPTIONS.index(cfg["model"])
                    if cfg["model"] in MODEL_OPTIONS else len(MODEL_OPTIONS) - 1
                )
                cfg["model"] = st.selectbox(
                    "Model", MODEL_OPTIONS, index=default_idx, key=f"model_{aid}",
                    format_func=model_option_label,
                    help="Pick a model — or 'Custom model id' to type any litellm model string.",
                )

            if cfg["model"] == CUSTOM:
                cc = st.columns([2, 2])
                with cc[0]:
                    cfg["custom_model"] = st.text_input(
                        "Custom model id", value=cfg.get("custom_model", ""),
                        key=f"cm_{aid}", placeholder="e.g. gemini/gemini-2.5-flash-lite",
                        help="Any litellm model string.",
                    )
                with cc[1]:
                    cfg["custom_key"] = st.text_input(
                        "API key for this model (optional)", type="password",
                        value=cfg.get("custom_key", ""), key=f"ck_{aid}",
                        help="Only needed if its provider isn't in the keys list. "
                             "Otherwise it uses your session/.env key.",
                    )

            cfg["role"] = st.text_area(
                "Role", value=cfg["role"], key=f"role_{aid}", height=110,
                help="The system prompt — tells this agent who it is and how to behave.",
            )

            if len(st.session_state.agents) > MIN_AGENTS:
                if st.button("🗑 Remove", key=f"rm_{aid}"):
                    remove_id = aid

    if remove_id is not None:
        st.session_state.agents = [a for a in st.session_state.agents if a["id"] != remove_id]
        st.rerun()

    if len(st.session_state.agents) < MAX_AGENTS:
        if st.button("➕  Add agent"):
            st.session_state.agents.append({
                "id": st.session_state.next_id,
                "name": f"Agent {len(st.session_state.agents) + 1}",
                "model": DEFAULT_MODEL_A, "custom_model": "", "custom_key": "",
                "role": DEFAULT_ROLE_A,
            })
            st.session_state.next_id += 1
            st.rerun()

# ── ▶️ RUN TAB ────────────────────────────────────────────────────────────────
with tab_run:
    st.caption("Set up your agents in the **👥 Team** tab and your keys in **🔑 API keys**, "
               "then write a task below and run.")

    # Live matchup hero
    chips = []
    for cfg in st.session_state.agents:
        model = resolved_model(cfg) or cfg["model"]
        m = pmeta(provider_for(model)) if model and model != CUSTOM else {"emoji": "•", "label": "—"}
        sub = find_model(model)["label"] if find_model(model) else (model or "—")
        chips.append(
            f'<div class="cai-agent"><span class="nm">{m["emoji"]} {cfg["name"] or "Agent"}</span>'
            f'<span class="pv">{m["label"]} · {sub}</span></div>'
        )
    st.markdown(
        '<div class="cai-matchup">' + '<span class="cai-vs">↔</span>'.join(chips) + '</div>',
        unsafe_allow_html=True,
    )

    needs = [pmeta(p)["label"] for p in PROVIDERS if not provider_ready(p)]
    if needs:
        st.caption("🔑 No key yet for: " + ", ".join(needs) +
                   ". Add it in the **🔑 API keys** tab to use those models. "
                   "Groq works free out of the box.")

    task = st.text_area(
        "What should the team work on?",
        placeholder="e.g.  Write a short guide to staying focused while studying",
        height=100, key="task",
    )

    s1, s2 = st.columns([3, 1])
    with s2:
        max_turns = st.slider(
            "Max turns", min_value=2, max_value=16, value=6,
            help="Maximum replies across all agents combined. Each reply is 1 turn. "
                 "Stops early when an agent signals the task is done.",
        )

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        run_btn = st.button("▶  Run collaboration", type="primary",
                            use_container_width=True, disabled=not task.strip())
    with c2:
        cost_box = st.empty()
    with c3:
        turn_box = st.empty()
    cost_box.metric("Cost", "$0.0000")
    turn_box.metric("Turns", f"0 / {max_turns}")

    # ── Collaboration loop ────────────────────────────────────────────────────
    if run_btn and task.strip():
        built, problems = [], []
        for cfg in st.session_state.agents:
            model = resolved_model(cfg)
            if not model:
                problems.append(f"**{cfg['name']}** has no model selected.")
                continue
            if not model_ready(model, cfg.get("custom_key")):
                p = pmeta(provider_for(model))
                problems.append(
                    f"**{cfg['name']}** uses {p['label']} ({model}) but no key is set."
                )
            built.append(Agent(cfg["name"], model, cfg["role"],
                               api_key=agent_key(model, cfg.get("custom_key"))))

        if problems:
            st.error("Can't run yet:\n\n- " + "\n- ".join(problems) +
                     "\n\nAdd the missing key in the **🔑 API keys** tab, or switch that "
                     "agent to a free Groq model.")
            st.stop()

        reset_cost()
        agents = built
        n = len(agents)
        scratchpad = ""
        st.divider()

        for turn in range(1, max_turns + 1):
            agent = agents[(turn - 1) % n]
            m = pmeta(agent.provider)
            can_stop = (turn >= n) and (turn % n == 0)

            user_msg = _build_prompt(agents, agent, task, scratchpad, can_stop)
            done_this_turn = False

            with st.container(border=True):
                st.markdown(
                    f'<div class="cai-turnhead">{m["emoji"]} {agent.name} '
                    f'<small>· {m["label"]} · {agent.model} · turn {turn}/{max_turns}</small></div>',
                    unsafe_allow_html=True,
                )
                with st.spinner(f"{agent.name} is thinking…"):
                    try:
                        reply = agent.reply(user_msg)
                    except ProviderError as e:
                        st.error(f"Provider error: {e}")
                        break

                display_reply = reply
                if reply.strip().upper().startswith(_DONE_SIGNAL):
                    done_this_turn = True
                    parts = reply.strip().split("\n", 1)
                    display_reply = parts[1].strip() if len(parts) > 1 else ""

                if display_reply:
                    st.markdown(display_reply)

            scratchpad += f"\n--- {agent.name} (turn {turn}) ---\n{display_reply}\n"
            cost_box.metric("Cost", f"${total_cost():.4f}")
            turn_box.metric("Turns", f"{turn} / {max_turns}")

            if done_this_turn:
                st.success(f"✓ {agent.name} signalled the task is complete.")
                break
        else:
            st.info(f"Reached the turn limit ({max_turns} turns).")

        st.divider()
        st.subheader("📄 Final result")
        st.markdown(scratchpad)
        st.download_button(
            "⬇  Download result (.md)", data=scratchpad.strip(),
            file_name="connectai_result.md", mime="text/markdown",
        )
        st.metric("Total cost", f"${total_cost():.4f}")
