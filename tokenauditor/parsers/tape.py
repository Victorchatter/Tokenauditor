"""agent-vcr tape reader.

A tape is JSONL of wire-level events with a `kind` and a `seq`:
`model_request`, `model_response`, `tool_call`, `tool_result`.

# ponytail: unlike the Claude Code parser, the prefix here is COUNTED, not
# inferred — a tape records the raw request body, so `system` and `tools` are
# read directly instead of being derived from "first turn's input minus first
# user message". Ceiling: only the Anthropic Messages and OpenAI
# chat-completions request shapes are understood; an exotic provider body
# falls back to counting the whole request once. Upgrade: per-provider body
# readers keyed on the `provider` field.
"""
import json

from . import Session, Turn
from ..counters import count_text, count_json, usage_total

_KINDS = {"model_request", "model_response", "tool_call", "tool_result"}


def _body(ev):
    """Tape bodies are either a JSON string or an already-decoded object."""
    b = ev.get("body")
    if isinstance(b, str):
        try:
            return json.loads(b)
        except json.JSONDecodeError:
            return None
    return b if isinstance(b, dict) else None


def _prefix_tokens(req):
    """system + tool definitions from a recorded request body."""
    if not req:
        return 0
    total = 0
    sysmsg = req.get("system")
    if isinstance(sysmsg, str):
        total += count_text(sysmsg)
    elif isinstance(sysmsg, list):
        total += count_json(sysmsg)
    if req.get("tools"):
        total += count_json(req["tools"])
    # OpenAI puts the system prompt in messages[] instead of a top-level field.
    for m in req.get("messages") or []:
        if isinstance(m, dict) and m.get("role") == "system":
            total += count_text(m.get("content") or "")
    return total


def _user_tokens(req):
    """User-authored text in a recorded request body.

    # ponytail: every request carries the FULL message history, so summing
    # across requests would multiply-count. Caller keeps only the last request
    # and counts it once — the last one holds the whole conversation.
    """
    if not req:
        return 0
    total = 0
    for m in req.get("messages") or []:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            total += count_text(c)
        elif isinstance(c, list):
            for block in c:
                # tool_result blocks are counted from tool_result events, not here
                if isinstance(block, dict) and block.get("type") == "text":
                    total += count_text(block.get("text") or "")
                elif isinstance(block, str):
                    total += count_text(block)
    return total


def _assistant_text(resp):
    """Visible assistant text + thinking from a recorded response body."""
    text = think = 0
    if not resp:
        return text, think
    for block in resp.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text += count_text(block.get("text") or "")
        elif block.get("type") == "thinking":
            think += count_text(block.get("thinking") or "")
    for choice in resp.get("choices") or []:          # OpenAI shape
        msg = (choice or {}).get("message") or {}
        text += count_text(msg.get("content") or "")
    return text, think


def parse(path: str) -> Session:
    cats = {"system+tools_prefix": 0, "user_text": 0, "assistant_text": 0,
            "thinking": 0, "tool_use_args": 0, "tool_results": 0, "total_visible": 0}
    by_seq = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("kind") in _KINDS:
                by_seq.setdefault(ev.get("seq"), []).append(ev)

    turns = []
    last_request = None
    pending_results = []
    pending_results_tok = 0
    reported_in = reported_out = 0

    for seq in sorted(by_seq, key=lambda s: (s is None, s)):
        group = by_seq[seq]

        for ev in group:
            kind = ev.get("kind")

            if kind == "model_request":
                req = _body(ev)
                # Counted once, from the first request that carries a prefix.
                if not cats["system+tools_prefix"]:
                    cats["system+tools_prefix"] = _prefix_tokens(req)
                # Keep the last request: it holds the full message history.
                if req is not None:
                    last_request = req

            elif kind == "tool_call":
                cats["tool_use_args"] += count_json(ev.get("args") or {})

            elif kind == "tool_result":
                tok = count_json(ev.get("result"))
                cats["tool_results"] += tok
                pending_results.append((ev.get("tool") or "?", tok))
                pending_results_tok += tok

            elif kind == "model_response":
                resp = _body(ev)
                text, think = _assistant_text(resp)
                cats["assistant_text"] += text
                cats["thinking"] += think

                u = ev.get("usage") or {}
                turn = Turn(
                    index=len(turns),
                    total_input=usage_total(u),
                    cache_creation=u.get("cache_creation_input_tokens", 0),
                    cache_read=u.get("cache_read_input_tokens", 0),
                    output=u.get("output_tokens", 0) or u.get("completion_tokens", 0),
                    added_tool_results=pending_results_tok,
                    tool_results=list(pending_results),
                    tool_calls=[(e.get("tool") or "?", e.get("args_hash") or "")
                                for e in group if e.get("kind") == "tool_call"],
                )
                reported_in += turn.total_input
                reported_out += turn.output
                turns.append(turn)
                pending_results, pending_results_tok = [], 0

    cats["user_text"] = _user_tokens(last_request)

    cats["total_visible"] = (cats["system+tools_prefix"] + cats["user_text"]
                             + cats["assistant_text"] + cats["thinking"]
                             + cats["tool_use_args"] + cats["tool_results"])

    return Session(
        format="agent_vcr_tape",
        turns=turns,
        categories=cats,
        inferred_prefix=cats["system+tools_prefix"],
        prefix_inferred=False,   # counted from the recorded request, not inferred
        reported_total_input=reported_in,
        reported_total_output=reported_out,
    )
