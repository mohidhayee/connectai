"""
manager.py — "Manager Mode" for ConnectAI.

A second way for the team to collaborate. Instead of taking fixed round-robin
turns over a shared scratchpad (that's `orchestrator.py`), one agent is the
**Manager** (the lead). The Manager reads the task, decides *which* worker should
do *what*, hands out one subtask at a time, and finally **synthesises** the
workers' contributions into a single answer. The Manager decides; the workers
advise. That gives us one source of truth for the final answer.

Why a whole module for this? Because the hard part isn't the happy path — it's
behaving safely on *every* input: never looping forever, never spending more than
a set budget, never crashing because a model returned messy text. Those guardrails
are the point, so they get their own home here (round-robin stays in
orchestrator.py, untouched).

────────────────────────────────────────────────────────────────────────────
THE DECISION PROTOCOL (the linchpin)
────────────────────────────────────────────────────────────────────────────
The Manager never talks to us in free-form prose that we'd have to guess at.
Every turn it must reply with exactly ONE JSON object, one of two shapes:

    {"action": "delegate", "to": "<worker name>", "instruction": "...", "reason": "..."}
    {"action": "finish",   "final_answer": "..."}

Structured JSON is what makes the control loop reliable: we can validate it,
and if it's malformed we can hand the error back and ask again, instead of
letting bad text derail everything.

Models are messy, though — they wrap JSON in ```code fences```, add "Sure, here's
my decision:" before it, or forget a key. So `parse_decision()` below is written
to be forgiving about the *wrapping* but strict about the *shape*. This file
(Step 1) implements that parser and its schema; the Manager loop that uses it is
added in the next step.
"""

import json
import re

import providers


# ── Tunables (the safety limits live here; the loop reads these) ─────────────────
DEFAULT_MAX_STEPS = 12               # hard cap on Manager decisions in one run
DEFAULT_MAX_COST_USD = 0.50          # hard $ cap; checked before every model call
DEFAULT_MAX_RETRIES = 3              # how many times to re-ask after malformed JSON
DEFAULT_MAX_CALLS_PER_WORKER = 4     # stop the lead hammering one worker in a loop
DEFAULT_STALL_LIMIT = 2              # consecutive no-progress steps before we stop

# When showing the Manager the work so far, cap each worker output so the prompt
# (and cost) stays bounded as the transcript grows. Full outputs are still kept
# for the final answer and the UI — this only trims the Manager's working view.
_TRANSCRIPT_OUTPUT_CAP = 1200


# ── The decision schema ─────────────────────────────────────────────────────────
# A Manager decision is always one of these two actions. Anything else is invalid.
VALID_ACTIONS = ("delegate", "finish")


class DecisionParseError(ValueError):
    """Raised when the Manager's reply can't be turned into a valid decision.

    The message is deliberately human-readable and safe to feed BACK to the
    Manager on a retry, e.g. '"action" must be one of [...]'. That feedback loop
    is how a model corrects itself instead of crashing ours.
    """


def parse_decision(raw, *, valid_workers=None):
    """Turn the Manager's raw text reply into a validated decision dict.

    Args:
        raw:            the Manager's raw reply (a string, possibly messy).
        valid_workers:  optional list of worker names. If given, a "delegate"
                        must target one of them. The match is case-insensitive
                        and the result is normalised to the configured spelling
                        (so "writer" → "Writer").

    Returns one of:
        {"action": "delegate", "to": <name>, "instruction": <str>, "reason": <str>}
        {"action": "finish",   "final_answer": <str>}

    Raises:
        DecisionParseError — if the reply isn't valid JSON, isn't a single object,
        or doesn't match the schema. The loop catches this and retries.
    """
    if not raw or not raw.strip():
        raise DecisionParseError("Reply was empty. Respond with one JSON object only.")

    block = _extract_json_block(raw)

    try:
        data = json.loads(block)
    except json.JSONDecodeError as e:
        raise DecisionParseError(
            f"Not valid JSON ({e.msg}). Respond with ONLY one JSON object, no prose, "
            "no code fences."
        )

    if not isinstance(data, dict):
        raise DecisionParseError(
            'JSON must be a single object, e.g. {"action": "finish", "final_answer": "..."}.'
        )

    action = data.get("action")
    if action not in VALID_ACTIONS:
        raise DecisionParseError(
            f'"action" must be one of {list(VALID_ACTIONS)}; got {action!r}.'
        )

    if action == "finish":
        return _validate_finish(data)
    return _validate_delegate(data, valid_workers)


