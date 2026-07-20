import json


def detect(path: str) -> str:
    # ponytail: first-line sniff. Claude Code lines are JSON objects with type/message;
    # OpenAI is a top-level array or {messages:...}. Sniff, don't configure.
    with open(path, "r", encoding="utf-8") as f:
        first = ""
        for line in f:
            first = line.strip()
            if first:
                break
    try:
        o = json.loads(first)
    except json.JSONDecodeError as e:
        raise ValueError(f"unrecognized transcript format (first line not JSON: {e})")
    if isinstance(o, list):
        return "openai"
    if isinstance(o, dict):
        if "messages" in o:
            return "openai"
        if "type" in o and "message" in o:
            return "claude_code"
    raise ValueError("unrecognized transcript format (expected Claude Code JSONL or OpenAI messages JSON)")