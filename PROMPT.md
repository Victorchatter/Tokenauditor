# tokenauditor — bootstrap session prompt

You are bootstrapping a new open-source project. Follow the full process: invoke `superpowers:brainstorming` first, lock the design with me, write the spec to `docs/superpowers/specs/YYYY-MM-DD-tokenauditor-design.md`, commit it, then `superpowers:writing-plans`, get plan approval, then implement with `superpowers:executing-plans`. Verify with a `selfcheck.py` before declaring done.

## Idea (one-liner)
A local, read-only CLI that parses an AI agent session transcript (Claude Code JSONL, OpenAI messages, Codex traces) and reports a per-turn token breakdown — system prompt vs tool definitions vs tool results vs user/assistant messages — plus "waste flags" (e.g. a single tool result larger than all user turns combined, system prompt growing across the session, repeated identical tool calls). Output: a terminal table + optional JSON.

## Why it doesn't exist
Tokenizers exist, but nothing walks a real recorded agent transcript and tells you *where the budget went*. Every agent dev feels this pain; nobody ships the tool. This is the "star magnet" of the family.

## Hard constraints
- Python, `pipx install .`. Fully local/offline, no API keys, no telemetry, read-only (never mutates the transcript file).
- Token counting must use the right tokenizer per provider: tiktoken for OpenAI, Anthropic's published token counts when present in the transcript; when absent, fall back to a documented approximation and label it clearly.
- Small and sharp. No web UI. One CLI: `tokenauditor <file> [--json] [--by-turn] [--flags]`.
- Ponytail (lazy senior dev): shortest working diff, stdlib first, no unrequested abstractions. Mark simplifications with `# ponytail:` comments naming the ceiling + upgrade path.
- One `selfcheck.py` with a tiny synthetic transcript that asserts the breakdown sums to the total and the waste flags fire. No test framework.
- License MIT. README with install + a screenshot-friendly example output.

## Scope / YAGNI (v1)
Ship: file parsers for Claude Code JSONL + OpenAI messages JSON (Codex as a stretch). Per-turn breakdown, totals, waste flags, JSON output. Out: live streaming attach, charts, remote transcripts, diffing two runs (cut — `agent-vcr diff` covers a different need).

## Inputs to lock during brainstorming
- Exact waste-flag rules (propose 3-5, each with a threshold + a clear message).
- Transcript format priority order (recommend Claude Code JSONL first since you have real samples).
- Whether to count tool *definitions* (system prompt tools) separately — recommend yes.

This is one of 10 sibling local-first agent-tooling projects. Keep it small and ship it.