# tokenauditor — design spec

**Date:** 2026-07-20
**Status:** Approved
**One-liner:** A local, read-only CLI that parses a recorded AI agent session transcript and reports a per-turn token breakdown — system prompt vs tool definitions vs tool results vs user/assistant messages — plus waste flags. Output: terminal table + optional JSON.

## Goals

- Tell an agent developer *where the token budget went* on a real recorded session.
- Fully local/offline. No API keys, no telemetry, no network. Read-only (never mutates the transcript).
- `pipx install .` on Python 3.9+.
- Small and sharp: one CLI, no web UI.
- Ponytail: stdlib first, shortest working diff, no unrequested abstractions. Simplifications marked with `# ponytail:` comments naming the ceiling and upgrade path.

## Non-goals (YAGNI — v1)

- Codex trace parser (stretch; deferred to a later release).
- Live streaming attach.
- Charts / web UI.
- Remote transcripts.
- Diffing two runs (`agent-vcr diff` covers a different need).
- Per-function test suites / a test framework. One `selfcheck.py` only.

## The two-count model

A recorded Claude Code transcript does **not** store the system prompt or tool definitions as discrete records. They live in the cached prefix that Anthropic reports only as aggregate token counts. So tokenauditor reports two parallel, clearly-labeled counts rather than one fiction:

- **Reported** — Anthropic `message.usage` per assistant turn. `total_input = input_tokens + cache_creation_input_tokens + cache_read_input_tokens`; `output_tokens`. Authoritative. Used for context-growth analysis and as the headline per-turn number.
- **Estimated** — tiktoken over the visible content blocks, categorized. Labeled `(approx, tiktoken)`. For Anthropic content there is no public tokenizer, so tiktoken (`cl100k_base`) is an approximation; for OpenAI content it is exact.
- **Inferred prefix** — `system + tools` size, one number: first turn's reported `total_input` minus the first user message's estimated tokens. Labeled `(inferred)`. This is the only way to size the hidden prefix from a Claude Code transcript; it conflates system prompt and tool defs into one bucket (separating them is not possible from this transcript format).

For OpenAI messages JSON, the system prompt (role `system`) and tool definitions (`tools` array) ARE present as records, so the estimated breakdown is exact and the categories sum to the total — no inference needed.

## Categories

Estimated breakdown buckets:

| Category | Claude Code source | OpenAI source |
|---|---|---|
| `system+tools_prefix` | inferred (one number) | `system` role messages + `tools` array |
| `user_text` | `user` lines, `message.content` str/list text | `role: user` text |
| `assistant_text` | `assistant` `text` blocks | `role: assistant` text |
| `thinking` | `assistant` `thinking` blocks | — |
| `tool_use_args` | `assistant` `tool_use` blocks (`input`) | `tool_calls[].function.arguments` |
| `tool_results` | `user` `tool_result` blocks + `toolUseResult` | `role: tool` content |

For OpenAI, `estimated_total = system + tools + user_text + assistant_text + tool_use_args + tool_results`, and this is asserted to equal the tiktoken count of the full serialized request.

## Per-turn view (`--by-turn`)

A turn is anchored by an assistant message. For each assistant turn we report:
- reported `total_input`, `cache_creation`, `cache_read`, `output_tokens`
- cache hit/miss (cache_read > 0 = hit)
- new content added since the previous assistant turn (the user lines in between): tool results + any user text, with estimated tokens per category

For OpenAI transcripts (no per-turn usage), a "turn" = one assistant message; we report only the estimated categories for that message and its preceding tool results.

## Waste flags

Three flags ship in v1. Each has a threshold and a clear message.

### `HEAVY_TOOL_RESULT`
A single tool result whose estimated tokens exceed the sum of all `user_text` turns.
Message: `HEAVY_TOOL_RESULT: <tool_name> result ~<N>tok > all user turns combined (~<M>tok) at turn <T>`.
Uses estimated counts. Threshold: strictly greater.

### `CONTEXT_GROWTH`
Reported `total_input` per turn grows more than 2× from the first quarter of turns to the last quarter (median of each quarter). Uses authoritative Anthropic usage — not the estimate.
Message: `CONTEXT_GROWTH: context grew ~<A>tok -> ~<B>tok (<xN>) from first to last quarter`.
Threshold: `last_quarter_median / first_quarter_median > 2`. Requires ≥4 assistant turns; below that the flag does not fire.

### `REPEAT_TOOL_CALL`
The same `tool_name + sha1(canonical_input_json)` appears ≥2 times across the session.
Message: `REPEAT_TOOL_CALL: <tool_name> called N times with identical input (first at turn <T>)`.
Threshold: count ≥ 2. Dedup by canonical JSON (sorted keys, compact).

## Parsers

### `claude_code.py` — Claude Code JSONL
- Stream the file line by line, `json.loads` each non-blank line.
- Keep only lines where `type` is `user` or `assistant` (ignore `mode`, `attachment`, `system`, `file-history-snapshot`, `ai-title`, etc.).
- Order by `parentUuid`/`uuid` ancestry where available; fall back to file order. `# ponytail: file order is already chronological; ancestry sort only if interleaving observed`.
- For `assistant`: read `message.content` blocks (`text`, `thinking`, `tool_use`) and `message.usage`.
- For `user`: read `message.content` — a `str` is user_text; a list holds `tool_result` blocks (and possibly `text`). Each `tool_result`'s tool name is read from the matching prior `tool_use` block via `tool_use_id`; fallback: read the paired `toolUseResult` field on the same line.
- Emit a list of normalized records: `{kind, turn_index, role, category, text, tool_name, tool_use_id, usage}`.

