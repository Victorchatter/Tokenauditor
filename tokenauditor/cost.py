"""Cost estimation for tokenauditor.

# ponytail: prices are vendored from agent-circuit-breaker so tokenauditor stays
self-contained. If a transcript reports usage, we use it; otherwise we fall back
to tiktoken/heuristic counts and label the estimate clearly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

DEFAULT_PRICE = (0.0, 0.0)


def _default_prices_path() -> Path:
    """Return the vendored prices.json path relative to this module."""
    return Path(__file__).with_name("data") / "prices.json"


def load_prices(path: str | Path | None = None) -> dict:
    """Load the per-model price table.

    If *path* is provided, read from disk. Otherwise load the bundled
    ``prices.json`` shipped with the package.
    """
    if path is None:
        path = _default_prices_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def price_for_model(prices: dict, model: str) -> Tuple[float, float, float]:
    """Return (input_price_per_1m, output_price_per_1m, cache_price_per_1m).

    Falls back to exact-stripped snapshots and finally to ``default`` if present.
    Cache price defaults to the input price if not specified.
    """
    entry = prices.get(model)
    if entry is None:
        base = model.rsplit("-", 1)[0]
        entry = prices.get(base)
    if entry is None:
        entry = prices.get("default", {})
    input_price = float(entry.get("input_price_per_1m", 0.0))
    output_price = float(entry.get("output_price_per_1m", 0.0))
    cache_price = float(entry.get("cache_price_per_1m", input_price))
    return input_price, output_price, cache_price


def compute_cost(
    prices: dict,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int = 0,
) -> Tuple[float, float, float, float]:
    """Compute USD cost breakdown: (input_cost, output_cost, cache_cost, total)."""
    inp, out, cache = price_for_model(prices, model)
    input_cost = input_tokens * (inp / 1_000_000)
    output_cost = output_tokens * (out / 1_000_000)
    cache_cost = cache_tokens * (cache / 1_000_000)
    return input_cost, output_cost, cache_cost, input_cost + output_cost + cache_cost


def detect_model(session) -> str:
    """Best-effort model detection from a parsed Session object.

    Checks turn-level model fields and session-level metadata. Returns the
    most common concrete model name, or "unknown" with a warning.
    """
    candidates = []
    for turn in getattr(session, "turns", []):
        # Turn objects may carry model only in some future extensions; for now
        # the parsers do not set it, so we fall through.
        if hasattr(turn, "model") and turn.model:
            candidates.append(turn.model)
    # Session attributes are not currently populated by parsers; leave the hook
    # for future readers that expose a top-level model.
    if hasattr(session, "model") and session.model:
        candidates.insert(0, session.model)

    if candidates:
        # Return the most common candidate.
        return max(set(candidates), key=candidates.count)

    return "unknown"


def model_from_transcript(path: str, fmt: str) -> str:
    """Attempt to extract a model name directly from the transcript file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return "unknown"

    if fmt == "openai":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data.get("model") or "unknown"
        except json.JSONDecodeError:
            pass
        return "unknown"

    # For JSONL formats, scan the first few model mentions.
    for line in text.splitlines()[:50]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        # Direct model field on an event or inside body.
        for key in ("model", "model_id", "model_name"):
            val = obj.get(key)
            if isinstance(val, str) and val:
                return val
        body = obj.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        if isinstance(body, dict):
            for key in ("model", "model_id", "model_name"):
                val = body.get(key)
                if isinstance(val, str) and val:
                    return val
    return "unknown"
