# Changelog

## 0.3.0

### Added
- `--cost-threshold USD` (default `0.10`) warns when a turn's estimated cost exceeds
  the threshold while using `--cost` or `--cost-json`.
- `EXPENSIVE_TURN` cost warning: fired when a single turn's cost_total exceeds
  `--cost-threshold`.
- `EXPENSIVE_TOOL` cost warning: fired when a tool result's token count is larger
  than the turn's reported `total_input + output`.
- Cost warnings are rendered below the total in `--cost` tables and included as a
  top-level `warnings` array in `--cost-json` output.
- `selfcheck.py` exercises both cost warnings and asserts `--cost-json` includes them.

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
