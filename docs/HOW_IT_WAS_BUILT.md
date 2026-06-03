# How ConnectAI Was Built

A developer-facing walkthrough of *what* ConnectAI is, *how* it was built, the
decisions behind it, and the methods used — with a deep-dive on the most
interesting part, **Manager Mode** and its reliability engineering.

This is a "how it was made" companion to the [README](../README.md) (which covers
*using* it). Everything here describes what's actually in the repo today.

---

## 1. What ConnectAI is

ConnectAI puts AI agents from **different providers** (Groq, Google Gemini, OpenAI,
Anthropic, Perplexity) onto one team that collaborates on a single task — the idea
being that there's no single "best" model, so you use each for what it's good at.

There are two collaboration modes:

- **🔁 Round-robin** — agents take turns adding to a shared scratchpad until the
  work is done.
- **🧭 Manager mode** — one agent is the **lead**: it delegates focused subtasks to
  worker agents and synthesises their work into the final answer.

It runs as both a **Streamlit web app** and a **terminal CLI**.

---

## 2. Guiding principles

These shaped every decision in the codebase:

1. **Hand-rolled, no agent frameworks.** No LangChain/LangGraph/etc. The control
   flow is plain Python you can read top to bottom. This was a deliberate choice to
   keep the project learnable and to *own* the logic that matters (especially the
   guardrails) instead of hiding it behind an abstraction.
2. **Provider-agnostic by design.** One function calls any model; providers are
   swappable; the model catalog lives in one file.
3. **Reliability over demo.** Especially in Manager Mode — behaving well on *every*
   input (malformed output, failures, runaway loops, cost spirals) was treated as
   the actual job, not an afterthought.
4. **Keep dev cost ~$0.** Built and tested almost entirely on Groq's free tier plus
   Gemini's cheap tier. Every guardrail has a logic test that runs **offline** with
   no model calls at all.
5. **Incremental, tested, committed.** Built in small steps; each step verified and
   committed before the next.

### Development approach (the method)

The code was written incrementally with **Claude Code** as the implementer, driven
by a human directing the design and decisions. The working method is worth noting
because it *is* part of how this was made:

- a single instance (not a swarm of agents — that burns far more tokens),
- one feature step at a time, each ending in a commit,
- and — the part that paid off most — **testing each failure mode by deliberately
  forcing it** before moving on (see §7).

---

## 3. Tech stack

