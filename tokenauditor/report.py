import json

from .counters import label as _counter_label
from .cost import compute_cost, load_prices
from .parsers import Session


def _fmt(n: int) -> str:
    return f"{n:,}"


def render_table(session: Session, flags: list, by_turn: bool = False) -> str:
    L = []
    L.append(f"tokenauditor - {session.format}, {len(session.turns)} turn(s)")
    L.append("")
    L.append(f"  Reported total input  (sum over turns): {_fmt(session.reported_total_input)}")
    L.append(f"  Reported total output:                  {_fmt(session.reported_total_output)}")
    plabel = "inferred" if session.prefix_inferred else "exact"
    L.append(f"  System+tools prefix:                    ~{_fmt(session.inferred_prefix)}  ({plabel})")
    L.append("")
    L.append(f"  Estimated breakdown ({_counter_label()}):")
    cats = session.categories
    order = ["system+tools_prefix", "user_text", "assistant_text", "thinking",
             "tool_use_args", "tool_results"]
    biggest = max(order, key=lambda k: cats.get(k, 0)) if order else ""
    for k in order:
        v = cats.get(k, 0)
        mark = "  <-- largest" if k == biggest and v else ""
        L.append(f"    {k:<22} ~{_fmt(v):>10}{mark}")
    L.append("    " + "-" * 34)
    L.append(f"    {'total_visible':<22} ~{_fmt(cats.get('total_visible', 0)):>10}")
    L.append("")
    if by_turn and session.turns:
        L.append("  Per turn:")
        L.append(f"    {'#':>3} {'input':>10} {'cache_r':>10} {'cache_c':>10} "
                  f"{'out':>8} {'+usr':>7} {'+tools':>8}")
        for t in session.turns:
            L.append(f"    {t.index:>3} {_fmt(t.total_input):>10} {_fmt(t.cache_read):>10} "
                      f"{_fmt(t.cache_creation):>10} {_fmt(t.output):>8} {t.added_user_text:>7} "
                      f"{t.added_tool_results:>8}")
        L.append("")
    L.append("  Flags:")
    if flags:
        for f in flags:
            L.append(f"    {f['message']}")
    else:
        L.append("    (none)")
    return "\n".join(L) + "\n"


def render_json(session: Session, flags: list, by_turn: bool = False) -> str:
    out = {
        "format": session.format,
        "turns": len(session.turns),
        "counter": _counter_label(),
        "reported": {"total_input": session.reported_total_input,
                     "total_output": session.reported_total_output},
        "inferred_prefix": session.inferred_prefix,
        "prefix_inferred": session.prefix_inferred,
        "estimated": session.categories,
        "flags": flags,
    }
    if by_turn:
        out["by_turn"] = [
            {"turn": t.index, "total_input": t.total_input, "cache_read": t.cache_read,
             "cache_creation": t.cache_creation, "output": t.output,
             "added_user_text": t.added_user_text, "added_tool_results": t.added_tool_results}
            for t in session.turns
        ]
    return json.dumps(out, indent=2) + "\n"


def _cost_rows(session: Session, model: str, prices: dict | None = None):
    """Return per-turn cost rows plus a total row."""
    prices = prices if prices is not None else load_prices()
    rows = []
    cumulative = 0.0
    for t in session.turns:
        cache_tok = t.cache_read + t.cache_creation
        inp, out, cache, total = compute_cost(prices, model, t.total_input, t.output, cache_tok)
        cumulative += total
        rows.append({
            "turn": t.index,
            "input_tokens": t.total_input,
            "output_tokens": t.output,
            "cache_tokens": cache_tok,
            "cost_input": inp,
            "cost_output": out,
            "cost_cache": cache,
            "cost_total": total,
            "cumulative_cost": cumulative,
        })
    return rows, cumulative


def _fmt_cost(n: float) -> str:
    return f"${n:,.6f}" if n >= 0.001 else f"${n:.8f}"


def render_cost_table(session: Session, model: str) -> str:
    rows, total = _cost_rows(session, model)
    L = []
    L.append(f"tokenauditor cost report — model: {model}")
    L.append("")
    L.append(f"{'turn':>4} {'input':>10} {'output':>8} {'cache':>8} "
              f"{'cost_in':>12} {'cost_out':>12} {'cost_cache':>12} {'cumulative':>14}")
    L.append("-" * 90)
    for r in rows:
        L.append(
            f"{r['turn']:>4} {r['input_tokens']:>10,} {r['output_tokens']:>8,} {r['cache_tokens']:>8,} "
            f"{_fmt_cost(r['cost_input']):>12} {_fmt_cost(r['cost_output']):>12} "
            f"{_fmt_cost(r['cost_cache']):>12} {_fmt_cost(r['cumulative_cost']):>14}"
        )
    L.append("-" * 90)
    L.append(f"{'total':>32} {_fmt_cost(total):>58}")
    return "\n".join(L) + "\n"


def render_cost_json(session: Session, model: str) -> str:
    rows, total = _cost_rows(session, model)
    out = {
        "model": model,
        "currency": "USD",
        "total_cost": total,
        "by_turn": rows,
    }
    return json.dumps(out, indent=2) + "\n"