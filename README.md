# ConnectAI

Connect AI agents from **different providers** — OpenAI, Anthropic, Google Gemini — into a
team that collaborates on a shared task. Use each model for what it's best at, together.

> 🚧 Early work in progress. Built in public.

## Status

- [x] Phase 0 — Project setup
- [x] Phase 1 — Multi-provider core (one interface for all providers)
- [ ] Phase 2 — Two-agent collaboration engine
- [ ] Phase 3 — Simple web UI
- [ ] Phase 4 — Open-source launch

## Quickstart (dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then paste your free Gemini key into .env
python hello.py
```

Get a free Gemini API key at https://aistudio.google.com/apikey — no credit card needed.

## License

MIT
