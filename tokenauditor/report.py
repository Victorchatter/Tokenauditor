import json

from .counters import label as _counter_label
from .parsers import Session


def _fmt(n: int) -> str:
    return f"{n:,}"


def render_table(session: Session, flags: list, by_turn: bool = False) -> str:
    L = []
    L.append(f"tokenauditor — {session.format}, {len(session.turns)} turn(s)")
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