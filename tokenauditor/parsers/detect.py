import json

_CODEX_TYPES = {"session_meta", "response_item", "event_msg"}
_CLAUDE_TYPES = {"user", "assistant", "system", "last-prompt", "mode",
                 "permission-mode", "attachment", "file-history-snapshot",
                 "ai-title", "queue-operation"}


def detect(path: str) -> str:
    # ponytail: first-line sniff. OpenAI = top-level array or {messages:...}.
    # Claude Code JSONL = one object per line with a `type` in the Claude set
    # (first line is often `last-prompt`, not a user/assistant record) and a
    # `message` field on content lines. Codex rollout = objects with a `payload`.
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
            return _openai_or_error(path)  # pretty-printed object where first line is just "{"
        if isinstance(o, dict):
            # agent-vcr tape: wire-level events carrying a `kind`. Checked before
            # "messages", because a model_request body can contain one.
            if o.get("kind") in ("model_request", "model_response",
                                 "tool_call", "tool_result", "run_aborted"):
                return "tape"
            if "messages" in o:
                return "openai"
            t = o.get("type")
            if t in _CODEX_TYPES:
                return "codex"
            if t in _CLAUDE_TYPES:
                return "claude_code"
            if "payload" in o:
                return "codex"
            if "message" in o:
                return "claude_code"
        raise ValueError("unrecognized transcript format (expected Claude Code JSONL, Codex rollout, or OpenAI messages JSON)")

    raise ValueError("unrecognized transcript format (first line not JSON)")


def _openai_or_error(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            o = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"unrecognized transcript format (could not parse as OpenAI JSON: {e})")
    if isinstance(o, list) or (isinstance(o, dict) and "messages" in o):
        return "openai"
    raise ValueError("unrecognized transcript format (expected Claude Code JSONL, Codex rollout, or OpenAI messages JSON)")