import hashlib
import json

from . import Session, Turn
from ..counters import count_text, count_json, usage_total


def parse(path: str) -> Session:
    cats = {"system+tools_prefix": 0, "user_text": 0, "assistant_text": 0,
            "thinking": 0, "tool_use_args": 0, "tool_results": 0, "total_visible": 0}
    turns = []
    pending_tools = {}        # tool_use_id -> tool_name
    pending_user_text = 0
    pending_tool_results = []   # (tool_name, tokens)
    pending_tool_results_tok = 0
    first_total_input = None
    first_user_text_tok = None

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
            if t == "assistant":
                msg = o.get("message", {})
                u = msg.get("usage", {}) or {}
                ti = usage_total(u)
                if first_total_input is None:
                    first_total_input = ti
                turn = Turn(
                    index=len(turns) + 1,
                    total_input=ti,
                    cache_creation=u.get("cache_creation_input_tokens", 0),
                    cache_read=u.get("cache_read_input_tokens", 0),
                    output=u.get("output_tokens", 0),
                    added_user_text=pending_user_text,
                    added_tool_results=pending_tool_results_tok,
                    tool_results=list(pending_tool_results),
                )
                for b in msg.get("content", []):
                    bt = b.get("type")
                    if bt == "text":
                        cats["assistant_text"] += count_text(b.get("text", ""))
                    elif bt == "thinking":
                        cats["thinking"] += count_text(b.get("thinking", ""))
                    elif bt == "tool_use":
                        name = b.get("name", "?")
                        args = b.get("input", {})
                        cats["tool_use_args"] += count_json(args)
                        turn.tool_calls.append((name, _hash(args)))
                        pending_tools[b.get("id")] = name
                turns.append(turn)
                pending_user_text = 0
                pending_tool_results = []
                pending_tool_results_tok = 0
            elif t == "user":
                msg = o.get("message", {})
                c = msg.get("content")
                if isinstance(c, str):
                    tok = count_text(c)
                    if first_user_text_tok is None:
                        first_user_text_tok = tok
                    cats["user_text"] += tok
                    pending_user_text += tok
                elif isinstance(c, list):
                    for b in c:
                        bt = b.get("type")
                        if bt == "text":
                            tok = count_text(b.get("text", ""))
                            if first_user_text_tok is None:
                                first_user_text_tok = tok
                            cats["user_text"] += tok
                            pending_user_text += tok
                        elif bt == "tool_result":
                            name = pending_tools.get(b.get("tool_use_id")) or _tool_name_from_result(o)
                            content = b.get("content")
                            tok = count_text(content) if isinstance(content, str) else count_json(content)
                            cats["tool_results"] += tok
                            pending_tool_results.append((name, tok))
                            pending_tool_results_tok += tok

    # ponytail: inferred prefix = first turn's total input minus first user message tokens.
    # Conflates system prompt + tool defs (not separable from this transcript format).
    inferred = 0
    if first_total_input is not None:
        inferred = max(0, first_total_input - (first_user_text_tok or 0))
    cats["system+tools_prefix"] = inferred
    cats["total_visible"] = sum(v for k, v in cats.items() if k != "total_visible")

    return Session(
        format="claude_code",
        turns=turns,
        categories=cats,
        inferred_prefix=inferred,
        prefix_inferred=True,
        reported_total_input=sum(t.total_input for t in turns),
        reported_total_output=sum(t.output for t in turns),
    )


def _tool_name_from_result(o):
    tr = o.get("toolUseResult")
    if isinstance(tr, dict):
        return tr.get("name") or tr.get("tool") or "?"
    return "?"


def _hash(obj) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()