# ── Internal helpers ──────────────────────────────────────────────────────────--

def _extract_json_block(text):
    """Pull the most likely JSON object out of a model's raw reply.

    Models love to wrap JSON in prose ("Here's my decision:") or Markdown code
    fences (```json ... ```). We peel those off so json.loads gets a clean shot:
      1. strip a surrounding ```...``` fence if present, then
      2. take the substring from the first '{' to the last '}' (drops any
         leading/trailing chatter around the object).

    This isn't a guarantee the result is valid JSON — it just gives the parser
    the best candidate. Anything still broken is caught (and retried) upstream.
    """
    s = text.strip()

    # 1. A Markdown code fence, e.g. ```json\n{...}\n```  (the json tag is optional).
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()

    # 2. The outermost {...} span, so "blah {..} blah" → "{..}".
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        s = s[start:end + 1]

    return s


def _validate_finish(data):
    """Validate a {"action": "finish", ...} decision."""
    final = data.get("final_answer")
    if not isinstance(final, str) or not final.strip():
        raise DecisionParseError(
            'A "finish" decision needs a non-empty string "final_answer".'
        )
    return {"action": "finish", "final_answer": final.strip()}


def _validate_delegate(data, valid_workers):
    """Validate a {"action": "delegate", ...} decision."""
    to = data.get("to")
    instruction = data.get("instruction")

    if not isinstance(to, str) or not to.strip():
        raise DecisionParseError(
            'A "delegate" decision needs a non-empty string "to" (a worker name).'
        )
    if not isinstance(instruction, str) or not instruction.strip():
        raise DecisionParseError(
            'A "delegate" decision needs a non-empty string "instruction".'
        )

    to = to.strip()
    if valid_workers is not None:
        match = _match_worker(to, valid_workers)
        if match is None:
            names = ", ".join(valid_workers) or "(none configured)"
            raise DecisionParseError(
                f"Unknown worker {to!r}. Choose exactly one of: {names}."
            )
        to = match

    # `reason` is optional — it's for the human watching, not the control flow.
    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = str(reason)

    return {
        "action": "delegate",
        "to": to,
        "instruction": instruction.strip(),
        "reason": reason.strip(),
    }


def _match_worker(name, workers):
    """Case-insensitive match of `name` against worker names.

    Returns the worker's canonical spelling (so the loop always uses the exact
    configured name), or None if there's no match.
    """
    lowered = name.strip().lower()
    for w in workers:
        if w.lower() == lowered:
            return w
    return None


def _normalize_instruction(text):
    """Lower-case and collapse whitespace, so trivially different phrasings of the
    same subtask are recognised as duplicates (no-progress detection)."""
    return " ".join((text or "").lower().split())


def _guardrail(name, step, detail):
    """Build a 'guardrail' event — a safety limit firing — for the UI/CLI/tests."""
    return {"type": "guardrail", "name": name, "step": step, "detail": detail}


def _note(step, to, instruction, reason, message):
    """A synthetic transcript record (no worker actually ran) recording WHY a
    delegate was refused, so the Manager sees it and adjusts next turn."""
    return {"step": step, "to": to, "instruction": instruction, "reason": reason,
            "output": "", "error": message}