| Tool | Role | Why |
|------|------|-----|
| **Python 3.12** | Language | Simple, readable, ubiquitous. |
| **[litellm](https://github.com/BerriAI/litellm)** | Provider abstraction | One API to call ~any model from any provider, with cost estimation built in. It's the reason adding a provider is trivial. |
| **[Streamlit](https://streamlit.io/)** | Web UI | Fastest way to a real interactive app in pure Python — no JS/HTML build step. |
| **python-dotenv** | Config | Loads API keys from a gitignored `.env`. |
| **Providers** | The models | Groq (free Llama), Google Gemini (cheap), OpenAI, Anthropic, Perplexity (web search). |

No database, no backend service, no framework — just a handful of small Python
files. Bring-your-own-key secrets live only in the browser session (never written
to disk).

---

## 4. The build journey

ConnectAI was built in phases. Each added one capability and ended in a commit.

| Phase | What was added |
|-------|----------------|
| **0 — Setup** | Repo, virtualenv, two providers wired up, pushed to GitHub. |
| **1 — Multi-provider core** | The single `providers.ask(...)` entry point + cost tracking. The foundation everything else calls. |
| **2 — Collaboration engine** | `Agent`, the round-robin `orchestrator`, and the `run.py` CLI — two agents passing a shared scratchpad. |
| **3 — Web UI** | The Streamlit `app.py`. |
| **4 — Launch prep** | Real `README.md`, MIT `LICENSE`, `.env.example`. |
| **4.5 — Flexibility** | Bring-your-own-keys, a per-agent model picker across 5 providers, 2–7 agents, a tabbed UI (later redesigned into a sidebar + chat-bubble layout). |
| **Manager Mode** | The lead-delegates-and-synthesises mode (the focus of this doc). |
| **5 — Next** | Live demo + community feedback (not done yet). |

### Lessons learned the hard way (provider quirks)

Real notes from the build, the kind that cost an hour each:

- **Gemini's free tier is blocked in the EU/Sweden** (`limit: 0`) — it needs
  billing enabled, even for the "free" models.
- **`gemini-2.0-flash` returns 404 for new users** — `gemini-2.5-flash` (or
  `-flash-lite` for near-zero cost) is the working choice.
- **On macOS, raw `urllib` HTTPS fails with a certificate error.** Going through
  litellm/httpx (which bundle certs) sidesteps it — another point for the
  single-`ask()` abstraction.

---

## 5. Architecture

Small files, each with one job:

| File | Role |
|------|------|
| `config.py` | The catalog — `PROVIDERS` (label/emoji/key env/tier) and `MODELS` (a curated list per provider with a "what it's best at" tag). The **one** place to add or retire a model. |
| `providers.py` | The universal translator — `ask(prompt, *, model, system, messages, api_key)` is the only way anything calls a model. It infers the provider from the model id, resolves the key (passed in, else from `.env`), and tracks running cost via `total_cost()`. **Nothing calls litellm directly.** |
| `agent.py` | One team member — an `Agent` has a name, model, role (system prompt), optional key, and its own message history. |
| `orchestrator.py` | Round-robin mode — `run(agents, task, max_turns)` cycles agents over a shared scratchpad; an agent may only signal `DONE` at the end of a full round. |
| `manager.py` | Manager mode — see §6. |
| `app.py` / `run.py` | The two front doors — Streamlit web UI and terminal CLI. |
| `test_*.py` | The test suite — see §7. |

**The key design seam** is `providers.ask()`. Because every model call goes through
one function, provider-specific quirks, cost tracking, and key resolution all live
in one place — and the rest of the code never has to know which vendor it's talking
to.

---

## 6. Manager Mode — the reliability deep-dive

Round-robin is simple but dumb: agents take fixed turns regardless of what the task
needs. Manager Mode adds *real* coordination — but the entire challenge isn't making
it work once (that's easy), it's making it behave on **every** input: malformed
model output, worker failures, runaway loops, cost spirals, contradictory workers.
The reliability *is* the feature.

### 6.1 The shape

One agent is the **lead**. On each turn it makes one decision: delegate a subtask to
a worker, or finish. Workers do focused subtasks and return text. The lead
synthesises everything into the final answer. **The lead decides; the workers
advise** — so there's a single source of truth for the answer (this is the defense
against workers contradicting each other).

### 6.2 The linchpin: structured decisions, not prose

The lead never replies in free-form prose we'd have to guess at. It must return
**exactly one JSON object**, one of two shapes:

```json
{"action": "delegate", "to": "<worker>", "instruction": "...", "reason": "..."}
{"action": "finish",   "final_answer": "..."}
```

Structured JSON is what makes the control loop trustworthy: we can *validate* it,
and if it's wrong we can hand the error back and ask again. But models are messy —
they wrap JSON in ```` ```code fences ```` or prefix it with "Sure, here's my
decision:". So `parse_decision()` is **forgiving about the wrapping, strict about
the shape**:

1. strip a surrounding code fence if present,
2. take the substring from the first `{` to the last `}` (drops chatter around it),
3. `json.loads`,
4. validate `action` against the allowed set, validate required keys/types, and
   match the worker name (case-insensitively) against the real roster.

Anything wrong raises a `DecisionParseError` whose message is **safe to feed back to
the model** (e.g. `'"action" must be one of ['delegate', 'finish']'`). This parser
was the first thing built and has its own unit tests against fences, leading/
trailing prose, truncated JSON, missing keys, wrong actions, lists, bare strings,
and single-quoted pseudo-JSON.

`decide()` wraps the parser in a **retry loop**: on bad JSON it re-asks with the
error appended, up to `max_retries` (default 3). If the model still can't comply, it
gives up gracefully and the run falls back to synthesising an answer — a misbehaving
lead can never hang or crash the loop.

### 6.3 The loop is a generator

`run_manager(...)` is written as a Python **generator** that `yield`s a small event
dict for everything that happens:

```
start → manager_decision → worker_result → critique? → guardrail? → synthesis? → final
```

This is the trick that keeps the codebase honest: **one loop feeds three consumers.**
The CLI prints the events, the Streamlit UI renders them as a live timeline, and the
tests assert on them — with no duplicated control flow. (`run_manager_collect()`
drains the generator for callers that want the whole result at once.)

A nice side effect: every decision and delegation is **observable**, which is both a
debugging aid and a genuine selling point — users can see *how* the team worked.

### 6.4 The guardrails

Every loop has a budget and every forced stop still produces an answer. Each
guardrail below was implemented **and then tested by deliberately triggering it**.

| Failure mode | Guardrail | Default |
|---|---|---|
| Infinite delegation | **Step cap** | `max_steps = 12` |
| Cost spiral | **Dollar cap**, checked before *every* model call | `max_cost_usd = 0.50` |
| Hammering one worker | **Per-worker call cap** | `max_calls_per_worker = 4` |
| Going in circles | **No-progress / stall** (duplicate instruction or empty worker output) | `stall_limit = 2` |
| Malformed lead output | **Parser + retries**, then graceful fallback | `max_retries = 3` |
| A worker's API failing | Error captured into the transcript, loop continues | — |
| A transient provider error (rate limit, brief outage) | **Retried with backoff** at the `providers.ask` layer; if it persists, reported as `provider_error` | — |

Two details that matter:

- **The cost cap never spends to honor "always answer."** If the dollar cap (or a
  persistent provider error) is what stops a run, the final answer is assembled
  **deterministically from the transcript with no extra paid call** — making another
  model call would just overspend or fail again. Every *other* forced stop gets a
  proper LLM synthesis pass (we still have budget).
- **Honest finish reasons.** A run reports *why* it ended — and a provider failure
  (e.g. a rate limit) is labelled `provider_error`, not lumped in with malformed-JSON
  `parse_failures`. (A real lesson: free-tier rate limits, like Groq's
  tokens-per-minute cap, are common enough on long runs that both the retry and the
  honest label earned their place — transient ones are retried, persistent ones are
  named correctly.)
- **The cardinal guarantee:** a run *always* ends with a non-empty `final` event —
  even if the lead misbehaves, a worker crashes, and a cap trips, all at once.

When a guardrail refuses a delegation (e.g. a worker is capped), it doesn't just
drop it — it writes a note *into the transcript* so the lead sees the refusal on its
next turn and can route around it.

### 6.5 Context discipline (keeping cost bounded)

The lead and the workers are driven **statelessly** via `providers.ask()` over a
**compact transcript we build ourselves**, *not* the `Agent.history` that grows every
turn. Each worker sees only the task, its specific instruction, and the most recent
relevant output — never the whole history. Worker outputs are length-capped in the
lead's working view. This is the main reason cost stays bounded as a run gets longer.

### 6.6 The optional critic

Turned off by default: a one-pass quality check (`use_critic=True`) where the lead
reviews each worker's output and its verdict is fed back into the transcript. It's
**strictly one pass** (it can't loop), it's skipped when over the cost cap, and it
**fails open** — any error or unparseable verdict is treated as "accept," so a flaky
critic can never block a run.

### 6.7 Why hand-rolled (the framework decision)

Manager Mode is exactly the point where a framework like LangGraph *could* help. It
was deliberately built hand-rolled anyway, because the guardrails — the caps, the
retries, the graceful termination — **are** the feature, and a framework would hide
the very control flow we most needed to own (and learn from). The validation surface
is tiny (two actions, a few fields), so a ~30-line parser we own and unit-test beats
a dependency.

---

## 7. Testing methodology

This is the part most worth stealing. The philosophy: **prove the system fails
gracefully by making it fail** — and do it offline so it's free and deterministic.

- **`test_manager.py` (35 checks, offline, $0).**
  - The parser is hit with every messy input a model might produce.
  - For the loop, a **`FakeProvider`** stands in for `providers.ask` /
    `total_cost`. It scripts exactly what the "lead" and "workers" say, so each
    guardrail is **forced on purpose**: an infinite-delegation loop (→ stopped by
    the step cap), always-malformed JSON (→ retries exhausted → graceful answer), a
    worker crash (→ captured, loop survives), a duplicate-subtask stall, the
    per-worker cap, and the cost cap both already-over *and* crossed mid-run
    (asserting **no** extra paid synth call). Every case asserts a non-empty final
    answer.
- **`test_app.py` (6 checks, offline, $0).** Streamlit's `AppTest` drives the real
  UI in both modes with the model layer faked — asserting no exception, that the
  Manager timeline shows the delegation/worker reply/final answer, and that changing
  the lead reassigns the workers.
- **`test_providers.py` (live, ~free).** A smoke test that the first model of each
  configured provider actually answers.

A concrete payoff: during a real CLI test, **Gemini threw a genuine transient
`ServiceUnavailableError` mid-run**. The loop didn't crash — it recorded the
failure, the lead saw it in the transcript, re-delegated, the retry succeeded, and
the run finished cleanly. The guardrails earned their keep against a real outage,
not just a simulated one.

A small but instructive bug the AppTest caught: a Streamlit selectbox `format_func`
that read `st.session_state` crashed under `AppTest`, because the test harness calls
`format_func` *outside* a script run. The fix — pass it a plain local dict instead —
was both test-safe and simply cleaner code.

---

## 8. Cost discipline

The whole thing was built and tested for roughly **$0**:

- Default dev provider is **Groq** (free tier); **Gemini** (cheap) for a second
  voice.
- Every guardrail test is **offline** (a fake provider) — no spend at all.
- Live checks during the build cost **fractions of a cent** each.
- Manager Mode's dollar cap and bounded context keep real runs cheap by design.

---

## 9. Running it yourself

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste a free Groq key (console.groq.com/keys)

python test_manager.py        # 35 offline reliability checks ($0)
python test_app.py            # 6 offline UI checks ($0)

streamlit run app.py          # web UI: Team tab → Manager mode → pick the lead
python run.py --manager "plan a balanced 3-day Stockholm itinerary"
```

See the [README](../README.md) for the full quickstart and bring-your-own-key
details.
