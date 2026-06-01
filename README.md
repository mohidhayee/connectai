# 🤝 ConnectAI

**Connect AI agents from different providers into a team that collaborates on one task.**

Most tools lock you into a single AI company. ConnectAI does the opposite: it lets a
Groq model and a Google Gemini model (with OpenAI and Anthropic coming) work *together*
on the same task — passing a shared scratchpad back and forth — so you can use each model
for what it's best at. It's a small, hand-rolled, open-source experiment in cross-vendor
AI collaboration.

> 🚧 Built in public by a beginner, one phase at a time. Feedback very welcome.

<!-- TODO: add a screenshot or GIF of the Streamlit app here, e.g. ![ConnectAI demo](docs/demo.png) -->

## What it does

You type a task ("write a short workout guide"). Two agents take turns:

- **Planner** (Groq) breaks the task into a clear structure.
- **Writer** (Gemini) reads that structure and expands it into the finished piece.

They collaborate through a shared *scratchpad* — a running document both can read and add
to — until the work is done. A live cost meter shows exactly how little it costs (a typical
run is well under one US cent).

## Quickstart

You only need **one free API key** (Groq) to run everything.

```bash
# 1. Set up a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your key
cp .env.example .env          # then paste your free Groq key into .env
```

Get a free Groq API key at **https://console.groq.com/keys** — no credit card needed.

```bash
# 3a. Run the web app (recommended)
streamlit run app.py

# 3b. ...or run it in the terminal
python run.py "write a short guide to staying focused while studying"
```

**Bring your own keys.** ConnectAI never ships with API keys — you use your own, stored
locally in `.env` (which is gitignored and never committed). You only pay your AI
providers directly, and Groq's free tier means you can try the whole thing for $0.

## How it works

Five small files, each with one job:

| File | Role |
|------|------|
| `config.py` | The address book — maps friendly names ("groq") to real model IDs. The one place to change models. |
| `providers.py` | The universal translator — one `ask()` function calls any provider and tracks cost. |
| `agent.py` | One team member — an `Agent` has a name, a provider, a role, and its own memory. |
| `orchestrator.py` | The chairperson — runs the turn-by-turn loop over a shared scratchpad. |
| `app.py` / `run.py` | The two front doors — a Streamlit web UI and a terminal CLI. |

It's deliberately hand-rolled (no agent frameworks) so the logic stays readable and easy
to learn from.

## Roadmap

- [x] **Phase 0** — Project setup
- [x] **Phase 1** — Multi-provider core (one interface for all providers + cost tracking)
- [x] **Phase 2** — Two-agent collaboration engine
- [x] **Phase 3** — Streamlit web UI
- [ ] **Phase 4** — Open-source launch (this README, a live demo, community feedback)
- [ ] **Phase 5** — Listen, iterate, decide

## Contributing & feedback

This is an early experiment and the big open question is simply: **would you use this?**
If you try it, open an issue with what worked, what didn't, and what's missing. That
feedback is the whole point right now.

## License

[MIT](LICENSE) — free to use, modify, and share.
