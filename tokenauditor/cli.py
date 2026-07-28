import argparse
import os
import sys

from . import charts
from . import counters
from . import flags as flags_mod
from . import report
from .cost import compute_cost, load_prices, model_from_transcript
from .parsers import claude_code, codex, detect, openai, tape


def _parse(fmt, path):
    if fmt == "claude_code":
        return claude_code.parse(path)
    if fmt == "codex":
        return codex.parse(path)
    if fmt == "tape":
        return tape.parse(path)
    return openai.parse(path)


def _write_charts(session, chart_dir):
    # ponytail: explicit --charts opts the user into output; transcript stays read-only.
    os.makedirs(chart_dir, exist_ok=True)
    bar = charts.category_bar_svg(session)
    area = charts.turn_area_svg(session)
    if bar:
        with open(os.path.join(chart_dir, "bar.svg"), "w", encoding="utf-8") as f:
            f.write(bar)
    if area:
        with open(os.path.join(chart_dir, "area.svg"), "w", encoding="utf-8") as f:
            f.write(area)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="tokenauditor",
        description="Audit where an AI agent session's token budget went.",
    )
    p.add_argument("file", help="path to transcript (Claude Code JSONL, Codex rollout JSONL, or OpenAI messages JSON)")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p.add_argument("--by-turn", action="store_true", help="include a per-turn table")
    p.add_argument("--flags", action="store_true", help="print waste flags only")
    p.add_argument("--charts", metavar="DIR", help="write SVG charts (bar.svg + area.svg) to DIR")
    p.add_argument("--cost", action="store_true",
                   help="estimate USD spend per turn and total")
    p.add_argument("--cost-json", action="store_true",
                   help="emit machine-readable cost JSON")
    p.add_argument("--model",
                   help="override the model used for cost estimation (default: auto-detect)")
    p.add_argument("--offline", action="store_true",
                   help="never load tiktoken; use the documented ~4 chars/token heuristic. "
                        "Guarantees no network call is attempted.")
    args = p.parse_args(argv)

    if args.offline:
        counters.force_offline()

    try:
        fmt = detect.detect(args.file)
    except (ValueError, OSError) as e:
        print(f"tokenauditor: {e}", file=sys.stderr)
        return 2

    try:
        session = _parse(fmt, args.file)
    except (ValueError, OSError, KeyError) as e:
        print(f"tokenauditor: failed to parse {args.file}: {e}", file=sys.stderr)
        return 2

    fl = flags_mod.check(session)

    if args.cost or args.cost_json:
        model = args.model
        if not model:
            # Prefer parser-extracted model; fall back to scanning the transcript.
            model = getattr(session, "model", None) or model_from_transcript(args.file, fmt)
        if model == "unknown" or not model:
            # Heuristic: if we see Anthropic-style usage, assume claude-3-5-sonnet-20241022;
            # otherwise a small OpenAI model so the report still renders with a warning.
            model = "claude-3-5-sonnet-20241022" if session.reported_total_input else "gpt-4o-mini"
            print(f"tokenauditor: could not detect model; assuming {model} for cost estimate",
                  file=sys.stderr)
        if args.cost_json:
            sys.stdout.write(report.render_cost_json(session, model))
        else:
            sys.stdout.write(report.render_cost_table(session, model))
        return 0

    if args.charts:
        try:
            _write_charts(session, args.charts)
        except OSError as e:
            print(f"tokenauditor: failed to write charts: {e}", file=sys.stderr)
            return 2

    if args.json:
        sys.stdout.write(report.render_json(session, fl, by_turn=args.by_turn))
        return 0

    if args.flags:
        for f in fl:
            print(f["message"])
        return 0

    sys.stdout.write(report.render_table(session, fl, by_turn=args.by_turn))
    return 0


# ponytail: `python -m tokenauditor.cli` used to run, exit 0, and print nothing —
# a silent no-op, because main() was defined but never called. __main__.py covers
# `python -m tokenauditor`, but the longer form is the one people reach for.
if __name__ == "__main__":
    sys.exit(main())