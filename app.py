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
from manager import run_manager, DEFAULT_MAX_STEPS, DEFAULT_MAX_COST_USD
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


def build_agents(cfgs):
    """Turn the UI's agent configs into Agent objects. Used by BOTH modes.

    Returns (agents, problems). `problems` lists human-readable reasons a run
    can't start yet (missing model / missing key); when it's empty, `agents`
    lines up 1-to-1 with `cfgs` in order.
    """
    built, problems = [], []
    for cfg in cfgs:
        model = resolved_model(cfg)
        if not model:
            problems.append(f"**{cfg['name']}** has no model selected.")
            continue
        if not model_ready(model, cfg.get("custom_key")):
            p = pmeta(provider_for(model))
            problems.append(f"**{cfg['name']}** uses {p['label']} ({model}) but no key is set.")
        built.append(Agent(cfg["name"], model, cfg["role"],
                           api_key=agent_key(model, cfg.get("custom_key"))))
    return built, problems


def _agent_head(name, model, tail):
    """The little coloured header used on each card (emoji · provider · model)."""
    m = pmeta(provider_for(model))
    label = find_model(model)["label"] if find_model(model) else model
    st.markdown(
        f'<div class="cai-turnhead">{m["emoji"]} {name} '
        f'<small>· {m["label"]} · {label} · {tail}</small></div>',
        unsafe_allow_html=True,
    )