# ══════════════════════════════════════════════════════════════════════════════
# THE MANAGER LOOP
# ══════════════════════════════════════════════════════════════════════════════
# run_manager() is written as a GENERATOR: it `yield`s a small dict for every
# thing that happens (a decision, a worker reply, the final answer). One loop then
# feeds three callers — the CLI prints the events, the Streamlit UI renders them
# live as a timeline, and the tests assert on them. No duplicated loop logic.
#
# Note on context: the Manager and workers are driven with providers.ask() and a
# transcript WE build and keep compact — not the stateful Agent.history (which
# would grow every turn and blow up cost). The Agent objects still carry the
# name / model / role / api_key; we just control exactly what each one sees.


def run_manager(manager, workers, task, *,
                max_steps=DEFAULT_MAX_STEPS,
                max_cost_usd=DEFAULT_MAX_COST_USD,
                max_retries=DEFAULT_MAX_RETRIES,
                max_calls_per_worker=DEFAULT_MAX_CALLS_PER_WORKER,
                stall_limit=DEFAULT_STALL_LIMIT):
    """Run Manager Mode on a task, yielding events as they happen.

    Args:
        manager:               the lead Agent (coordinates; never writes content).
        workers:               worker Agents the lead can delegate to (>= 1).
        task:                  the user's task, as plain text.
        max_steps:             hard cap on Manager decisions (anti-infinite-loop).
        max_cost_usd:          hard $ cap; checked before each model call.
        max_retries:           re-asks allowed on malformed Manager JSON.
        max_calls_per_worker:  cap on how often one worker can be used.
        stall_limit:           consecutive no-progress steps before we force-stop.

    Yields dicts with a "type":
        start            — run is beginning (manager, workers, task, caps)
        manager_decision — the Manager decided (decision, raw, attempts, error)
        worker_result    — a worker replied (worker, output, error, cost)
        guardrail        — a safety limit fired (name, detail) — observable!
        synthesis        — we're building a best-effort answer after a forced stop
        final            — the final answer (answer, finish_reason, steps, cost)

    The run ALWAYS ends with a "final" event carrying a non-empty answer — even
    if the Manager misbehaves, a worker fails, or a cap trips. That guarantee is
    the whole point. Each guardrail below is paired with a forced test in
    test_manager.py.
    """
    worker_by_name = {w.name: w for w in workers}
    transcript = []                              # delegation records (see _run_worker)
    worker_calls = {w.name: 0 for w in workers}  # per-worker call counter
    seen_instructions = set()                    # (worker, normalised instruction)
    steps_used = 0
    stall = 0                                    # consecutive no-progress steps
    finish_reason = None
    final_answer = None

    yield {"type": "start", "manager": manager.name, "workers": list(worker_by_name),
           "task": task, "max_steps": max_steps, "max_cost_usd": max_cost_usd,
           "max_calls_per_worker": max_calls_per_worker}

    # Defensive: no workers means nothing to coordinate. Don't crash — finish.
    if not workers:
        final_answer = "No worker agents were configured, so there was nothing to coordinate."
        yield {"type": "final", "answer": final_answer, "finish_reason": "no_workers",
               "steps": 0, "cost": providers.total_cost()}
        return

    while steps_used < max_steps:
        # GUARDRAIL: dollar cap. A Manager call itself costs money, so check first.
        if providers.total_cost() >= max_cost_usd:
            finish_reason = "cost_cap"
            yield _guardrail("cost_cap", steps_used,
                             f"cost ${providers.total_cost():.4f} reached cap ${max_cost_usd:.2f}")
            break

        steps_used += 1

        # 1. Ask the Manager for its next decision (validated JSON, with retries).
        result = decide(manager, task, transcript, workers, max_retries=max_retries)
        decision = result["decision"]
        yield {"type": "manager_decision", "step": steps_used, "decision": decision,
               "raw": result["raw"], "attempts": result["attempts"],
               "error": result["error"], "cost": providers.total_cost()}

        # 2. Couldn't get a valid decision after all retries → stop gracefully.
        if decision is None:
            finish_reason = "parse_failures"
            break

        # 3. Manager says we're done — take its answer as the final answer.
        if decision["action"] == "finish":
            final_answer = decision["final_answer"]
            finish_reason = "manager_finished"
            break

        # ── It's a delegate. Run the no-progress guardrails BEFORE spending on it.
        name = decision["to"]               # already validated to a real worker
        instruction = decision["instruction"]

        # GUARDRAIL: per-worker call cap. Don't let the lead hammer one worker.
        if worker_calls[name] >= max_calls_per_worker:
            stall += 1
            yield _guardrail("worker_cap", steps_used,
                             f"{name} hit its call cap ({max_calls_per_worker})")
            transcript.append(_note(steps_used, name, instruction, decision["reason"],
                                    f"{name} has reached its call limit "
                                    f"({max_calls_per_worker}). Pick another worker or finish."))
            if stall >= stall_limit:
                finish_reason = "stalled"
                break
            continue

        # GUARDRAIL: no-progress / duplicate instruction.
        key = (name.lower(), _normalize_instruction(instruction))
        if key in seen_instructions:
            stall += 1
            yield _guardrail("duplicate", steps_used,
                             f"repeat subtask to {name} — no new progress")
            transcript.append(_note(steps_used, name, instruction, decision["reason"],
                                    "This exact subtask was already requested. "
                                    "Do something new or finish."))
            if stall >= stall_limit:
                finish_reason = "stalled"
                break
            continue
        seen_instructions.add(key)

        # GUARDRAIL: dollar cap again — the decide() call may have pushed us over.
        if providers.total_cost() >= max_cost_usd:
            finish_reason = "cost_cap"
            yield _guardrail("cost_cap", steps_used,
                             f"cost ${providers.total_cost():.4f} reached cap ${max_cost_usd:.2f}")
            break

        # 4. Run the worker and record the result.
        worker = worker_by_name[name]
        output, error = _run_worker(worker, task, instruction, transcript)
        worker_calls[name] += 1
        transcript.append({
            "step": steps_used, "to": name, "instruction": instruction,
            "reason": decision["reason"], "output": output, "error": error,
        })
        yield {"type": "worker_result", "step": steps_used, "worker": name,
               "model": worker.model, "instruction": instruction,
               "reason": decision["reason"], "output": output, "error": error,
               "cost": providers.total_cost()}

        # Track progress: a worker that returns real content resets the stall
        # counter; an empty reply counts as a stall (no-progress).
        if error or not output.strip():
            stall += 1
            if stall >= stall_limit:
                finish_reason = "stalled"
                break
        else:
            stall = 0
    else:
        # while-loop ran the full count without a break → we hit the step cap.
        finish_reason = "max_steps"

    # 5. If the Manager never produced a final answer (any forced stop), build one
    #    from whatever work exists. This is the always-terminate guarantee.
    if final_answer is None:
        yield {"type": "synthesis", "reason": finish_reason}
        if finish_reason == "cost_cap":
            # We're over budget — assemble deterministically, NO extra paid call.
            final_answer = _best_effort_from_transcript(transcript)
        else:
            final_answer = synthesize(manager, task, transcript, reason=finish_reason)

    yield {"type": "final", "answer": final_answer, "finish_reason": finish_reason,
           "steps": steps_used, "cost": providers.total_cost()}


