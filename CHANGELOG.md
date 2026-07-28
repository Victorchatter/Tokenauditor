# Changelog

## 0.2.0

### Added
- `--cost` estimates USD spend per turn and total, with columns for input, output,
  cache tokens, and cumulative cost.
- `--cost-json` emits machine-readable cost JSON.
- `--model` overrides auto-detected model for cost estimation.
- Vendored `tokenauditor/data/prices.json` copied from `agent-circuit-breaker` so
  tokenauditor stays self-contained.
- Model auto-detection from transcript fields; fallback to heuristic with a warning.
- `selfcheck.py` asserts a known tape costs a known amount within 1%.

## 0.1.0

### Added
- Initial release: local, read-only token auditor for Claude Code, OpenAI,
  Codex, and agent-vcr tape transcripts.
