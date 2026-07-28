from .parsers import Session


def _fmt_cost(n: float) -> str:
    return f"${n:,.6f}" if n >= 0.001 else f"${n:.8f}"


def check(session: Session) -> list:
    return (
        _heavy_tool_result(session)
        + _context_growth(session)
        + _repeat_tool_call(session)
    )


def _heavy_tool_result(s: Session) -> list:
    out = []
    user_total = s.categories.get("user_text", 0)
    if user_total == 0:
        return out
    for t in s.turns:
        for name, tok in t.tool_results:
            if tok > user_total:
                out.append({
                    "flag": "HEAVY_TOOL_RESULT",
                    "message": (f"HEAVY_TOOL_RESULT: {name} result ~{tok}tok > "
                                f"all user turns combined (~{user_total}tok) at turn {t.index}"),
                    "turn": t.index,
                })
    return out


def _context_growth(s: Session) -> list:
    # ponytail: needs >=4 turns with reported usage; OpenAI has none, so this never fires there.
    inputs = [t.total_input for t in s.turns if t.total_input > 0]
    if len(inputs) < 4:
        return []
    q = len(inputs) // 4
    first_q = sorted(inputs[:q])
    last_q = sorted(inputs[-q:])
    fm = first_q[len(first_q) // 2]
    lm = last_q[len(last_q) // 2]
    if fm == 0 or lm / fm <= 2:
        return []
    return [{
        "flag": "CONTEXT_GROWTH",
        "message": (f"CONTEXT_GROWTH: context grew ~{fm}tok -> ~{lm}tok "
                    f"({lm/fm:.1f}x) from first to last quarter"),
        "turn": None,
    }]


def _repeat_tool_call(s: Session) -> list:
    seen = {}  # (name, hash) -> [turn indexes]
    for t in s.turns:
        for name, h in t.tool_calls:
            seen.setdefault((name, h), []).append(t.index)
    out = []
    for (name, _h), idxs in seen.items():
        if len(idxs) >= 2:
            out.append({
                "flag": "REPEAT_TOOL_CALL",
                "message": (f"REPEAT_TOOL_CALL: {name} called {len(idxs)} times "
                            f"with identical input (first at turn {idxs[0]})"),
                "turn": idxs[0],
            })
    return out


def check_cost_warnings(session: Session, cost_rows: list, threshold: float) -> list:
    """Return cost warnings for turns exceeding a spend threshold or tool results
    that dominate a turn.

    - EXPENSIVE_TURN: a turn's ``cost_total`` exceeds *threshold*.
    - EXPENSIVE_TOOL: a tool result's token count is larger than the turn's
      ``total_input + output``.
    """
    warnings = []
    if threshold is None:
        threshold = 0.0

    for row in cost_rows:
        total = row.get("cost_total", 0.0)
        if total > threshold:
            turn = row.get("turn")
            warnings.append({
                "flag": "EXPENSIVE_TURN",
                "message": (f"EXPENSIVE_TURN: turn {turn} cost {_fmt_cost(total)} "
                            f"exceeds threshold {_fmt_cost(threshold)}"),
                "turn": turn,
            })

    for turn in session.turns:
        total_io = turn.total_input + turn.output
        if total_io <= 0:
            continue
        for name, tok in turn.tool_results:
            if tok > total_io:
                warnings.append({
                    "flag": "EXPENSIVE_TOOL",
                    "message": (f"EXPENSIVE_TOOL: {name} result ~{tok}tok > "
                                f"turn {turn.index} input+output (~{total_io}tok)"),
                    "turn": turn.index,
                })

    return warnings