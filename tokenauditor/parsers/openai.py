import hashlib
import json

from . import Session, Turn
from ..counters import count_text, count_json


def parse(path: str) -> Session:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        messages = data
        tools = []
    elif isinstance(data, dict):
        messages = data.get("messages", [])
        tools = data.get("tools", []) or []
    else:
        raise ValueError("openai: expected a messages array or object with 'messages'")

    cats = {"system+tools_prefix": 0, "user_text": 0, "assistant_text": 0,
            "thinking": 0, "tool_use_args": 0, "tool_results": 0, "total_visible": 0}
    cats["system+tools_prefix"] = count_json(tools) + sum(
        count_text(m.get("content") or "") for m in messages if m.get("role") == "system"
    )

    # ponytail: tool_call_id -> tool_name map for role:tool results (flat list, no nesting)
    pending = {}
    turns = []
    turn_idx = 0
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role == "user":
            cats["user_text"] += _count(content)
        elif role == "assistant":
            turn_idx += 1
            t = Turn(index=turn_idx)
            cats["assistant_text"] += _count(content)
            for tc in m.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                args = fn.get("arguments", "")
                cats["tool_use_args"] += _count(args)
                t.tool_calls.append((name, _hash(args)))
                pending[tc.get("id")] = name
            turns.append(t)
        elif role == "tool":
            name = pending.get(m.get("tool_call_id"), "?")
            tok = _count(content)
            cats["tool_results"] += tok
            if turns:
                turns[-1].tool_results.append((name, tok))
                turns[-1].added_tool_results += tok
    cats["total_visible"] = sum(v for k, v in cats.items() if k != "total_visible")
    return Session(format="openai", turns=turns, categories=cats,
                   inferred_prefix=cats["system+tools_prefix"], prefix_inferred=False,
                   reported_total_input=0, reported_total_output=0)


def _count(content) -> int:
    if content is None:
        return 0
    return count_text(content) if isinstance(content, str) else count_json(content)


def _hash(args) -> str:
    s = args if isinstance(args, str) else json.dumps(args, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()