def manager_timeline(manager, workers, task, *, max_steps, max_cost, use_critic,
                     cost_box, steps_box):
    """Run Manager Mode and render every decision as a live timeline.

    Consumes the SAME run_manager() generator the CLI and tests use, so the UI is
    just a view over the engine. Returns (final_answer, finish_reason, steps).
    """
    final_answer, finish_reason, steps = "", None, 0

    try:
        for ev in run_manager(manager, workers, task, max_steps=max_steps,
                              max_cost_usd=max_cost, use_critic=use_critic):
            t = ev["type"]

            if t == "manager_decision":
                steps = ev["step"]
                steps_box.metric("Steps", f"{steps} / {max_steps}")
                cost_box.metric("Cost", f"${ev['cost']:.4f} / ${max_cost:.2f}")
                with st.container(border=True):
                    _agent_head(manager.name, manager.model,
                                f"Manager · step {steps}/{max_steps}")
                    d = ev["decision"]
                    if d is None:
                        st.warning(
                            f"Couldn't get a valid decision after {ev['attempts']} "
                            f"tries ({ev['error']}). Falling back to a best-effort answer."
                        )
                    elif d["action"] == "delegate":
                        st.markdown(f"**→ Delegates to {d['to']}**")
                        if d.get("reason"):
                            st.caption(f"Why: {d['reason']}")
                        st.markdown(f"> {d['instruction']}")
                    else:
                        st.markdown("**✓ Decides the task is complete.**")
                    if ev["attempts"] > 1 and d is not None:
                        st.caption(f"(took {ev['attempts']} tries to get valid JSON)")

            elif t == "worker_result":
                cost_box.metric("Cost", f"${ev['cost']:.4f} / ${max_cost:.2f}")
                with st.container(border=True):
                    _agent_head(ev["worker"], ev["model"], f"worker · step {ev['step']}")
                    if ev["error"]:
                        st.error(f"Worker error: {ev['error']}")
                    elif ev["output"]:
                        st.markdown(ev["output"])
                    else:
                        st.caption("(returned nothing)")

            elif t == "critique":
                if ev["accept"]:
                    st.caption(f"🔎 Quality check [OK]: {ev['feedback']}")
                else:
                    st.warning(f"🔎 Quality check [needs work]: {ev['feedback']}")

            elif t == "guardrail":
                st.warning(f"⛔ Guardrail — **{ev['name']}**: {ev['detail']}")

            elif t == "synthesis":
                st.info(f"⏳ Stopping ({ev['reason']}) — asking {manager.name} to "
                        "synthesise the best possible answer from the work so far…")

            elif t == "final":
                final_answer = ev["answer"]
                finish_reason = ev["finish_reason"]
                steps = ev["steps"]
                cost_box.metric("Cost", f"${ev['cost']:.4f} / ${max_cost:.2f}")
                steps_box.metric("Steps", f"{steps} / {max_steps}")
    except ProviderError as e:
        st.error(f"Provider error: {e}")
    except Exception as e:  # never white-screen — surface and keep the page alive
        st.error(f"Unexpected error: {e}")

    return final_answer, finish_reason, steps

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

    # ── Collaboration mode ────────────────────────────────────────────────────
    with st.container(border=True):
        mode = st.radio(
            "Collaboration mode", ["Round-robin", "Manager"],
            key="mode_choice", horizontal=True,
            help="Round-robin: agents take turns adding to a shared scratchpad. "
                 "Manager: one lead agent delegates subtasks to the others and "
                 "synthesises the final answer.",
        )
        if mode == "Manager":
            agent_ids = [c["id"] for c in st.session_state.agents]
            # A plain local map (id -> name). Kept out of st.session_state so the
            # selectbox's format_func stays pure — Streamlit's test harness calls
            # it outside a script run, where touching session_state would error.
            id_to_name = {c["id"]: (c["name"] or "Agent") for c in st.session_state.agents}
            # Reset the stored lead if it points at a removed agent (avoids a crash).
            if st.session_state.get("lead_choice") not in agent_ids:
                st.session_state.lead_choice = agent_ids[0]

            st.selectbox(
                "👑 Lead (the Manager)", agent_ids, key="lead_choice",
                format_func=lambda aid: id_to_name.get(aid, "Agent"),
                help="This agent coordinates: it delegates subtasks to the others "
                     "and writes the final answer. In Manager mode its own role "
                     "text is replaced by manager instructions — but its MODEL "
                     "still matters, so pick a strong reasoner. The other agents "
                     "become workers (their roles are used).",
            )
            st.caption("Everyone except the lead becomes a worker. Verify free on "
                       "Groq/Gemini before switching the lead to a paid model.")

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

    is_manager = st.session_state.get("mode_choice", "Round-robin") == "Manager"

    if is_manager:
        lead_id = st.session_state.get("lead_choice")
        lead_cfg = next((c for c in st.session_state.agents if c["id"] == lead_id),
                        st.session_state.agents[0])
        workers_str = ", ".join(c["name"] for c in st.session_state.agents
                                if c["id"] != lead_cfg["id"]) or "—"
        st.caption(f"🧭 **Manager mode** — 👑 lead: **{lead_cfg['name']}**  ·  "
                   f"workers: {workers_str}  (change in the **👥 Team** tab)")
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            max_steps = st.slider(
                "Max steps", min_value=2, max_value=20, value=DEFAULT_MAX_STEPS,
                help="Hard cap on the lead's decisions — the main brake on runaway loops.",
            )
        with mc2:
            max_cost = st.number_input(
                "Max cost (USD)", min_value=0.0, value=float(DEFAULT_MAX_COST_USD),
                step=0.05, format="%.2f",
                help="Hard spend cap, checked before every model call. On Groq/Gemini "
                     "you'll rarely get close.",
            )
        with mc3:
            st.write("")  # vertical spacer to line the checkbox up with the inputs
            use_critic = st.checkbox(
                "🔎 Quality critic", value=False,
                help="One review pass per worker output (advisory — fed back to the "
                     "lead). Improves quality but adds model calls.",
            )
    else:
        st.caption("🔁 **Round-robin mode** — agents take turns on a shared scratchpad.")
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
        prog_box = st.empty()
    if is_manager:
        cost_box.metric("Cost", f"$0.0000 / ${max_cost:.2f}")
        prog_box.metric("Steps", f"0 / {max_steps}")
    else:
        cost_box.metric("Cost", "$0.0000")
        prog_box.metric("Turns", f"0 / {max_turns}")

    # ── Run ─────────────────────────────────────────────────────────────────--
    if run_btn and task.strip():
        agents, problems = build_agents(st.session_state.agents)
        if problems:
            st.error("Can't run yet:\n\n- " + "\n- ".join(problems) +
                     "\n\nAdd the missing key in the **🔑 API keys** tab, or switch that "
                     "agent to a free Groq model.")
            st.stop()

        reset_cost()
        st.divider()

        # ── MANAGER MODE ───────────────────────────────────────────────────────
        if is_manager:
            lead_idx = next((i for i, c in enumerate(st.session_state.agents)
                             if c["id"] == st.session_state.get("lead_choice")), 0)
            manager = agents[lead_idx]
            workers = [a for i, a in enumerate(agents) if i != lead_idx]

            final_answer, finish_reason, steps = manager_timeline(
                manager, workers, task, max_steps=max_steps, max_cost=max_cost,
                use_critic=use_critic, cost_box=cost_box, steps_box=prog_box,
            )

            st.divider()
            st.subheader("📄 Final answer")
            if final_answer:
                st.markdown(final_answer)
                st.download_button(
                    "⬇  Download answer (.md)", data=final_answer.strip(),
                    file_name="connectai_answer.md", mime="text/markdown",
                )
            reason_label = {
                "manager_finished": "✓ the manager finished",
                "max_steps": "⛔ hit the step cap",
                "cost_cap": "⛔ hit the cost cap",
                "stalled": "⛔ no further progress",
                "parse_failures": "⛔ manager output couldn't be parsed",
                "no_workers": "no workers configured",
            }.get(finish_reason, str(finish_reason))
            st.caption(f"Ended: {reason_label}  ·  {steps} steps  ·  ${total_cost():.4f}")
            st.metric("Total cost", f"${total_cost():.4f}")

        # ── ROUND-ROBIN MODE (unchanged) ───────────────────────────────────────
        else:
            n = len(agents)
            scratchpad = ""

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
                prog_box.metric("Turns", f"{turn} / {max_turns}")

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
