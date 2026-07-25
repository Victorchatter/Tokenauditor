import json

# ponytail: tiktoken downloads its BPE table on first use, which breaks the
# offline constraint. Try to load it; on any failure fall back to a documented
# char-based heuristic and label it clearly in the report.
_ENC = None
_MODE = None  # "tiktoken" | "heuristic"
_FORCE_OFFLINE = False


def force_offline(on: bool = True) -> None:
    """Skip tiktoken entirely, so no BPE-table download is ever attempted.

    The fallback already handles a *failed* download, but only after trying —
    which is a network call. On an egress-controlled machine the attempt itself
    is the problem, so this makes the offline promise something you can assert
    rather than something you discover.
    """
    global _FORCE_OFFLINE, _ENC, _MODE
    _FORCE_OFFLINE = on
    _ENC, _MODE = None, None  # re-resolve on next use


def _ensure():
    global _ENC, _MODE
    if _MODE is not None:
        return
    if _FORCE_OFFLINE:
        _ENC, _MODE = None, "heuristic"
        return
    try:
        import tiktoken
        _ENC = tiktoken.get_encoding("cl100k_base")
        _MODE = "tiktoken"
    except Exception:
        # ponytail: heuristic ceiling = ~4 chars/token (English/code rule of thumb).
        # Upgrade path: ship/cache a real BPE file or call a real tokenizer.
        _ENC = None
        _MODE = "heuristic"


def mode() -> str:
    _ensure()
    return _MODE


def label() -> str:
    return "approx, tiktoken" if mode() == "tiktoken" else "approx, heuristic (offline)"


def count_text(s: str) -> int:
    if not s:
        return 0
    _ensure()
    if _ENC is not None:
        return len(_ENC.encode(s))
    # heuristic: ~4 chars per token
    return max(1, (len(s) + 3) // 4)


def count_json(obj) -> int:
    return count_text(json.dumps(obj, sort_keys=True, ensure_ascii=False))


def usage_total(u: dict) -> int:
    # ponytail: Anthropic usage only; missing keys -> 0. OpenAI has no per-turn usage here.
    if not u:
        return 0
    return (
        u.get("input_tokens", 0)
        + u.get("cache_creation_input_tokens", 0)
        + u.get("cache_read_input_tokens", 0)
    )