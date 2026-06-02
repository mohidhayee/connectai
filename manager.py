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
