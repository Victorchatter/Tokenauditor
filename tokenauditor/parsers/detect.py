import json


def detect(path: str) -> str:
    # ponytail: first-line sniff. Claude Code JSONL = one JSON object per line with a
    # `type` field (the first line is often `last-prompt`, not a user/assistant record).
    # OpenAI = a top-level array, or an object with a `messages` key.
    with open(path, "r", encoding="utf-8") as f:
        first = ""
        for line in f:
            first = line.strip()
            if first:
                break
    if not first:
        raise ValueError("unrecognized transcript format (empty file)")

    if first.startswith("["):
        return "openai"  # compact array or pretty-printed array start

    if first.startswith("{"):
        try:
            o = json.loads(first)
        except json.JSONDecodeError:
            # pretty-printed object where first line is just "{"
            return _openai_or_error(path)
        if isinstance(o, dict):
            if "messages" in o:
                return "openai"
            if "type" in o:
                return "claude_code"
        raise ValueError("unrecognized transcript format (expected Claude Code JSONL or OpenAI messages JSON)")

    raise ValueError("unrecognized transcript format (first line not JSON)")


def _openai_or_error(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            o = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"unrecognized transcript format (could not parse as OpenAI JSON: {e})")
    if isinstance(o, list) or (isinstance(o, dict) and "messages" in o):
        return "openai"
    raise ValueError("unrecognized transcript format (expected Claude Code JSONL or OpenAI messages JSON)")