def run_manager_collect(manager, workers, task, **kwargs):
    """Convenience: run the loop to completion and return (final_event, events).

    Handy for the CLI and tests, which want the whole result, not a live stream.
    """
    events = []
    for event in run_manager(manager, workers, task, **kwargs):
        events.append(event)
    final = next((e for e in reversed(events) if e["type"] == "final"), None)
    return final, events


# ── The Manager's decision step (ask → parse → validate → retry → give up) ──────--

def decide(manager, task, transcript, workers, *, max_retries=DEFAULT_MAX_RETRIES):
    """Ask the Manager for its next decision and validate it.

    Returns a dict: {"decision", "raw", "attempts", "error"}.
      - decision: a validated decision dict, or None if every attempt failed.
      - raw:      the Manager's last raw reply (for the UI / debugging).
      - attempts: how many model calls it took.
      - error:    the last error message, if any.

    On malformed JSON we feed the parser's (human-readable) error back to the
    Manager and ask again, up to max_retries. If it still can't comply, we return
    decision=None so the caller falls back to synthesising a best-effort answer —
    a misbehaving Manager can never hang or crash the loop.
    """
    system = _build_manager_system(manager, workers)
    base_user = _build_manager_user(task, transcript)
    worker_names = [w.name for w in workers]

    feedback = ""
    last_error = None
    raw = ""

    for attempt in range(1, max_retries + 1):
        user = base_user + feedback
        try:
            raw = providers.ask(prompt=user, model=manager.model,
                                system=system, api_key=manager.api_key)
        except providers.ProviderError as e:
            # The provider itself failed (bad key, network, etc.). Retrying the
            # exact same call rarely helps, so stop and let the caller synthesise.
            return {"decision": None, "raw": "", "attempts": attempt, "error": str(e)}

        try:
            decision = parse_decision(raw, valid_workers=worker_names)
            return {"decision": decision, "raw": raw, "attempts": attempt, "error": None}
        except DecisionParseError as e:
            last_error = str(e)
            feedback = (
                f"\n\n⚠ Your previous reply could not be used: {e}\n"
                "Reply with ONLY one valid JSON object — no prose, no code fences."
            )

    return {"decision": None, "raw": raw, "attempts": max_retries, "error": last_error}


