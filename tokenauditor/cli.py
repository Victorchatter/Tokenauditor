import argparse
import sys

from . import flags as flags_mod
from . import report
from .parsers import claude_code, codex, detect, openai


def _parse(fmt, path):
    if fmt == "claude_code":
        return claude_code.parse(path)
    if fmt == "codex":
        return codex.parse(path)
    return openai.parse(path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="tokenauditor",
        description="Audit where an AI agent session's token budget went.",
    )
    p.add_argument("file", help="path to transcript (Claude Code JSONL or OpenAI messages JSON)")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p.add_argument("--by-turn", action="store_true", help="include a per-turn table")
    p.add_argument("--flags", action="store_true", help="print waste flags only")
    args = p.parse_args(argv)

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

    if args.json:
        sys.stdout.write(report.render_json(session, fl, by_turn=args.by_turn))
        return 0

    if args.flags:
        for f in fl:
            print(f["message"])
        return 0

    sys.stdout.write(report.render_table(session, fl, by_turn=args.by_turn))
    return 0