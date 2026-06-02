# 🤝 ConnectAI

**Build a team of AI agents from different providers — each on the model it does best — and watch them collaborate on one task.**

There's no single "best" AI model: Claude is great at coding, Gemini at reasoning,
GPT is a strong all-rounder, Groq's Llama is free and fast. ConnectAI lets you put
them on the *same* team — e.g. **Opus as the coder ↔ Gemini as the reasoner ↔ GPT as
the all-rounder** — passing a shared scratchpad back and forth until the work is done.
It's a small, hand-rolled, open-source experiment in cross-vendor AI collaboration.

> 🚧 Built in public, one phase at a time. Feedback very welcome.

<!-- TODO: add a screenshot or GIF of the app here, e.g. ![ConnectAI demo](docs/demo.png) -->

## What makes it different

- **Mix providers and models.** Pick any model per agent from a curated list (with
  "what it's best at" tags) — or type any custom model id. Combine their strengths.
- **2–4 agents.** Add up to four collaborators that take turns on a shared scratchpad.
- **Two collaboration modes.** *Round-robin* (agents take turns) or **Manager mode** — a
  lead agent delegates subtasks to the others and synthesises the final answer, with every
  decision shown live and hard caps on steps and cost.
- **Bring your own keys.** Paste your own API keys; they live only in your browser
  session — never saved to disk, never logged. You pay your providers directly.
- **Live cost meter.** See exactly what each run costs (often a fraction of a cent).
- **Runs free.** Groq's free tier means you can try the whole thing for $0.

## Two ways to collaborate

- **🔁 Round-robin** — agents take turns adding to a shared scratchpad until the work is
  done. Simple, and great for drafting and refining together.
- **🧭 Manager mode** — one agent is the **lead**: it reads the task, **delegates** focused
  subtasks to the workers, then **synthesises** their work into one final answer. It's built
  for reliability, not just demos:
  - the lead's decisions are **structured JSON** (validated, with automatic retries),
  - every run has a **step cap *and* a dollar cap**,
  - repeated/duplicate work and stalls are detected and stopped,
  - it **always returns a best-effort answer**, even if a worker fails or a cap trips,
  - and every decision, delegation and guardrail is shown **live**, so you can see *how* the
    team worked (an optional one-pass quality critic can review each worker's output too).

  Pick the mode — and which agent is the lead — in the **Team** tab.

## Quickstart

```bash
# 1. Set up a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Add a key (for local dev). The web app can also take keys in the browser.
cp .env.example .env          # then paste your free Groq key into .env
```

Get a free Groq API key at **https://console.groq.com/keys** — no credit card needed.

```bash
# 3a. Run the web app (recommended)
streamlit run app.py

# 3b. ...or run it in the terminal
python run.py "write a short guide to staying focused while studying"
python run.py --manager "plan a balanced 3-day Stockholm itinerary"   # manager mode
```

**Bring your own keys.** In the web app, paste keys in the sidebar — they're kept in
your session only. For local/CLI use, keys come from `.env` (gitignored, never committed).
Groq is free, so you can try everything at no cost.

## How it works

Small, readable files, each with one job:

| File | Role |
|------|------|
| `config.py` | The model catalog — providers + a curated list of models (with strengths). The one place to add/retire models. |
| `providers.py` | The universal translator — one `ask(model=...)` calls any model (via `litellm`), tracks cost, resolves the API key (yours or from `.env`). |
| `agent.py` | One team member — an `Agent` has a name, a model, a role, an optional key, and its own memory. |
| `orchestrator.py` | The chairperson — runs the round-robin over 2–4 agents on a shared scratchpad. |
| `manager.py` | The lead — Manager mode's delegate → work → synthesise loop: JSON decisions, retries, and every safety cap (steps, cost, per-worker, no-progress). |
| `app.py` / `run.py` | The two front doors — a Streamlit web UI and a terminal CLI. |

It's deliberately hand-rolled (no agent frameworks) so the logic stays readable and
easy to learn from. `litellm` underneath means ~any model from any provider works
through the same interface.

📖 **Want the full story?** [How ConnectAI was built](docs/HOW_IT_WAS_BUILT.md) covers
the stack, the phase-by-phase journey, the decisions, and a deep-dive on Manager
Mode's reliability engineering — including how every failure mode was tested.

## Roadmap

- [x] **Phase 0** — Project setup
- [x] **Phase 1** — Multi-provider core (one interface + cost tracking)
- [x] **Phase 2** — Two-agent collaboration engine
- [x] **Phase 3** — Streamlit web UI
- [x] **Phase 4** — Open-source launch prep (docs, MIT license)
- [x] **Phase 4.5** — BYO keys · per-model picker · 2–4 agents
- [x] **Manager mode** — a lead delegates + synthesises; structured, cost-capped, reliable *(you're looking at it)*
- [ ] **Phase 5** — Live demo, share, listen, iterate

## Contributing & feedback

This is an early experiment and the big open question is simply: **would you use this?**
If you try it, open an issue with what worked, what didn't, and what's missing. That
feedback is the whole point right now.

## License

[MIT](LICENSE) — free to use, modify, and share.