# ── Running a worker (stateless, curated context) ───────────────────────────────--

def _run_worker(worker, task, instruction, transcript):
    """Run one worker on one subtask. Returns (output, error).

    The worker sees the overall task, its specific instruction, and ONLY the most
    recent prior output (the thing it's most likely to build on) — not the whole
    history. If the worker's provider errors, we capture it as `error` and return
    an empty output instead of crashing: the Manager will see the failure in the
    transcript next turn and can route around it.
    """
    prior = next((r["output"] for r in reversed(transcript) if r.get("output")), None)
    user = _build_worker_prompt(task, instruction, prior)
    try:
        output = providers.ask(prompt=user, model=worker.model,
                               system=worker.role, api_key=worker.api_key)
        return output.strip(), None
    except providers.ProviderError as e:
        return "", str(e)


# ── Synthesising the final answer (best effort, always returns something) ───────--

def synthesize(manager, task, transcript, *, reason=""):
    """Ask the Manager to write the final answer from the work so far.

    Used whenever the loop is forced to stop before the Manager said "finish"
    (step cap, malformed output, etc.). If even this call fails or comes back
    empty, we fall back to a deterministic answer assembled straight from the
    transcript — so the run NEVER ends without an answer.
    """
    system = _build_synth_system()
    user = _build_synth_user(task, transcript, reason)
    try:
        answer = providers.ask(prompt=user, model=manager.model,
                               system=system, api_key=manager.api_key)
        if answer.strip():
            return answer.strip()
    except providers.ProviderError:
        pass
    return _best_effort_from_transcript(transcript)


def _best_effort_from_transcript(transcript):
    """A last-resort answer built from worker outputs, with no extra model call."""
    outputs = [r for r in transcript if r.get("output")]
    if not outputs:
        return ("The team couldn't produce an answer within the limits set. "
                "Try again with a higher step or cost budget, or a clearer task.")
    return "\n\n".join(f"**{r['to']}:**\n{r['output']}" for r in outputs)


# ── Prompt builders ─────────────────────────────────────────────────────────────--

