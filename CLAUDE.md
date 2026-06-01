# ConnectAI — Project Guide for Claude Code

ConnectAI connects AI agents from **different providers** (Groq, Google Gemini, and
later OpenAI/Anthropic) into a team that collaborates on a shared task — using each
model for what it's best at.

## ⚠️ Read this first
- The user is a **university student in Stockholm, a beginner coder with no real coding
  experience, and limited funds.** Claude does the building; the user assists with
  accounts, keys, and decisions. **Explain what you're doing and why, in plain language.**
- **Build with a single instance, NOT agent teams** (teams burn 3–4x tokens). Use
  **Sonnet 4.6** for most work; switch to **Opus 4.8** only for hard architecture/bugs.
- Keep dev cost ~$0: cheapest models, set in `config.py`.

## Current status
- ✅ **Phase 0** — setup, two providers working, repo on GitHub
- ✅ **Phase 1** — unified provider interface (`providers.ask()`) + cost tracking
- ✅ **Phase 2** — two-agent collaboration engine: `agent.py`, `orchestrator.py`, `run.py`
- ✅ **Phase 3** — Streamlit web UI: `app.py` (`streamlit run app.py`)
- ✅ **Phase 4** — launch docs: real `README.md`, `LICENSE` (MIT), `.env.example`
- ✅ **Phase 4.5** — BYO keys + per-model picker (5 providers) + 2–4 agents + tabbed UI.
  All 5 keys (Groq/Gemini/OpenAI/Anthropic/Perplexity) live in `.env` and tested working.
- ⏭️ **NEXT → Phase 5** — add a README screenshot (TODO marker is in `README.md`); deploy
  free demo to Streamlit Community Cloud; user posts to ≥3 communities (needs user accounts).
- 🔮 **Future → "Manager mode"** — let agents truly collaborate via a lead/manager agent
  (design sketch below). Deferred: it's a real feature deserving a fresh session.

## Manager mode (next big feature — design sketch for a fresh session)
Today agents take fixed round-robin turns over a shared scratchpad (`orchestrator.run`).
The next step the user wants: a **manager/supervisor pattern** (not free-for-all chatter,
which is messier + burns tokens). Plan:
- Designate one agent as **lead** (e.g. agent 1, or a UI toggle / a dedicated "Manager" role).
- New orchestrator mode: lead reads the task → decides *which* worker does *what* (delegates)
  → workers reply → lead **synthesizes** the final answer. Lead drives the loop instead of
  fixed round-robin.
- Keep the hand-rolled style. Add a mode switch in `orchestrator.py` (round-robin vs manager)
  and a UI control in the **Team** tab to pick the lead. Watch cost — delegation = more calls.
- Verify free with Groq + Gemini before using paid models.

Full build plan: `~/.claude/plans/lets-go-with-that-quirky-feather.md`
Strategy/market context: `~/.claude/projects/-Users-mohidhayee-Documents-ConnectAI/memory/`

## How to run
```bash
source .venv/bin/activate
python test_providers.py                   # confirm providers with keys work
python run.py "your task here"             # CLI: multi-agent collaboration
streamlit run app.py                       # web UI (BYO keys, 2–4 agents, model picker)
```

## Architecture (keep it this way)
- `config.py` — the catalog: `PROVIDERS` (label/emoji/key_env/tier) + `MODELS` (curated
  list per provider, each `{id,label,strength}`). **Add/retire models only here.**
- `providers.py` — `ask(prompt, *, model, system=None, messages=None, api_key=None)` is the
  ONE way to call any model. Provider is inferred from the model id (`provider_for`); key is
  the passed `api_key` else the provider's env var. Tracks cost via `total_cost()`. Never
  call litellm directly elsewhere.
- `agent.py` — `Agent(name, model, role, api_key=None)`; `.provider` is derived from model.
- `orchestrator.py` — `run(agents_list, task, max_turns)`; round-robin over 2–4 agents; an
  agent may only signal DONE at the end of a full round (`turn>=n and turn%n==0`).
- `app.py` — imports `_build_prompt`/`_DONE_SIGNAL` from orchestrator (one source of truth).
  BYO keys live in `st.session_state` only (never written to disk).
- `test_providers.py` — smoke-tests the first model of each provider that has a key.
- `.env` — secrets (gitignored, NEVER commit). All keys optional; `.env.example` shows shape.

## Provider notes (learned the hard way)
- Default dev provider is **groq** (free). Google's free Gemini tier is **blocked in the
  EU/Sweden** (`limit: 0`), so Gemini needs billing (user has ~120 SEK credit).
- `gemini-2.0-flash` is **dead for new users** (404) — use `gemini-2.5-flash` (or
  `gemini-2.5-flash-lite` for near-zero cost). `groq/llama-3.3-70b-versatile` works.
- macOS: raw `urllib` HTTPS fails with a cert error — use litellm/httpx (bundles certs).

## Git
- Remote `origin` → git@github.com:mohidhayee/connectai.git (SSH key, no passphrase).
- `git push` works seamlessly. Commit at the end of each phase.