### `openai.py` — OpenAI messages JSON
- `json.load` the file. Accept either a bare `[{messages}]` array or `{"messages": [...], "tools": [...]}`.
- Walk messages in order. `role: system` → `system` category; `role: user` → `user_text`; `role: assistant` → `assistant_text` + `tool_calls` → `tool_use_args` (record tool name + arguments); `role: tool` → `tool_results` (match by `tool_call_id` to get the tool name).
- Count `tools` array once as `system+tools_prefix`.
- tiktoken `cl100k_base` is exact here.

### Provider detection
First-line sniff: if the first non-blank line of the file is a JSON object with `type` ∈ `{user, assistant, ...}` and a `message` field, it's Claude Code JSONL; if the file parses as a JSON array or an object with a `messages` key, it's OpenAI. `# ponytail: sniff, don't configure`. If neither matches, error out with a clear message.

## Token counting (`counters.py`)

- `count_text(s) -> int` via `tiktoken.get_encoding("cl100k_base").encode` length. Labeled approximate for Anthropic content, exact for OpenAI.
- `count_json(obj) -> int` via `count_text(json.dumps(obj, sort_keys=True, ensure_ascii=False))`.
- A module-level singleton encoder (tiktoken load is the one real cost). `# ponytail: process-global encoder; per-call encoders would reload the BPE table`.
- For Claude Code, `usage_total(u) = input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.

## CLI

```
tokenauditor <file> [--json] [--by-turn] [--flags]
```
- Default: summary table (estimated category breakdown + inferred prefix + reported totals) + flags section.
- `--by-turn`: also print a per-turn table.
- `--flags`: print flags only (no summary).
- `--json`: emit machine-readable JSON of the full report; with `--by-turn` includes the turn list.
- Read-only: opens with `open(path, "r", encoding="utf-8")`. Never opens for write, never writes anywhere.
- Exit codes: 0 on success, 2 on unreadable/unknown-format file.

## Output — summary table (terminal)

```
tokenauditor — <file>  (claude_code, 306 turns)
  Reported total input (sum over turns):   1,234,567
  Reported total output:                      45,678
  Inferred system+tools prefix:              ~12,345  (inferred)

  Estimated breakdown (approx, tiktoken):
    system+tools_prefix   ~12,345  (inferred)
    user_text                3,210
    assistant_text           8,765
    thinking                 5,432
    tool_use_args            2,109
    tool_results            98,765   <-- largest
    ─────────────────────────────────
    estimated visible       128,286

  Flags:
    HEAVY_TOOL_RESULT: browser_snapshot result ~42k tok > all user turns (~3k) at turn 14
    CONTEXT_GROWTH: context grew ~18k -> ~52k tok (2.9x) from first to last quarter
    REPEAT_TOOL_CALL: Read called 3 times with identical input (first at turn 7)
```

(Exact numbers illustrative.)

## Output — JSON (`--json`)

```json
{
  "file": "<path>",
  "format": "claude_code" | "openai",
  "turns": 306,
  "reported": {"total_input": 1234567, "total_output": 45678},
  "inferred_prefix": 12345,
  "estimated": {
    "system+tools_prefix": 12345,
    "user_text": 3210, "assistant_text": 8765, "thinking": 5432,
    "tool_use_args": 2109, "tool_results": 98765,
    "total_visible": 128286
  },
  "by_turn": [{"turn": 1, "total_input": 22862, "cache_read": 21056,
                "cache_creation": 22859, "output": 1215,
                "added": {"tool_results": 0, "user_text": 12}}, ...],
  "flags": [{"flag": "HEAVY_TOOL_RESULT", "message": "...", "turn": 14}, ...]
}
```

## Layout

```
tokenauditor/
  pyproject.toml
  README.md
  LICENSE                    (MIT)
  selfcheck.py
  tokenauditor/
    __init__.py
    __main__.py               # `python -m tokenauditor`
    cli.py
    counters.py
    flags.py
    report.py                 # table + json renderers
    parsers/
      __init__.py
      claude_code.py
      openai.py
```

Unit boundaries: `counters` (pure token math), `parsers/*` (file → normalized records), `flags` (records → flag list), `report` (report object → str/json), `cli` (argv → report object). Each is independently understandable.

## selfcheck.py

No framework. Two tiny synthetic transcripts written to temp files.

1. **OpenAI synthetic** — a `messages` array with a system message, a user message, an assistant message with a `tool_call`, and a `tool` result larger than the user message. Asserts:
   - estimated category breakdown sums to `total_visible`,
   - `system+tools_prefix` (from a `tools` array) is counted,
   - `HEAVY_TOOL_RESULT` fires,
   - `REPEAT_TOOL_CALL` fires (duplicate tool_call input),
   - `CONTEXT_GROWTH` does NOT fire (no per-turn usage for OpenAI → flag skipped cleanly).

2. **Claude Code synthetic** — a hand-built JSONL with two assistant turns whose `usage.total_input` grows 3×, a tool result larger than the user text, and a repeated `tool_use` with identical input. Asserts:
   - usage parsed and `reported.total_input` equals the sum of per-turn totals,
   - inferred prefix > 0,
   - `CONTEXT_GROWTH` fires,
   - `HEAVY_TOOL_RESULT` fires,
   - `REPEAT_TOOL_CALL` fires,
   - the input file's bytes are unchanged after the run (read-only).

Exit 0 on all asserts, nonzero otherwise. Prints `selfcheck OK` or the first failing assert.

## Dependencies

- Runtime: `tiktoken` (only).
- Build: `setuptools` or `flit-core` via `pyproject.toml`; `pipx install .`.
- Python 3.9+.

## License

MIT.