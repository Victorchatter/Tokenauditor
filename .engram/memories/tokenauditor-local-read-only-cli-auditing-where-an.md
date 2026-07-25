---
id: "38cd22e6"
type: context
tags: []
created: "2026-07-25T13:27:42.728Z"
source: manual
---
tokenauditor: local, read-only CLI auditing where an agent session's token budget went — parses Claude Code, OpenAI, and Codex transcripts, reports per-turn token breakdown plus waste flags. CLI entry point: tokenauditor (tokenauditor/cli.py). No API keys, offline-first, built 2026-07-20, repo github.com/Victorchatter/Tokenauditor. # ponytail: falls back to a ~4-chars/token heuristic when tiktoken's BPE table can't be fetched (counters.py).
