import hashlib
import json

from . import Session, Turn
from ..counters import count_text, count_json


def parse(path: str) -> Session:
    cats = {"system+tools_prefix": 0, "user_text": 0, "assistant_text": 0,
            "thinking": 0, "tool_use_args": 0, "tool_results": 0, "total_visible": 0}
    turns = []
    pending = {}  # call_id -> tool_name

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = o.get("type")
            if t == "session_meta":
                bi = o.get("payload", {}).get("base_instructions", {})
                cats["system+tools_prefix"] += count_text(bi.get("text", ""))
            elif t == "response_item":
                p = o.get("payload", {})
                _handle_item(p, cats, turns, pending)
            elif t == "event_msg":
                p = o.get("payload", {})
                if p.get("type") == "token_count":
                    _handle_usage(p.get("info", {}), turns)

    cats["total_visible"] = sum(v for k, v in cats.items() if k != "total_visible")
    return Session(
        format="codex",
        turns=turns,
        categories=cats,
        inferred_prefix=cats["system+tools_prefix"],
        prefix_inferred=False,
        reported_total_input=sum(t.total_input for t in turns),
        reported_total_output=sum(t.output for t in turns),
        model=None,
    )


def _cur_turn(turns):
    # ponytail: attach function_call/output/reasoning to the most recent turn,
    # creating one if none exists yet (Codex emits these around/before assistant text).
    if not turns:
        turns.append(Turn(index=1))
    return turns[-1]


def _handle_item(p, cats, turns, pending):
    pt = p.get("type")
    if pt == "message":
        role = p.get("role")
        text = _concat_content(p.get("content", []))
        if role == "system":
            cats["system+tools_prefix"] += count_text(text)
        elif role == "user":
            cats["user_text"] += count_text(text)
            _cur_turn(turns).added_user_text += count_text(text)
        elif role == "assistant":
            t = Turn(index=len(turns) + 1)
            cats["assistant_text"] += count_text(text)
            turns.append(t)
    elif pt == "reasoning":
        text = " ".join(s.get("text", "") for s in p.get("summary", []) if isinstance(s, dict))
        cats["thinking"] += count_text(text)
    elif pt == "function_call":
        name = p.get("name", "?")
        args = p.get("arguments", "")
        cats["tool_use_args"] += _count(args)
        _cur_turn(turns).tool_calls.append((name, _hash(args)))
        pending[p.get("call_id")] = name
    elif pt == "function_call_output":
        name = pending.get(p.get("call_id"), "?")
        out = p.get("output", "")
        tok = _count(out)
        cats["tool_results"] += tok
        t = _cur_turn(turns)
        t.tool_results.append((name, tok))
        t.added_tool_results += tok


def _handle_usage(info, turns):
    if not info:
        return
    last = info.get("last_token_usage") or {}
    if not last:
        return
    t = _cur_turn(turns)
    # ponytail: Codex/oOllama token_count often reports subfields as 0 with only
    # total_tokens set; total_input stays 0 then (CONTEXT_GROWTH won't fire — honest).
    t.total_input = last.get("input_tokens", 0) + last.get("cached_input_tokens", 0)
    t.cache_read = last.get("cached_input_tokens", 0)
    t.output = last.get("output_tokens", 0) + last.get("reasoning_output_tokens", 0)


def _concat_content(content):
    parts = []
    for c in content:
        if isinstance(c, dict):
            parts.append(c.get("text", ""))
    return "\n".join(parts)


def _count(s):
    if s is None:
        return 0
    return count_text(s) if isinstance(s, str) else count_json(s)


def _hash(args) -> str:
    s = args if isinstance(args, str) else json.dumps(args, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()