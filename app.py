"""
app.py — Streamlit web UI for ConnectAI.

Run with:
    streamlit run app.py

Layout (chat-app style, like Claude / ChatGPT):
  • Sidebar — all the setup: collaboration mode, the lead picker, your team of
    2–7 agents, API keys, and the run limits.
  • Main    — a clean conversation. You type a task at the bottom and the team's
    work streams in as message bubbles (round-robin turns, or the manager's
    delegations + the workers' replies + the synthesised final answer).
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
MIN_AGENTS, MAX_AGENTS = 2, 7

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

# Friendly labels for how a Manager-mode run ended.
REASON_LABELS = {
    "manager_finished": "✓ the manager finished",
    "max_steps": "⛔ hit the step cap",
    "cost_cap": "⛔ hit the cost cap",
    "stalled": "⛔ no further progress",
    "parse_failures": "⛔ manager output couldn't be parsed",
    "provider_error": "⛔ a model provider errored (e.g. rate limit)",
    "no_workers": "no workers configured",
}

st.set_page_config(page_title="ConnectAI", page_icon="🤝", layout="wide")

# ── Config helpers ──────────────────────────────────────────────────────────────

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
    return f"{p['emoji']} {p['label']} · {m['label']}{tail}"


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


def model_sub(model):
    """Short '<Provider> · <Model>' label for a model id (for message headers)."""
    p = pmeta(provider_for(model))
    name = find_model(model)["label"] if find_model(model) else model
    return f"{p['label']} · {name}"


# st.chat_message avatars must be REAL emoji. Some of config.py's display glyphs
# (Gemini's "✦", the "•" fallback) aren't valid emoji and make chat_message raise,
# so map each provider to a guaranteed-valid emoji for avatars here. (The original
# glyphs are still fine for plain text like the team strip.)
AVATARS = {"groq": "⚡", "gemini": "✨", "openai": "🤖",
           "anthropic": "🧠", "perplexity": "🔎"}


def avatar_for(model):
    return AVATARS.get(provider_for(model), "🤖")


# ── CSS (keep the brand; constrain the chat column for readability) ─────────────--
st.markdown(
    """
    <style>
      .block-container { padding-top: 2.6rem; max-width: 860px; }
      .cai-title {
        font-size: 1.9rem; font-weight: 800; letter-spacing: -0.02em;
        background: linear-gradient(90deg, #7c5cff 0%, #4dd6ff 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.05rem;
      }
      .cai-sub { color: #9aa3b2; font-size: 0.95rem; margin-bottom: 0.4rem; }
      .cai-team { color: #c7cdda; font-size: 0.9rem; padding: 0.45rem 0.7rem;
                  border: 1px solid #262c3a; border-radius: 10px; background: #131825;
                  margin-bottom: 0.4rem; }
      [data-testid="stSidebar"] { min-width: 340px; }
      [data-testid="stChatMessage"] { background: transparent; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ───────────────────────────────────────────────────────────────
if "agents" not in st.session_state:
    st.session_state.agents = [
        {"id": 0, "name": "Planner", "model": DEFAULT_MODEL_A,
         "custom_model": "", "custom_key": "", "role": DEFAULT_ROLE_A},
        {"id": 1, "name": "Writer", "model": DEFAULT_MODEL_B,
         "custom_model": "", "custom_key": "", "role": DEFAULT_ROLE_B},
    ]
    st.session_state.next_id = 2
st.session_state.setdefault("messages", [])   # the conversation so far
st.session_state.setdefault("last_result", "")
st.session_state.setdefault("last_cost", 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# RENDERING — one function turns a stored message dict into a chat bubble, so the
# conversation can be re-rendered on every rerun AND streamed live during a run.
# ══════════════════════════════════════════════════════════════════════════════

def render_message(m):
    kind = m["kind"]
    if kind == "user":
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(m["content"])
    elif kind in ("agent", "worker"):
        with st.chat_message(m["name"], avatar=m["emoji"]):
            st.markdown(f"**{m['name']}**  ·  <span style='color:#9aa3b2'>{m['sub']}</span>",
                        unsafe_allow_html=True)
            if m.get("error"):
                st.error(m["content"])
            else:
                st.markdown(m["content"] or "_(no output)_")
    elif kind == "manager":
        with st.chat_message("Lead", avatar="🧭"):
            st.markdown(m["content"])
    elif kind == "system":
        st.caption(m["content"])
    elif kind == "final":
        with st.chat_message("Final", avatar="✅"):
            st.markdown("**📄 Final answer**")
            st.markdown(m["content"])
            with st.expander("📋 Copy as text"):
                # st.code shows a one-click copy button in its top-right corner.
                st.code(m["content"], language=None)
            if m.get("meta"):
                st.caption(m["meta"])


# ── The two run loops (each calls add(msg) so messages stream + persist) ────────--

def run_round_robin(agents, task, *, max_turns, add):
    n = len(agents)
    scratchpad = ""
    for turn in range(1, max_turns + 1):
        agent = agents[(turn - 1) % n]
        can_stop = (turn >= n) and (turn % n == 0)
        user_msg = _build_prompt(agents, agent, task, scratchpad, can_stop)
        try:
            reply = agent.reply(user_msg)
        except ProviderError as e:
            add({"kind": "system", "content": f"⚠ {agent.name} (provider error): {e}"})
            break

        display = reply
        done = reply.strip().upper().startswith(_DONE_SIGNAL)
        if done:
            parts = reply.strip().split("\n", 1)
            display = parts[1].strip() if len(parts) > 1 else ""

        if display:
            add({"kind": "agent", "name": agent.name,
                 "emoji": avatar_for(agent.model),
                 "sub": f"{model_sub(agent.model)} · turn {turn}/{max_turns}",
                 "content": display})
        scratchpad += f"\n--- {agent.name} (turn {turn}) ---\n{display}\n"
        if done:
            add({"kind": "system", "content": f"✓ {agent.name} signalled the task is complete."})
            break
    else:
        add({"kind": "system", "content": f"Reached the turn limit ({max_turns} turns)."})

    add({"kind": "system", "content": f"💰 Done · ${total_cost():.4f}"})
    return scratchpad.strip()


def run_manager_chat(manager, workers, task, *, max_steps, max_cost, use_critic, add):
    final_text = ""
    for ev in run_manager(manager, workers, task, max_steps=max_steps,
                          max_cost_usd=max_cost, use_critic=use_critic):
        t = ev["type"]
        if t == "manager_decision":
            d = ev["decision"]
            if d is None:
                why = (f"the lead's provider errored ({ev['error']})" if ev.get("provider_error")
                       else f"the lead couldn't produce a valid decision ({ev['error']})")
                add({"kind": "system", "content": f"⚠ {why} — building a best-effort answer."})
            elif d["action"] == "delegate":
                c = f"**Step {ev['step']} — Delegates to {d['to']}**\n\n> {d['instruction']}"
                if d.get("reason"):
                    c += f"\n\n*why: {d['reason']}*"
                add({"kind": "manager", "content": c})
            else:
                add({"kind": "manager",
                     "content": f"**Step {ev['step']} — Task complete; synthesising the answer.**"})
        elif t == "worker_result":
            add({"kind": "worker", "name": ev["worker"],
                 "emoji": avatar_for(ev["model"]),
                 "sub": f"{model_sub(ev['model'])} · step {ev['step']}",
                 "content": (ev["error"] and f"Worker error: {ev['error']}") or ev["output"],
                 "error": bool(ev["error"])})
        elif t == "critique":
            add({"kind": "system",
                 "content": f"🔎 quality check [{'OK' if ev['accept'] else 'needs work'}]: {ev['feedback']}"})
        elif t == "guardrail":
            add({"kind": "system", "content": f"⛔ guardrail [{ev['name']}]: {ev['detail']}"})
        elif t == "synthesis":
            add({"kind": "system",
                 "content": f"⏳ stopping ({ev['reason']}) — assembling the best answer so far…"})
        elif t == "final":
            final_text = ev["answer"]
            meta = f"{REASON_LABELS.get(ev['finish_reason'], ev['finish_reason'])} · {ev['steps']} steps · ${ev['cost']:.4f}"
            add({"kind": "final", "content": final_text, "meta": meta})
    return final_text


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — all configuration lives here
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown('<div class="cai-title">🤝 ConnectAI</div>', unsafe_allow_html=True)
    st.caption("A team of AI agents, each on the model it does best.")

    mode = st.radio("Collaboration mode", ["Round-robin", "Manager"],
                    key="mode_choice", horizontal=True,
                    help="Round-robin: agents take turns on a shared scratchpad. "
                         "Manager: a lead delegates subtasks and synthesises the answer.")
    is_manager = mode == "Manager"

    # Defaults so both modes' variables always exist.
    max_turns, max_steps, max_cost, use_critic = 6, DEFAULT_MAX_STEPS, DEFAULT_MAX_COST_USD, False

    if is_manager:
        agent_ids = [c["id"] for c in st.session_state.agents]
        id_to_name = {c["id"]: (c["name"] or "Agent") for c in st.session_state.agents}
        if st.session_state.get("lead_choice") not in agent_ids:
            st.session_state.lead_choice = agent_ids[0]
        st.selectbox("👑 Lead (the Manager)", agent_ids, key="lead_choice",
                     format_func=lambda aid: id_to_name.get(aid, "Agent"),
                     help="This agent coordinates: it delegates to the others and writes the "
                          "final answer. Its role is set automatically — but its MODEL matters, "
                          "so pick a strong reasoner. Everyone else becomes a worker.")
        cc = st.columns(2)
        with cc[0]:
            max_steps = st.slider("Max steps", 2, 20, DEFAULT_MAX_STEPS,
                                  help="Hard cap on the lead's decisions.")
        with cc[1]:
            max_cost = st.number_input("Max $", min_value=0.0, value=float(DEFAULT_MAX_COST_USD),
                                       step=0.05, format="%.2f", help="Hard spend cap per run.")
        use_critic = st.toggle("🔎 Quality critic", value=False,
                               help="One review pass per worker output (adds calls).")
    else:
        max_turns = st.slider("Max turns", 2, 16, 6,
                              help="Total replies across all agents. Stops early on DONE.")

    # ── Team ──────────────────────────────────────────────────────────────────
    with st.expander(f"👥 Team — {len(st.session_state.agents)} agents", expanded=False):
        st.caption(f"Add {MIN_AGENTS}–{MAX_AGENTS} agents. Give each a different model to "
                   "combine their strengths.")
        remove_id = None
        for i, cfg in enumerate(st.session_state.agents):
            aid = cfg["id"]
            with st.container(border=True):
                cfg["name"] = st.text_input("Name", value=cfg["name"], key=f"name_{aid}")
                default_idx = (MODEL_OPTIONS.index(cfg["model"])
                               if cfg["model"] in MODEL_OPTIONS else len(MODEL_OPTIONS) - 1)
                cfg["model"] = st.selectbox("Model", MODEL_OPTIONS, index=default_idx,
                                            key=f"model_{aid}", format_func=model_option_label)
                if cfg["model"] == CUSTOM:
                    cfg["custom_model"] = st.text_input(
                        "Custom model id", value=cfg.get("custom_model", ""), key=f"cm_{aid}",
                        placeholder="e.g. gemini/gemini-2.5-flash-lite")
                    cfg["custom_key"] = st.text_input(
                        "API key for it (optional)", type="password",
                        value=cfg.get("custom_key", ""), key=f"ck_{aid}")
                cfg["role"] = st.text_area("Role", value=cfg["role"], key=f"role_{aid}", height=90)
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

    # ── Keys ──────────────────────────────────────────────────────────────────
    with st.expander("🔑 API keys", expanded=False):
        st.caption("Bring your own keys — kept in this browser session only, never saved.")
        for provider, pcfg in PROVIDERS.items():
            m = pmeta(provider)
            st.text_input(f"{m['emoji']} {m['label']}", type="password",
                          key=f"key_{provider}", placeholder=pcfg["key_env"])
            if is_configured(provider) and not session_key(provider):
                st.caption("✓ detected from your local .env")

    st.divider()
    st.metric("Spent (last run)", f"${st.session_state.last_cost:.4f}")
    if st.session_state.last_result:
        st.download_button("⬇  Download last result (.md)", data=st.session_state.last_result,
                           file_name="connectai_result.md", mime="text/markdown",
                           use_container_width=True)
    if st.session_state.messages:
        if st.button("🗑  Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_result = ""
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — the conversation (the brand lives in the sidebar; keep this area clean)
# ══════════════════════════════════════════════════════════════════════════════

# Compact team strip showing who's playing (and who leads, in manager mode).
lead_id = st.session_state.get("lead_choice")
chips = []
for c in st.session_state.agents:
    model = resolved_model(c) or c["model"]
    emoji = pmeta(provider_for(model))["emoji"] if model and model != CUSTOM else "•"
    crown = " 👑" if (is_manager and c["id"] == lead_id) else ""
    chips.append(f"{emoji} {c['name'] or 'Agent'}{crown}")
prefix = "🧭 Manager mode" if is_manager else "🔁 Round-robin"
st.markdown(f'<div class="cai-team"><b>{prefix}</b> &nbsp;·&nbsp; {"  ".join(chips)}</div>',
            unsafe_allow_html=True)

# Any provider without a key (helpful nudge).
needs = [pmeta(p)["label"] for p in PROVIDERS if not provider_ready(p)]
if needs:
    st.caption("🔑 No key yet for: " + ", ".join(needs) +
               " — add it in the sidebar. Groq works free out of the box.")

# Replay the conversation so far.
for m in st.session_state.messages:
    render_message(m)

if not st.session_state.messages:
    st.info("👋 Set up your team in the sidebar, then type a task below to start.")

# The composer (pinned to the bottom, ChatGPT-style).
prompt = st.chat_input("Give your team a task…")

if prompt:
    agents, problems = build_agents(st.session_state.agents)
    if problems:
        st.error("Can't run yet:\n\n- " + "\n- ".join(problems) +
                 "\n\nAdd the missing key in the sidebar, or switch that agent to a free "
                 "Groq model.")
    else:
        def add(msg):
            st.session_state.messages.append(msg)
            render_message(msg)

        add({"kind": "user", "content": prompt})
        reset_cost()

        if is_manager:
            lead_idx = next((i for i, c in enumerate(st.session_state.agents)
                             if c["id"] == st.session_state.get("lead_choice")), 0)
            manager = agents[lead_idx]
            workers = [a for i, a in enumerate(agents) if i != lead_idx]
            result = run_manager_chat(manager, workers, prompt, max_steps=max_steps,
                                      max_cost=max_cost, use_critic=use_critic, add=add)
        else:
            result = run_round_robin(agents, prompt, max_turns=max_turns, add=add)

        st.session_state.last_result = result
        st.session_state.last_cost = total_cost()
        st.rerun()   # refresh the sidebar metric / download button with this run's totals
