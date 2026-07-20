# tokenauditor

A local, read-only CLI that parses a recorded AI agent session transcript (Claude Code JSONL or OpenAI messages JSON) and tells you **where the token budget went** — a per-turn breakdown across system prompt, tool definitions, tool results, and user/assistant messages — plus waste flags.

Fully offline. No API keys, no telemetry, never mutates your transcript.

## Install

```bash
pipx install .
# or
pip install .
```

Requires Python 3.9+.

> **Offline note:** `tiktoken` downloads its BPE table on first use. tokenauditor caches it after the first successful run; on a fully air-gapped machine where the BPE can't be fetched, it falls back to a ~4-chars-per-token heuristic and labels the output `(approx, heuristic (offline))` so the numbers are never silently wrong.

## Usage

```bash
tokenauditor <file>              # summary table + waste flags
tokenauditor <file> --by-turn    # add a per-turn table
tokenauditor <file> --flags      # waste flags only
tokenauditor <file> --json       # machine-readable JSON
```

`<file>` is a Claude Code session JSONL (e.g. `~/.claude/projects/<proj>/<session>.jsonl`) or an OpenAI messages JSON (`[{...}]` or `{"messages":[...]}`).

## Example output

```
tokenauditor - claude_code, 306 turn(s)

  Reported total input  (sum over turns): 30,744,786
  Reported total output:                  269,844
  System+tools prefix:                    ~41,047  (inferred)

  Estimated breakdown (approx, tiktoken):
    system+tools_prefix    ~    41,047
    user_text              ~    11,569
    assistant_text         ~     2,460
    thinking              ~         0
    tool_use_args         ~    50,321
    tool_results          ~ 1,120,033  <-- largest
    ----------------------------------
    total_visible         ~ 1,225,430

  Flags:
    HEAVY_TOOL_RESULT: Read result ~102284tok > all user turns combined (~11569tok) at turn 225
    CONTEXT_GROWTH: context grew ~1500tok -> ~28000tok (18.7x) from first to last quarter
    REPEAT_TOOL_CALL: Read called 3 times with identical input (first at turn 7)
```

## Two counts, on purpose

A recorded Claude Code transcript does not store the system prompt or tool definitions as records — they live in the cached prefix that Anthropic reports only as aggregate token counts. So tokenauditor shows two numbers:

- **Reported** — Anthropic `usage` per turn (authoritative): `input + cache_creation + cache_read`, plus `output`.
- **Estimated** — a tiktoken count over the visible content blocks, labeled `(approx, tiktoken)`. Exact for OpenAI, approximate for Anthropic content.
- **Inferred prefix** — system+tools size = first turn's reported total minus the first user message's tokens, labeled `(inferred)`. Conflates the system prompt and tool definitions, which can't be separated from this transcript format.

For OpenAI transcripts, the system prompt (role `system`) and tool definitions (`tools` array) are present as records, so the estimated breakdown is exact and the categories sum to the total.

## Waste flags

- `HEAVY_TOOL_RESULT` — a single tool result whose estimated tokens exceed all user-text turns combined.
- `CONTEXT_GROWTH` — reported context grows more than 2× from the first quarter of turns to the last (requires ≥4 turns with reported usage; never fires for OpenAI).
- `REPEAT_TOOL_CALL` — the same tool called 2+ times with identical input (canonical JSON compared).

## Self-test

```bash
python selfcheck.py
```

## License

MIT