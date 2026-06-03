# ConnectAI — Project Guide for Claude Code

ConnectAI connects AI agents from **different providers** (Groq, Google Gemini, and
later OpenAI/Anthropic) into a team that collaborates on a shared task — using each
model for what it's best at. Two collaboration modes ship today: **round-robin**
(agents take turns on a shared scratchpad) and **Manager mode** (a lead agent
delegates subtasks to workers and synthesises the final answer).

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
- ✅ **Phase 4.5** — BYO keys + per-model picker (5 providers) + 2–7 agents + tabbed UI.
  All 5 keys (Groq/Gemini/OpenAI/Anthropic/Perplexity) live in `.env` and tested working.
- ✅ **Manager mode** — `manager.py`: a lead agent delegates subtasks + synthesises the final
  answer, with structured-JSON decisions, retries, step/cost/per-worker/no-progress caps,
  graceful always-an-answer termination, an optional 1-pass critic, and a live UI timeline.
  Round-robin kept fully working. Tests: `test_manager.py` (36 offline) + `test_app.py`
  (3) + offline retry tests in `test_providers.py`.
- ⏭️ **NEXT → Phase 5** — add a README screenshot (TODO marker is in `README.md`); deploy
  free demo to Streamlit Community Cloud; user posts to ≥3 communities (needs user accounts).

## Manager mode (SHIPPED — `manager.py`)
A second collaboration mode alongside round-robin. One agent is the **lead**: it reads the
task, **delegates** one subtask at a time to the best worker, and **synthesises** the final
answer (lead decides, workers advise). Reliability is the whole point:
- **Structured JSON decisions** (`parse_decision`): lead replies with `{"action":"delegate",
  "to","instruction","reason"}` or `{"action":"finish","final_answer"}`. The parser strips
  fences/prose and validates; `decide()` retries on bad JSON (feeding the error back), then
  falls back to synthesise. Never parse loose prose — this is the linchpin.
- **The loop is a generator** `run_manager(...)` yielding events (start / manager_decision /
  worker_result / critique / guardrail / synthesis / final). ONE loop feeds the CLI, the UI
  timeline, and the tests; `run_manager_collect()` drains it for CLI/tests.
- **Guardrails** (each force-tested; defaults: `max_steps=12`, `max_cost_usd=0.50`,
  `max_retries=3`, `max_calls_per_worker=4`, `stall_limit=2`): the dollar cap is checked
  before every call and, when hit, assembles the answer from the transcript with NO extra
  paid call; no-progress/stall = duplicate instruction or empty worker output. It ALWAYS
  ends with a non-empty answer. `finish_reason` is one of `manager_finished` / `max_steps` /
  `cost_cap` / `stalled` / `parse_failures` / `provider_error` (a model error such as a rate
  limit that outlived `providers.ask`'s retries) — `cost_cap` and `provider_error` both
  assemble deterministically rather than make a doomed extra call.
- **Context discipline**: lead + workers run statelessly via `providers.ask` over a compact
  transcript WE build (not `Agent.history`), so cost stays bounded.
- **Optional critic** (`use_critic`, default off): one bounded quality pass per worker output;
  fails OPEN, so it can never block a run.
- **UI/CLI**: Team tab = mode switch + lead picker; Run tab = live decision timeline + steps/
  cost-vs-cap. CLI: `python run.py --manager "task"`. Tunable defaults sit at the top of
  `manager.py`. Verify free on Groq + Gemini.

History: the original build brief is `~/.claude/plans/manager-mode-brief.md`.
Full build plan: `~/.claude/plans/lets-go-with-that-quirky-feather.md`
Strategy/market context: `~/.claude/projects/-Users-mohidhayee-Documents-ConnectAI/memory/`

## How to run
```bash
source .venv/bin/activate
python test_providers.py                   # confirm providers with keys work
python test_manager.py                     # Manager-mode logic tests (offline, free)
python test_app.py                         # Streamlit UI smoke tests (offline, free)
python run.py "your task here"             # CLI: round-robin collaboration
python run.py --manager "your task here"   # CLI: Manager mode (lead delegates + synthesises)
streamlit run app.py                       # web UI (mode switch, BYO keys, 2–7 agents, picker)
```

## Architecture (keep it this way)
- `config.py` — the catalog: `PROVIDERS` (label/emoji/key_env/tier) + `MODELS` (curated
  list per provider, each `{id,label,strength}`). **Add/retire models only here.**
- `providers.py` — `ask(prompt, *, model, system=None, messages=None, api_key=None)` is the
  ONE way to call any model. Provider is inferred from the model id (`provider_for`); key is
  the passed `api_key` else the provider's env var. Tracks cost via `total_cost()`. **Retries
  transient errors** (rate limits like Groq's free TPM cap, brief outages, timeouts) with a
  short backoff (`_RETRY_BACKOFF`) before raising `ProviderError`; non-transient errors fail
  fast. Never call litellm directly elsewhere.
- `agent.py` — `Agent(name, model, role, api_key=None)`; `.provider` is derived from model.
- `orchestrator.py` — `run(agents_list, task, max_turns)`; round-robin over 2–7 agents; an
  agent may only signal DONE at the end of a full round (`turn>=n and turn%n==0`).
- `manager.py` — Manager mode. `run_manager(manager, workers, task, *, max_steps,
  max_cost_usd, max_retries, max_calls_per_worker, stall_limit, use_critic)` is a generator
  of events; `decide()` (validated JSON + retries), `synthesize()` (best-effort with a
  deterministic fallback), `parse_decision()` (robust parser), and the caps live here.
  Round-robin stays in `orchestrator.py` — manager mode is additive.
- `app.py` — imports `_build_prompt`/`_DONE_SIGNAL` from orchestrator and `run_manager` from
  manager (one source of truth per mode). `build_agents()` is shared; `manager_timeline()`
  renders the Manager event stream. Mode switch + lead picker in the Team tab. BYO keys live
  in `st.session_state` only (never written to disk). Keep selectbox `format_func`s pure
  (no `st.session_state` reads) — AppTest calls them outside a script run.
- `test_providers.py` — smoke-tests the first model of each provider that has a key.
- `test_manager.py` — offline Manager-mode tests (parser + every guardrail, via a fake
  provider). `test_app.py` — offline Streamlit AppTest for both modes. Both free.
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
