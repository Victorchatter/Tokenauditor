"""No-framework self-test. Run: python selfcheck.py"""
import json
import os
import sys
import tempfile

import tokenauditor.parsers.claude_code as cc
import tokenauditor.parsers.codex as codex
import tokenauditor.parsers.openai as oai
import tokenauditor.parsers.tape as tape
from tokenauditor.parsers import detect
from tokenauditor import charts, flags
from tokenauditor.cli import main


def _write(suffix, text):
    p = tempfile.mktemp(suffix=suffix)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _openai_synthetic():
    return json.dumps({
        "tools": [{"type": "function", "function": {"name": "read", "parameters": {}}}],
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ok",
             "tool_calls": [{"id": "c1", "function": {"name": "read", "arguments": '{"p":1}'}}]},
            {"role": "assistant", "content": "again",
             "tool_calls": [{"id": "c2", "function": {"name": "read", "arguments": '{"p":1}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "X" * 4000},
        ],
    })


def _codex_synthetic():
    def L(o): return json.dumps(o)
    lines = [
        L({"type": "session_meta", "payload": {"id": "s1",
           "base_instructions": {"text": "You are Codex, a coding agent."}}}),
        L({"type": "response_item", "payload": {"type": "message", "role": "user",
           "content": [{"type": "input_text", "text": "hi"}]}}),
        L({"type": "response_item", "payload": {"type": "message", "role": "assistant",
           "content": [{"type": "output_text", "text": "ok"}]}}),
        L({"type": "response_item", "payload": {"type": "function_call", "name": "read",
           "arguments": '{"p":1}', "call_id": "c1"}}),
        L({"type": "response_item", "payload": {"type": "function_call_output",
           "call_id": "c1", "output": "X" * 4000}}),
        L({"type": "response_item", "payload": {"type": "message", "role": "assistant",
           "content": [{"type": "output_text", "text": "again"}]}}),
        L({"type": "response_item", "payload": {"type": "function_call", "name": "read",
           "arguments": '{"p":1}', "call_id": "c2"}}),
        L({"type": "event_msg", "payload": {"type": "token_count", "info": {
           "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 50,
                                "output_tokens": 30, "reasoning_output_tokens": 5,
                                "total_tokens": 185}}}}),
    ]
    return "\n".join(lines)


def _claude_synthetic():
    def L(o): return json.dumps(o)
    usages = [
        {"input_tokens": 3, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 0, "output_tokens": 50},
        {"input_tokens": 3, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 3500, "output_tokens": 60},
        {"input_tokens": 3, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 9000, "output_tokens": 70},
        {"input_tokens": 3, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 20000, "output_tokens": 80},
        {"input_tokens": 3, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 30000, "output_tokens": 90},
    ]
    lines = [L({"type": "user", "message": {"role": "user", "content": "hi"}})]
    for i, u in enumerate(usages):
        content = ([{"type": "tool_use", "id": f"tu{i}", "name": "read", "input": {"p": 1}}]
                    if i < 2 else [{"type": "text", "text": "done"}])
        lines.append(L({"type": "assistant", "message": {"role": "assistant", "usage": u, "content": content}}))
        if i < 2:
            lines.append(L({"type": "user", "message": {"role": "user",
                          "content": [{"type": "tool_result", "tool_use_id": f"tu{i}",
                                       "content": "X" * 4000}]}}))
    return "\n".join(lines), sum(u["input_tokens"] + u["cache_creation_input_tokens"]
                                 + u["cache_read_input_tokens"] for u in usages)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_openai():
    p = _write(".json", _openai_synthetic())
    try:
        s = oai.parse(p)
        cats = s.categories
        _assert(cats["total_visible"] == sum(v for k, v in cats.items() if k != "total_visible"),
                "openai: categories must sum to total_visible")
        _assert(s.categories["system+tools_prefix"] > 0, "openai: tools/system prefix missing")
        _assert(not s.prefix_inferred, "openai: prefix must be exact, not inferred")
        fl = {f["flag"] for f in flags.check(s)}
        _assert("HEAVY_TOOL_RESULT" in fl, "openai: HEAVY_TOOL_RESULT should fire")
        _assert("REPEAT_TOOL_CALL" in fl, "openai: REPEAT_TOOL_CALL should fire")
        _assert("CONTEXT_GROWTH" not in fl, "openai: CONTEXT_GROWTH must not fire (no per-turn usage)")
    finally:
        os.remove(p)


def test_codex():
    p = _write(".jsonl", _codex_synthetic())
    try:
        s = codex.parse(p)
        cats = s.categories
        _assert(s.format == "codex", "codex: format must be codex")
        _assert(s.categories["system+tools_prefix"] > 0, "codex: system prefix missing")
        _assert(not s.prefix_inferred, "codex: prefix must be exact (from base_instructions), not inferred")
        _assert(cats["total_visible"] == sum(v for k, v in cats.items() if k != "total_visible"),
                "codex: categories must sum to total_visible")
        _assert(s.reported_total_input == 150, f"codex: reported_total_input {s.reported_total_input} != 150")
        _assert(s.reported_total_output == 35, f"codex: reported_total_output {s.reported_total_output} != 35")
        _assert(cats["tool_results"] > cats["user_text"], "codex: tool_results should exceed user_text")
        fl = {f["flag"] for f in flags.check(s)}
        _assert("HEAVY_TOOL_RESULT" in fl, "codex: HEAVY_TOOL_RESULT should fire")
        _assert("REPEAT_TOOL_CALL" in fl, "codex: REPEAT_TOOL_CALL should fire")
    finally:
        os.remove(p)


def test_claude():
    text, expected_total = _claude_synthetic()
    p = _write(".jsonl", text)
    before = open(p, "rb").read()
    try:
        s = cc.parse(p)
        _assert(s.reported_total_input == expected_total,
                f"claude: reported_total_input {s.reported_total_input} != {expected_total}")
        _assert(s.inferred_prefix > 0 and s.prefix_inferred, "claude: prefix must be inferred > 0")
        fl = {f["flag"] for f in flags.check(s)}
        _assert("CONTEXT_GROWTH" in fl, "claude: CONTEXT_GROWTH should fire")
        _assert("HEAVY_TOOL_RESULT" in fl, "claude: HEAVY_TOOL_RESULT should fire")
        _assert("REPEAT_TOOL_CALL" in fl, "claude: REPEAT_TOOL_CALL should fire")
        _assert(open(p, "rb").read() == before, "claude: transcript file must not change (read-only)")
    finally:
        os.remove(p)


def _tape_synthetic():
    def L(o): return json.dumps(o)
    req = L({"system": "You are careful. " * 30,
             "tools": [{"name": "read", "description": "Read a file",
                        "input_schema": {"type": "object"}}],
             "messages": [{"role": "user", "content": "audit this repo"}]})
    lines = [
        L({"kind": "model_request", "seq": 1, "provider": "anthropic", "body": req}),
        L({"kind": "tool_call", "seq": 2, "server": "fs", "tool": "read",
           "args": {"p": "/big.py"}, "args_hash": "h1"}),
        L({"kind": "tool_result", "seq": 3, "server": "fs", "tool": "read",
           "args_hash": "h1", "result": {"text": "x = 1" * 2000}}),
        L({"kind": "model_response", "seq": 4, "provider": "anthropic",
           "body": L({"content": [{"type": "text", "text": "Found it."}]}),
           "usage": {"input_tokens": 9000, "cache_read_input_tokens": 1200,
                     "output_tokens": 40}}),
    ]
    return "\n".join(lines) + "\n"


def test_tape():
    """agent-vcr tape -> tokenauditor.

    This is the cross-tool interop the LocalLab README advertises. Without a
    test it rots silently, and the family claim stops being true.
    """
    p = _write(".jsonl", _tape_synthetic())
    before = open(p, "rb").read()
    try:
        _assert(detect.detect(p) == "tape", "tape: detect must return 'tape'")
        s = tape.parse(p)
        _assert(s.format == "agent_vcr_tape", f"tape: format {s.format}")
        _assert(len(s.turns) == 1, f"tape: expected 1 turn, got {len(s.turns)}")
        _assert(s.reported_total_input == 10200,
                f"tape: reported_total_input {s.reported_total_input} != 10200")
        # A tape records the raw request, so the prefix is COUNTED, not inferred.
        _assert(s.inferred_prefix > 0 and not s.prefix_inferred,
                "tape: prefix must be counted exactly, not inferred")
        _assert(s.categories["user_text"] > 0,
                "tape: user_text must be populated, else HEAVY_TOOL_RESULT never fires")
        fl = {f["flag"] for f in flags.check(s)}
        _assert("HEAVY_TOOL_RESULT" in fl, "tape: HEAVY_TOOL_RESULT should fire")
        _assert(open(p, "rb").read() == before,
                "tape: transcript must not change (read-only)")
    finally:
        os.remove(p)


def test_cli_exit_codes():
    p = _write(".json", _openai_synthetic())
    saved_out, saved_err = sys.stdout, sys.stderr
    devnull = open(os.devnull, "w", encoding="utf-8")
    try:
        sys.stdout = sys.stderr = devnull
        _assert(main([p]) == 0, "cli: success must exit 0")
        _assert(main([p, "--json"]) == 0, "cli: --json must exit 0")
        _assert(main([p, "--by-turn"]) == 0, "cli: --by-turn must exit 0")
        _assert(main([os.path.join(tempfile.gettempdir(), "definitely_missing_tokenauditor.json")]) == 2,
                "cli: missing file must exit 2")
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
        devnull.close()
        os.remove(p)


def test_charts():
    text, _expected_total = _claude_synthetic()
    p = _write(".jsonl", text)
    try:
        s = cc.parse(p)
        bar = charts.category_bar_svg(s)
        _assert(bar.startswith("<svg") and "</svg>" in bar, "charts: bar.svg must be a valid SVG")
        area = charts.turn_area_svg(s)
        _assert(area.startswith("<svg") and "</svg>" in area,
                "charts: area.svg must be a valid SVG for transcripts with usage")
    finally:
        os.remove(p)


def main_selfcheck():
    test_openai()
    test_codex()
    test_claude()
    test_tape()
    test_charts()
    test_cli_exit_codes()
    print("selfcheck OK")


if __name__ == "__main__":
    try:
        main_selfcheck()
    except AssertionError as e:
        print(f"selfcheck FAIL: {e}", file=sys.stderr)
        sys.exit(1)