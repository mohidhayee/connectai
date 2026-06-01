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
- 🔨 **Phase 4 (in progress)** — open-source launch. Done: real `README.md`, `LICENSE`
  (MIT), `.env.example` includes Groq. TODO: add a screenshot to README; deploy free demo
  to Streamlit Community Cloud; user posts to ≥3 communities (needs user's accounts).

Full build plan: `~/.claude/plans/lets-go-with-that-quirky-feather.md`
Strategy/market context: `~/.claude/projects/-Users-mohidhayee-Documents-ConnectAI/memory/`

## How to run
```bash
source .venv/bin/activate
python test_providers.py                   # confirm all providers work
python hello.py                            # Phase 0 smoke test
python run.py "your task here"             # Phase 2: two-agent collaboration
python run.py                              # interactive prompt
```

## Architecture (keep it this way)
- `config.py` — friendly provider name → model + API-key env var. **Change models only here.**
- `providers.py` — `ask(prompt, provider="groq", system=None)` is the ONE way to call any
  AI. Tracks cost via `total_cost()`. Never call litellm directly elsewhere.
- `test_providers.py` — smoke test for every provider in config.
- `.env` — secrets (gitignored, NEVER commit). `.env.example` shows the shape.

## Provider notes (learned the hard way)
- Default dev provider is **groq** (free). Google's free Gemini tier is **blocked in the
  EU/Sweden** (`limit: 0`), so Gemini needs billing (user has ~120 SEK credit).
- `gemini-2.0-flash` is **dead for new users** (404) — use `gemini-2.5-flash` (or
  `gemini-2.5-flash-lite` for near-zero cost). `groq/llama-3.3-70b-versatile` works.
- macOS: raw `urllib` HTTPS fails with a cert error — use litellm/httpx (bundles certs).

## Git
- Remote `origin` → git@github.com:mohidhayee/connectai.git (SSH key, no passphrase).
- `git push` works seamlessly. Commit at the end of each phase.