def _build_manager_system(manager, workers):
    """The Manager's system prompt: who it is, its team, and the strict protocol.

    Note: in Manager Mode the lead's *configured* role text is intentionally
    replaced by these coordination instructions (its name and model still apply).
    The job of the lead is fixed — coordinate and emit JSON — so we don't let a
    "you are a poet" role prompt talk it out of returning valid decisions.
    """
    roster = "\n".join(f'  - "{w.name}": {_short(w.role, 160)}' for w in workers)
    names = ", ".join(f'"{w.name}"' for w in workers)
    return (
        f"You are {manager.name}, the LEAD of a small AI team. You do NOT do the "
        "work yourself — you break the task down, delegate subtasks to the worker "
        "best suited to each, and finally deliver one synthesised answer.\n\n"
        f"YOUR WORKERS:\n{roster}\n\n"
        "EVERY turn, reply with EXACTLY ONE JSON object and nothing else — no "
        "prose, no markdown code fences. It must be one of:\n\n"
        '  {"action": "delegate", "to": "<worker name>", "instruction": "<the subtask>", "reason": "<short why>"}\n'
        '  {"action": "finish", "final_answer": "<the complete answer to the task>"}\n\n'
        "RULES:\n"
        f'- "to" must be exactly one of: {names}.\n'
        "- Delegate ONE concrete subtask at a time, to the worker whose described "
        "skill fits it best. Read what workers have already returned before "
        "deciding, and never re-ask for work that's already done.\n"
        "- Workers do NOT see the full history — only your instruction and the most "
        "recent result. Put any specific details they need (facts to use, text to "
        "edit) directly in the instruction.\n"
        "- When the task is fully handled, choose \"finish\" and put the COMPLETE, "
        "self-contained answer in \"final_answer\" — synthesise the workers' "
        "contributions into one coherent reply; if they disagree, reconcile it. "
        "Do not just point at their work."
    )


def _build_manager_user(task, transcript):
    """The per-turn message: the task + a compact view of the work so far."""
    return (
        f"TASK:\n{task}\n\n"
        f"WORK SO FAR:\n{_render_transcript(transcript)}\n\n"
        "What is your next decision? Reply with ONE JSON object only."
    )


def _build_worker_prompt(task, instruction, prior_output):
    """The message a worker receives for one subtask."""
    msg = f"You're part of a team working on this overall TASK:\n{task}\n\n"
    if prior_output:
        msg += (
            "RELEVANT WORK ALREADY DONE (build on it; don't repeat it):\n"
            f"{_short(prior_output, 2000)}\n\n"
        )
    msg += (
        f"YOUR SUBTASK (assigned by the lead):\n{instruction}\n\n"
        "Do exactly this subtask — focused and concrete. Don't try to do the "
        "whole task or anyone else's part."
    )
    return msg


def _build_synth_system():
    return (
        "You are the lead, delivering the FINAL answer to the task. Use the team's "
        "work below. Reconcile any contradictions and prefer well-supported content. "
        "Write the complete answer directly — do not describe the process or mention "
        "the workers by name. Output only the final answer."
    )


def _build_synth_user(task, transcript, reason):
    note = ""
    if reason and reason != "manager_finished":
        note = (
            f"\n(Note: the run stopped early — reason: {reason}. Do the best you can "
            "with the work that exists.)\n"
        )
    return (
        f"TASK:\n{task}\n\n"
        f"THE TEAM'S WORK:\n{_render_transcript(transcript)}\n{note}\n"
        "Write the final answer now."
    )


def _render_transcript(transcript):
    """Compact, readable view of the work so far, for the Manager's prompt."""
    if not transcript:
        return "Nothing yet — this is your first decision."
    lines = []
    for r in transcript:
        lines.append(f'[Step {r["step"]}] You delegated to {r["to"]}: {r["instruction"]}')
        if r.get("error"):
            lines.append(f'   → {r["to"]} FAILED: {r["error"]} (try another worker or finish)')
        else:
            lines.append(f'   → {r["to"]} returned:\n{_short(r["output"], _TRANSCRIPT_OUTPUT_CAP)}')
    return "\n".join(lines)


def _short(text, limit):
    """Trim text to `limit` chars with an ellipsis, so prompts stay bounded."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …[trimmed]"
