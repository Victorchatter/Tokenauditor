# tokenauditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local, read-only CLI that parses a Claude Code JSONL or OpenAI messages transcript and reports a per-turn token breakdown plus three waste flags.

**Architecture:** Parsers turn a file into a normalized `Session` (turns + estimated category counts + reported usage). `flags` computes waste flags from the `Session`. `report` renders a terminal table or JSON. `cli` wires argv → parse → flags → render. Two parallel counts: authoritative Anthropic `usage` (labeled "reported") and a tiktoken estimate over visible blocks (labeled "approx, tiktoken"), with the hidden system+tools prefix inferred from the first turn's cache creation.

**Tech Stack:** Python 3.9+, `tiktoken` (only runtime dep), stdlib `argparse`/`json`/`hashlib`. No test framework — one `selfcheck.py`.

## Global Constraints

- Read-only: open files with `open(path, "r", encoding="utf-8")` only. Never write to the transcript file.
- Fully local/offline: no network, no API keys, no telemetry.
- Python 3.9+ (`pipx install .`).
- One runtime dependency: `tiktoken`.
- Ponytail: stdlib first, shortest working diff, no unrequested abstractions. Mark simplifications with `# ponytail:` comments naming ceiling + upgrade path.
- Estimated counts use tiktoken `cl100k_base`, labeled `(approx, tiktoken)` for Anthropic content (exact for OpenAI).
- Exit codes: 0 success, 2 unreadable/unknown-format file.
- MIT license.
- Repo is the clean inner git repo at `C:/Users/Victor/tokenauditor` (the home-dir repo is out of scope — never `git add` outside this directory). Remote to set: `https://github.com/Victorchatter/Tokenauditor`.
- Line endings: files written with `\n`; git CRLF warnings are harmless.

---

## File Structure

- `pyproject.toml` — packaging, entry point `tokenauditor = "tokenauditor.cli:main"`, dep `tiktoken`.
- `LICENSE` — MIT.
- `README.md` — install + example output.
- `selfcheck.py` — no-framework self-test with two synthetic transcripts.
- `tokenauditor/__init__.py` — version string.
- `tokenauditor/__main__.py` — `python -m tokenauditor` shim.
- `tokenauditor/cli.py` — argparse, provider detect, parse, flags, render, exit codes.
- `tokenauditor/counters.py` — tiktoken wrappers + `usage_total`.
- `tokenauditor/parsers/__init__.py` — `Session`/`Turn` dataclasses (shared model).
- `tokenauditor/parsers/claude_code.py` — JSONL → `Session`.
- `tokenauditor/parsers/openai.py` — messages JSON → `Session`.
- `tokenauditor/parsers/detect.py` — first-line sniff → parser choice.
- `tokenauditor/flags.py` — three waste-flag rules.
- `tokenauditor/report.py` — table + JSON renderers.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `tokenauditor/__init__.py`, `tokenauditor/__main__.py`, `tokenauditor/cli.py`

**Interfaces:**
- Produces: `tokenauditor.cli.main(argv=None) -> int` (stub returning 0); `tokenauditor.__version__`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["flit-core>=3.4"]
build-backend = "flit_core.buildapi"

[project]
name = "tokenauditor"
version = "0.1.0"
description = "Local, read-only CLI that audits where an AI agent session's token budget went."
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.9"
authors = [{name = "Victor"}]
dependencies = ["tiktoken>=0.5"]

[project.scripts]
tokenauditor = "tokenauditor.cli:main"

[tool.flit.module]
name = "tokenauditor"
```

- [ ] **Step 2: Write `LICENSE`** (MIT, year 2026, author Victor). Standard MIT text.

- [ ] **Step 3: Write `tokenauditor/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Write `tokenauditor/__main__.py`**

```python
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Write `tokenauditor/cli.py` stub**

```python
def main(argv=None):
    # ponytail: stub — wired up in Task 8
    return 0
```

- [ ] **Step 6: Verify `python -m tokenauditor` runs and exits 0**

Run: `python -m tokenauditor; echo "exit=$?"`
Expected: `exit=0`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml LICENSE tokenauditor/
git commit -m "scaffold: package, entry point, stub CLI"
```

---

## Task 2: Token counters

**Files:**
- Create: `tokenauditor/counters.py`

**Interfaces:**
- Produces: `count_text(s: str) -> int`, `count_json(obj) -> int`, `usage_total(u: dict) -> int`.

- [ ] **Step 1: Write `tokenauditor/counters.py`**

```python
import json
import tiktoken

_ENC = None


def _enc():
    # ponytail: process-global encoder; per-call get_encoding reloads the BPE table (~ms).
    global _ENC
    if _ENC is None:
        _ENC = tiktoken.get_encoding("cl100k_base")
    return _ENC


def count_text(s: str) -> int:
    if not s:
        return 0
    return len(_enc().encode(s))


def count_json(obj) -> int:
    return count_text(json.dumps(obj, sort_keys=True, ensure_ascii=False))


def usage_total(u: dict) -> int:
    # ponytail: Anthropic usage only; missing keys -> 0. OpenAI has no per-turn usage here.
    if not u:
        return 0
    return (
        u.get("input_tokens", 0)
        + u.get("cache_creation_input_tokens", 0)
        + u.get("cache_read_input_tokens", 0)
    )
```

- [ ] **Step 2: Verify with an inline check**

Run:
```bash
python -c "from tokenauditor.counters import count_text, count_json, usage_total; assert count_text('hello world')>0; assert count_json({'b':1,'a':2})==count_text('{\"a\": 2, \"b\": 1}'); assert usage_total({'input_tokens':3,'cache_creation_input_tokens':100,'cache_read_input_tokens':50})==153; assert usage_total({})==0; print('counters OK')"
```
Expected: `counters OK`

- [ ] **Step 3: Commit**

```bash
git add tokenauditor/counters.py
git commit -m "feat: token counters (tiktoken + usage_total)"
```

---

## Task 3: Session model + OpenAI parser

**Files:**
- Create: `tokenauditor/parsers/__init__.py`, `tokenauditor/parsers/openai.py`

**Interfaces:**
- Produces: `Session` dataclass, `Turn` dataclass (defined in `parsers/__init__.py`); `openai.parse(path: str) -> Session`.

**Session/Turn contract (used by all later tasks):**

```python
@dataclass
class Turn:
    index: int                 # 1-based
    total_input: int           # reported Anthropic total_input; 0 for OpenAI
    cache_creation: int        # reported; 0 for OpenAI
    cache_read: int            # reported; 0 for OpenAI
    output: int                # reported output_tokens; 0 for OpenAI
    added_user_text: int       # estimated tokens of new user text since prev turn
    added_tool_results: int    # estimated tokens of new tool results since prev turn
    tool_results: list          # list of (tool_name:str, tokens:int)
    tool_calls: list            # list of (tool_name:str, input_hash:str)

@dataclass
class Session:
    format: str                # "claude_code" | "openai"
    turns: list                # list[Turn]
    categories: dict            # estimated: {"system+tools_prefix","user_text","assistant_text","thinking","tool_use_args","tool_results","total_visible"}
    inferred_prefix: int       # system+tools size (inferred for claude_code, exact for openai)
    prefix_inferred: bool      # True for claude_code, False for openai
    reported_total_input: int   # sum of per-turn total_input (claude_code) or 0 (openai)
    reported_total_output: int  # sum of per-turn output (claude_code) or 0 (openai)
```

- [ ] **Step 1: Write `tokenauditor/parsers/__init__.py`** with the dataclasses above plus `from dataclasses import dataclass, field`. `tool_results`/`tool_calls` default to `field(default_factory=list)`.

```python
from dataclasses import dataclass, field


@dataclass
class Turn:
    index: int
    total_input: int = 0
    cache_creation: int = 0
    cache_read: int = 0
    output: int = 0
    added_user_text: int = 0
    added_tool_results: int = 0
    tool_results: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)


@dataclass
class Session:
    format: str
    turns: list = field(default_factory=list)
    categories: dict = field(default_factory=dict)
    inferred_prefix: int = 0
    prefix_inferred: bool = False
    reported_total_input: int = 0
    reported_total_output: int = 0
```

- [ ] **Step 2: Write `tokenauditor/parsers/openai.py`**

```python
import json
from . import Session, Turn
from ..counters import count_text, count_json


def parse(path: str) -> Session:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        messages = data
        tools = []
    elif isinstance(data, dict):
        messages = data.get("messages", [])
        tools = data.get("tools", []) or []
    else:
        raise ValueError("openai: expected a messages array or object with 'messages'")

    cats = {"system+tools_prefix": 0, "user_text": 0, "assistant_text": 0,
            "thinking": 0, "tool_use_args": 0, "tool_results": 0, "total_visible": 0}
    cats["system+tools_prefix"] = count_json(tools) + sum(
        count_text(m.get("content") or "") for m in messages if m.get("role") == "system"
    )

    # ponytail: index tool_call_id -> tool name for role:tool results (no nested lookup needed here)
    pending = {}  # tool_call_id -> tool_name
    turns = []
    turn_idx = 0
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "user":
            cats["user_text"] += count_text(content if isinstance(content, str) else json.dumps(content))
        elif role == "assistant":
            turn_idx += 1
            t = Turn(index=turn_idx)
            cats["assistant_text"] += count_text(content if isinstance(content, str) else json.dumps(content))
            for tc in m.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                args = fn.get("arguments", "")
                cats["tool_use_args"] += count_text(args) if isinstance(args, str) else count_json(args)
                t.tool_calls.append((name, _hash(args)))
                pending[tc.get("id")] = name
            turns.append(t)
        elif role == "tool":
            name = pending.get(m.get("tool_call_id"), "?")
            tok = count_text(content if isinstance(content, str) else json.dumps(content))
            cats["tool_results"] += tok
            if turns:
                turns[-1].tool_results.append((name, tok))
                turns[-1].added_tool_results += tok
    cats["total_visible"] = sum(v for k, v in cats.items() if k != "total_visible")
    return Session(format="openai", turns=turns, categories=cats,
                   inferred_prefix=cats["system+tools_prefix"], prefix_inferred=False,
                   reported_total_input=0, reported_total_output=0)


def _hash(args) -> str:
    import hashlib
    s = args if isinstance(args, str) else json.dumps(args, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Verify with an inline synthetic**

Run:
```bash
python -c "
import json, tempfile, os
from tokenauditor.parsers import openai
msgs={'tools':[{'type':'function','function':{'name':'read','parameters':{}}}],
 'messages':[
  {'role':'system','content':'You are helpful.'},
  {'role':'user','content':'hi'},
  {'role':'assistant','content':'ok','tool_calls':[{'id':'c1','function':{'name':'read','arguments':'{\"p\":1}'}}]},
  {'role':'assistant','content':'again','tool_calls':[{'id':'c2','function':{'name':'read','arguments':'{\"p\":1}'}}]},
  {'role':'tool','tool_call_id':'c1','content':'X'*4000},
 ]}
p=tempfile.mktemp(suffix='.json'); open(p,'w',encoding='utf-8').write(json.dumps(msgs))
s=openai.parse(p)
assert s.format=='openai'
assert s.categories['system+tools_prefix']>0
assert s.categories['tool_results']>s.categories['user_text']
assert s.categories['total_visible']==sum(v for k,v in s.categories.items() if k!='total_visible')
assert s.turns[0].tool_calls[0][0]=='read'
assert s.turns[1].tool_calls[0][0]=='read'
assert s.turns[0].tool_calls[0][1]==s.turns[1].tool_calls[0][1]
os.remove(p)
print('openai OK')
"
```
Expected: `openai OK`

- [ ] **Step 4: Commit**

```bash
git add tokenauditor/parsers/__init__.py tokenauditor/parsers/openai.py
git commit -m "feat: Session model + OpenAI messages parser"
```

---

## Task 4: Claude Code JSONL parser

**Files:**
- Create: `tokenauditor/parsers/claude_code.py`

**Interfaces:**
- Consumes: `Session`, `Turn` from `parsers/__init__.py`; `count_text`, `count_json`, `usage_total` from `counters`.
- Produces: `claude_code.parse(path: str) -> Session`.

- [ ] **Step 1: Write `tokenauditor/parsers/claude_code.py`**

```python
import json
from . import Session, Turn
from ..counters import count_text, count_json, usage_total


def parse(path: str) -> Session:
    cats = {"system+tools_prefix": 0, "user_text": 0, "assistant_text": 0,
            "thinking": 0, "tool_use_args": 0, "tool_results": 0, "total_visible": 0}
    turns = []
    # tool_use_id -> tool_name, for resolving tool_result blocks
    pending_tools = {}
    # pending user content (text + tool_results) not yet attached to a turn
    pending_user_text = 0
    pending_tool_results = []  # list of (tool_name, tokens)
    pending_tool_results_tok = 0
    first_total_input = None
    first_user_text_tok = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = o.get("type")
            if t == "assistant":
                msg = o.get("message", {})
                u = msg.get("usage", {}) or {}
                ti = usage_total(u)
                if first_total_input is None:
                    first_total_input = ti
                turn = Turn(
                    index=len(turns) + 1,
                    total_input=ti,
                    cache_creation=u.get("cache_creation_input_tokens", 0),
                    cache_read=u.get("cache_read_input_tokens", 0),
                    output=u.get("output_tokens", 0),
                    added_user_text=pending_user_text,
                    added_tool_results=pending_tool_results_tok,
                    tool_results=list(pending_tool_results),
                )
                for b in msg.get("content", []):
                    bt = b.get("type")
                    if bt == "text":
                        cats["assistant_text"] += count_text(b.get("text", ""))
                    elif bt == "thinking":
                        cats["thinking"] += count_text(b.get("thinking", ""))
                    elif bt == "tool_use":
                        name = b.get("name", "?")
                        args = b.get("input", {})
                        cats["tool_use_args"] += count_json(args)
                        turn.tool_calls.append((name, _hash(args)))
                        pending_tools[b.get("id")] = name
                turns.append(turn)
                # reset pending
                pending_user_text = 0
                pending_tool_results = []
                pending_tool_results_tok = 0
            elif t == "user":
                msg = o.get("message", {})
                c = msg.get("content")
                if isinstance(c, str):
                    tok = count_text(c)
                    if first_user_text_tok is None:
                        first_user_text_tok = tok
                    cats["user_text"] += tok
                    pending_user_text += tok
                elif isinstance(c, list):
                    for b in c:
                        bt = b.get("type")
                        if bt == "text":
                            tok = count_text(b.get("text", ""))
                            if first_user_text_tok is None:
                                first_user_text_tok = tok
                            cats["user_text"] += tok
                            pending_user_text += tok
                        elif bt == "tool_result":
                            name = pending_tools.get(b.get("tool_use_id")) or _tool_name_from_result(o)
                            content = b.get("content")
                            tok = count_text(content if isinstance(content, str) else json.dumps(content))
                            cats["tool_results"] += tok
                            pending_tool_results.append((name, tok))
                            pending_tool_results_tok += tok

    # ponytail: inferred prefix = first turn's total input minus first user message tokens.
    # Conflates system prompt + tool defs (not separable from this transcript).
    inferred = 0
    if first_total_input is not None:
        inferred = max(0, first_total_input - (first_user_text_tok or 0))
    cats["system+tools_prefix"] = inferred
    cats["total_visible"] = sum(v for k, v in cats.items() if k != "total_visible")

    return Session(
        format="claude_code",
        turns=turns,
        categories=cats,
        inferred_prefix=inferred,
        prefix_inferred=True,
        reported_total_input=sum(t.total_input for t in turns),
        reported_total_output=sum(t.output for t in turns),
    )


def _tool_name_from_result(o):
    tr = o.get("toolUseResult")
    if isinstance(tr, dict):
        return tr.get("name") or tr.get("tool") or "?"
    return "?"


def _hash(obj) -> str:
    import hashlib
    s = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()
```

- [ ] **Step 2: Verify with an inline synthetic**

Run:
```bash
python -c "
import json, tempfile, os
from tokenauditor.parsers import claude_code
def L(o): return json.dumps(o)
lines=[
 L({'type':'user','message':{'role':'user','content':'hi'}}),
 L({'type':'assistant','message':{'role':'assistant','usage':{'input_tokens':3,'cache_creation_input_tokens':1000,'cache_read_input_tokens':0,'output_tokens':50},'content':[{'type':'tool_use','id':'tu1','name':'read','input':{'p':1}}]}}),
 L({'type':'user','message':{'role':'user','content':[{'type':'tool_result','tool_use_id':'tu1','content':'X'*4000}]}}),
 L({'type':'assistant','message':{'role':'assistant','usage':{'input_tokens':3,'cache_creation_input_tokens':10,'cache_read_input_tokens':3500,'output_tokens':60},'content':[{'type':'tool_use','id':'tu2','name':'read','input':{'p':1}}]}}),
 L({'type':'user','message':{'role':'user','content':[{'type':'tool_result','tool_use_id':'tu2','content':'Y'*4000}]}}),
 L({'type':'assistant','message':{'role':'assistant','usage':{'input_tokens':3,'cache_creation_input_tokens':10,'cache_read_input_tokens':9000,'output_tokens':70},'content':[{'type':'text','text':'done'}]}}),
]
p=tempfile.mktemp(suffix='.jsonl'); open(p,'w',encoding='utf-8').write('\n'.join(lines))
s=claude_code.parse(p)
assert s.format=='claude_code'
assert len(s.turns)==3
assert s.reported_total_input==1000+3513+9013
assert s.inferred_prefix>0 and s.prefix_inferred
assert s.categories['tool_results']>s.categories['user_text']
assert s.turns[0].tool_calls[0][0]=='read'
assert s.turns[0].tool_calls[0][1]==s.turns[1].tool_calls[0][1]
assert s.categories['total_visible']==sum(v for k,v in s.categories.items() if k!='total_visible')
os.remove(p)
print('claude_code OK')
"
```
Expected: `claude_code OK`

- [ ] **Step 3: Commit**

```bash
git add tokenauditor/parsers/claude_code.py
git commit -m "feat: Claude Code JSONL parser with inferred prefix"
```

---

## Task 5: Provider detection

**Files:**
- Create: `tokenauditor/parsers/detect.py`

**Interfaces:**
- Produces: `detect(path: str) -> str` returning `"claude_code"` or `"openai"`; raises `ValueError` on unknown format.

- [ ] **Step 1: Write `tokenauditor/parsers/detect.py`**

```python
import json


def detect(path: str) -> str:
    # ponytail: first-line sniff. Claude Code lines are JSON objects with type/message;
    # OpenAI is a top-level array or {messages:...}. Sniff, don't configure.
    with open(path, "r", encoding="utf-8") as f:
        first = ""
        for line in f:
            first = line.strip()
            if first:
                break
    try:
        o = json.loads(first)
    except json.JSONDecodeError as e:
        raise ValueError(f"unrecognized transcript format (first line not JSON: {e})")
    if isinstance(o, list):
        return "openai"
    if isinstance(o, dict):
        if "messages" in o:
            return "openai"
        if "type" in o and "message" in o:
            return "claude_code"
    raise ValueError("unrecognized transcript format (expected Claude Code JSONL or OpenAI messages JSON)")
```

- [ ] **Step 2: Verify**

Run:
```bash
python -c "
import tempfile, os, json
from tokenauditor.parsers import detect
p1=tempfile.mktemp(suffix='.jsonl'); open(p1,'w',encoding='utf-8').write(json.dumps({'type':'assistant','message':{'role':'assistant'}})); assert detect(p1)=='claude_code'; os.remove(p1)
p2=tempfile.mktemp(suffix='.json'); open(p2,'w',encoding='utf-8').write(json.dumps({'messages':[]})); assert detect(p2)=='openai'; os.remove(p2)
p3=tempfile.mktemp(suffix='.json'); open(p3,'w',encoding='utf-8').write(json.dumps([{'role':'user','content':'hi'}])); assert detect(p3)=='openai'; os.remove(p3)
print('detect OK')
"
```
Expected: `detect OK`

- [ ] **Step 3: Commit**

```bash
git add tokenauditor/parsers/detect.py
git commit -m "feat: provider detection by first-line sniff"
```

---

## Task 6: Waste flags

**Files:**
- Create: `tokenauditor/flags.py`

**Interfaces:**
- Consumes: `Session` from `parsers`.
- Produces: `check(session: Session) -> list[dict]`, each dict `{flag: str, message: str, turn: int|None}`.

- [ ] **Step 1: Write `tokenauditor/flags.py`**

```python
from .parsers import Session


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
                    "message": f"HEAVY_TOOL_RESULT: {name} result ~{tok}tok > all user turns combined (~{user_total}tok) at turn {t.index}",
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
        "message": f"CONTEXT_GROWTH: context grew ~{fm}tok -> ~{lm}tok ({lm/fm:.1f}x) from first to last quarter",
        "turn": None,
    }]


def _repeat_tool_call(s: Session) -> list:
    seen = {}  # (name, hash) -> [turn indexes]
    for t in s.turns:
        for name, h in t.tool_calls:
            seen.setdefault((name, h), []).append(t.index)
    out = []
    for (name, h), idxs in seen.items():
        if len(idxs) >= 2:
            out.append({
                "flag": "REPEAT_TOOL_CALL",
                "message": f"REPEAT_TOOL_CALL: {name} called {len(idxs)} times with identical input (first at turn {idxs[0]})",
                "turn": idxs[0],
            })
    return out
```

- [ ] **Step 2: Verify against the OpenAI synthetic from Task 3**

Run:
```bash
python -c "
import json, tempfile, os
from tokenauditor.parsers import openai
from tokenauditor import flags
msgs={'messages':[
  {'role':'user','content':'hi'},
  {'role':'assistant','content':'ok','tool_calls':[{'id':'c1','function':{'name':'read','arguments':'{\"p\":1}'}}]},
  {'role':'assistant','content':'again','tool_calls':[{'id':'c2','function':{'name':'read','arguments':'{\"p\":1}'}}]},
  {'role':'tool','tool_call_id':'c1','content':'X'*4000},
 ]}
p=tempfile.mktemp(suffix='.json'); open(p,'w',encoding='utf-8').write(json.dumps(msgs))
s=openai.parse(p); fl=flags.check(s)
names={f['flag'] for f in fl}
assert 'HEAVY_TOOL_RESULT' in names
assert 'REPEAT_TOOL_CALL' in names
assert 'CONTEXT_GROWTH' not in names
os.remove(p)
print('flags OK')
"
```
Expected: `flags OK`

- [ ] **Step 3: Commit**

```bash
git add tokenauditor/flags.py
git commit -m "feat: three waste flags (heavy tool result, context growth, repeat tool call)"
```

---

## Task 7: Report renderers

**Files:**
- Create: `tokenauditor/report.py`

**Interfaces:**
- Consumes: `Session`, flags list.
- Produces: `render_table(session, flags, by_turn=False) -> str`, `render_json(session, flags, by_turn=False) -> str`.

- [ ] **Step 1: Write `tokenauditor/report.py`**

```python
import json
from .parsers import Session


def _fmt(n: int) -> str:
    return f"{n:,}"


def render_table(session: Session, flags: list, by_turn: bool = False) -> str:
    L = []
    L.append(f"tokenauditor — {session.format}, {len(session.turns)} turn(s)")
    L.append("")
    L.append(f"  Reported total input  (sum over turns): {_fmt(session.reported_total_input)}")
    L.append(f"  Reported total output:                  {_fmt(session.reported_total_output)}")
    label = "inferred" if session.prefix_inferred else "exact"
    L.append(f"  System+tools prefix:                    ~{_fmt(session.inferred_prefix)}  ({label})")
    L.append("")
    L.append("  Estimated breakdown (approx, tiktoken):")
    cats = session.categories
    order = ["system+tools_prefix", "user_text", "assistant_text", "thinking",
             "tool_use_args", "tool_results"]
    biggest = max(order, key=lambda k: cats.get(k, 0))
    for k in order:
        v = cats.get(k, 0)
        mark = "  <-- largest" if k == biggest and v else ""
        L.append(f"    {k:<22} ~{_fmt(v):>10}{mark}")
    L.append("    " + "-" * 34)
    L.append(f"    {'total_visible':<22} ~{_fmt(cats.get('total_visible', 0)):>10}")
    L.append("")
    if by_turn:
        L.append("  Per turn:")
        L.append(f"    {'#':>3} {'input':>10} {'cache_r':>10} {'cache_c':>10} {'out':>8} {'+usr':>7} {'+tools':>8}")
        for t in session.turns:
            L.append(f"    {t.index:>3} {_fmt(t.total_input):>10} {_fmt(t.cache_read):>10} "
                      f"{_fmt(t.cache_creation):>10} {_fmt(t.output):>8} {t.added_user_text:>7} "
                      f"{t.added_tool_results:>8}")
        L.append("")
    L.append("  Flags:")
    if flags:
        for f in flags:
            L.append(f"    {f['message']}")
    else:
        L.append("    (none)")
    return "\n".join(L) + "\n"


def render_json(session: Session, flags: list, by_turn: bool = False) -> str:
    out = {
        "format": session.format,
        "turns": len(session.turns),
        "reported": {"total_input": session.reported_total_input,
                     "total_output": session.reported_total_output},
        "inferred_prefix": session.inferred_prefix,
        "prefix_inferred": session.prefix_inferred,
        "estimated": session.categories,
        "flags": flags,
    }
    if by_turn:
        out["by_turn"] = [
            {"turn": t.index, "total_input": t.total_input, "cache_read": t.cache_read,
             "cache_creation": t.cache_creation, "output": t.output,
             "added_user_text": t.added_user_text, "added_tool_results": t.added_tool_results}
            for t in session.turns
        ]
    return json.dumps(out, indent=2) + "\n"
```

- [ ] **Step 2: Verify renderers don't crash and JSON round-trips**

Run:
```bash
python -c "
import json, tempfile, os
from tokenauditor.parsers import openai
from tokenauditor import flags, report
msgs={'messages':[{'role':'user','content':'hi'},{'role':'assistant','content':'ok'}]}
p=tempfile.mktemp(suffix='.json'); open(p,'w',encoding='utf-8').write(json.dumps(msgs))
s=openai.parse(p); fl=flags.check(s)
assert 'tokenauditor' in report.render_table(s, fl)
assert 'tokenauditor' in report.render_table(s, fl, by_turn=True)
j=report.render_json(s, fl, by_turn=True); json.loads(j)
os.remove(p)
print('report OK')
"
```
Expected: `report OK`

- [ ] **Step 3: Commit**

```bash
git add tokenauditor/report.py
git commit -m "feat: table + JSON report renderers"
```

---

## Task 8: CLI wiring

**Files:**
- Modify: `tokenauditor/cli.py`

**Interfaces:**
- Consumes: `parsers.detect.detect`, `parsers.claude_code.parse`, `parsers.openai.parse`, `flags.check`, `report.render_table`, `report.render_json`.

- [ ] **Step 1: Replace `tokenauditor/cli.py`**

```python
import argparse
import sys

from .parsers import detect, claude_code, openai
from . import flags as flags_mod
from . import report


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
        session = claude_code.parse(args.file) if fmt == "claude_code" else openai.parse(args.file)
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
```

- [ ] **Step 2: Verify CLI end-to-end on a temp OpenAI file**

Run:
```bash
python -c "
import json, tempfile
msgs={'messages':[{'role':'user','content':'hi'},{'role':'assistant','content':'ok','tool_calls':[{'id':'c1','function':{'name':'read','arguments':'{\"p\":1}'}}]},{'role':'tool','tool_call_id':'c1','content':'X'*4000}]}
open('tmp_transcript.json','w',encoding='utf-8').write(json.dumps(msgs))
"
python -m tokenauditor tmp_transcript.json | grep -q tokenauditor && echo "table OK"
python -m tokenauditor tmp_transcript.json --flags | grep -q HEAVY_TOOL_RESULT && echo "flags OK"
python -m tokenauditor tmp_transcript.json --json | python -c "import sys,json; json.load(sys.stdin); print('json OK')"
python -m tokenauditor /no/such/file; echo "exit=$?"
rm -f tmp_transcript.json
```
Expected: `table OK`, `flags OK`, `json OK`, then `exit=2` for the missing file.

- [ ] **Step 3: Commit**

```bash
git add tokenauditor/cli.py
git commit -m "feat: CLI wiring (argparse, detect, flags, render, exit codes)"
```

---

## Task 9: selfcheck.py

**Files:**
- Create: `selfcheck.py` (repo root, runnable as `python selfcheck.py`)

**Interfaces:**
- Consumes: `tokenauditor.parsers.{openai,claude_code}`, `tokenauditor.flags`, `tokenauditor.cli`.

- [ ] **Step 1: Write `selfcheck.py`**

```python
"""No-framework self-test. Run: python selfcheck.py"""
import json
import os
import sys
import tempfile

import tokenauditor.parsers.openai as oai
import tokenauditor.parsers.claude_code as cc
from tokenauditor import flags
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


def _claude_synthetic():
    def L(o): return json.dumps(o)
    lines = [
        L({"type": "user", "message": {"role": "user", "content": "hi"}}),
        L({"type": "assistant", "message": {"role": "assistant",
           "usage": {"input_tokens": 3, "cache_creation_input_tokens": 1000,
                     "cache_read_input_tokens": 0, "output_tokens": 50},
           "content": [{"type": "tool_use", "id": "tu1", "name": "read", "input": {"p": 1}}]}}),
        L({"type": "user", "message": {"role": "user",
           "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "X" * 4000}]}}),
        L({"type": "assistant", "message": {"role": "assistant",
           "usage": {"input_tokens": 3, "cache_creation_input_tokens": 10,
                     "cache_read_input_tokens": 3500, "output_tokens": 60},
           "content": [{"type": "tool_use", "id": "tu2", "name": "read", "input": {"p": 1}}]}}),
        L({"type": "user", "message": {"role": "user",
           "content": [{"type": "tool_result", "tool_use_id": "tu2", "content": "Y" * 4000}]}}),
        L({"type": "assistant", "message": {"role": "assistant",
           "usage": {"input_tokens": 3, "cache_creation_input_tokens": 10,
                     "cache_read_input_tokens": 9000, "output_tokens": 70},
           "content": [{"type": "text", "text": "done"}]}}),
        L({"type": "assistant", "message": {"role": "assistant",
           "usage": {"input_tokens": 3, "cache_creation_input_tokens": 10,
                     "cache_read_input_tokens": 20000, "output_tokens": 80},
           "content": [{"type": "text", "text": "more"}]}}),
        L({"type": "assistant", "message": {"role": "assistant",
           "usage": {"input_tokens": 3, "cache_creation_input_tokens": 10,
                     "cache_read_input_tokens": 30000, "output_tokens": 90},
           "content": [{"type": "text", "text": "end"}]}}),
    ]
    return "\n".join(lines)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_openai():
    p = _write(".json", _openai_synthetic())
    try:
        s = oai.parse(p)
        cats = s.categories
        # breakdown sums to total_visible
        _assert(cats["total_visible"] == sum(v for k, v in cats.items() if k != "total_visible"),
                "openai: categories must sum to total_visible")
        # tools counted in prefix
        _assert(s.categories["system+tools_prefix"] > 0, "openai: tools/system prefix missing")
        _assert(not s.prefix_inferred, "openai: prefix must be exact, not inferred")
        fl = {f["flag"] for f in flags.check(s)}
        _assert("HEAVY_TOOL_RESULT" in fl, "openai: HEAVY_TOOL_RESULT should fire")
        _assert("REPEAT_TOOL_CALL" in fl, "openai: REPEAT_TOOL_CALL should fire")
        _assert("CONTEXT_GROWTH" not in fl, "openai: CONTEXT_GROWTH must not fire (no per-turn usage)")
    finally:
        os.remove(p)


def test_claude():
    p = _write(".jsonl", _claude_synthetic())
    before = open(p, "rb").read()
    try:
        s = cc.parse(p)
        # usage parsed and summed
        expected = (1000 + 3513 + 9013 + 20013 + 30013)
        _assert(s.reported_total_input == expected,
                f"claude: reported_total_input {s.reported_total_input} != {expected}")
        _assert(s.inferred_prefix > 0 and s.prefix_inferred, "claude: prefix must be inferred > 0")
        fl = {f["flag"] for f in flags.check(s)}
        _assert("CONTEXT_GROWTH" in fl, "claude: CONTEXT_GROWTH should fire")
        _assert("HEAVY_TOOL_RESULT" in fl, "claude: HEAVY_TOOL_RESULT should fire")
        _assert("REPEAT_TOOL_CALL" in fl, "claude: REPEAT_TOOL_CALL should fire")
        # read-only: file unchanged
        _assert(open(p, "rb").read() == before, "claude: transcript file must not change")
    finally:
        os.remove(p)


def test_cli_exit_codes():
    p = _write(".json", _openai_synthetic())
    try:
        _assert(main([p]) == 0, "cli: success must exit 0")
        _assert(main([p, "--json"]) == 0, "cli: --json must exit 0")
        _assert(main(["/no/such/file"]) == 2, "cli: missing file must exit 2")
    finally:
        os.remove(p)


def main_selfcheck():
    test_openai()
    test_claude()
    test_cli_exit_codes()
    print("selfcheck OK")


if __name__ == "__main__":
    try:
        main_selfcheck()
    except AssertionError as e:
        print(f"selfcheck FAIL: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 2: Run the selfcheck**

Run: `python selfcheck.py`
Expected: `selfcheck OK`

- [ ] **Step 3: Commit**

```bash
git add selfcheck.py
git commit -m "test: selfcheck.py (openai + claude synthetic + cli exit codes)"
```

---

## Task 10: README, install verification, push to remote

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
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
tokenauditor — claude_code, 306 turn(s)

  Reported total input  (sum over turns): 1,234,567
  Reported total output:                  45,678
  System+tools prefix:                    ~12,345  (inferred)

  Estimated breakdown (approx, tiktoken):
    system+tools_prefix   ~    12,345
    user_text             ~     3,210
    assistant_text        ~     8,765
    thinking              ~     5,432
    tool_use_args         ~     2,109
    tool_results          ~    98,765  <-- largest
    ----------------------------------
    total_visible         ~   128,286

  Flags:
    HEAVY_TOOL_RESULT: browser_snapshot result ~42000tok > all user turns (~3210tok) at turn 14
    CONTEXT_GROWTH: context grew ~18000tok -> ~52000tok (2.9x) from first to last quarter
    REPEAT_TOOL_CALL: Read called 3 times with identical input (first at turn 7)
```

## Two counts, on purpose

A recorded Claude Code transcript does not store the system prompt or tool definitions as records — they live in the cached prefix that Anthropic reports only as aggregate token counts. So tokenauditor shows two numbers:

- **Reported** — Anthropic `usage` per turn (authoritative).
- **Estimated** — a tiktoken count over the visible content blocks, labeled `(approx, tiktoken)`. Exact for OpenAI, approximate for Anthropic content.
- **Inferred prefix** — system+tools size = first turn's reported total minus the first user message's tokens, labeled `(inferred)`.

## Waste flags

- `HEAVY_TOOL_RESULT` — a tool result larger than all user turns combined.
- `CONTEXT_GROWTH` — reported context grows >2× from the first to last quarter of turns.
- `REPEAT_TOOL_CALL` — the same tool called 2+ times with identical input.

## Self-test

```bash
python selfcheck.py
```

## License

MIT
````

- [ ] **Step 2: Verify `pipx install .` works in a clean way (editable sanity check)**

Run: `python -m pip install -e . -q && tokenauditor --help | grep -q file && python -m pip uninstall -y tokenauditor -q`
Expected: command succeeds (prints nothing on success beyond the grep match).

- [ ] **Step 3: Add a `.gitignore`**

Create `.gitignore`:
```
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.venv/
tmp_transcript.json
```

- [ ] **Step 4: Commit**

```bash
git add README.md .gitignore
git commit -m "docs: README + gitignore"
```

- [ ] **Step 5: Add remote and push**

```bash
git remote add origin https://github.com/Victorchatter/Tokenauditor.git
git push -u origin main
```
If the remote already has an initial commit, instead: `git pull --rebase origin main && git push -u origin main`.

Expected: pushes `main` to `github.com/Victorchatter/Tokenauditor`.

---

## Self-Review (run after writing — already applied)

**Spec coverage:** every spec section maps to a task: two-count model → Tasks 2,3,4; categories → Tasks 3,4; per-turn view → Tasks 4,7; waste flags → Task 6; parsers → Tasks 3,4,5; provider detection → Task 5; counters → Task 2; CLI → Task 8; output tables/JSON → Task 7; selfcheck → Task 9; README/license/push → Task 10. MIT license → Tasks 1,10. Read-only → enforced in Tasks 3,4,8 and asserted in Task 9.

**Placeholder scan:** none — every step has complete code.

**Type consistency:** `Session`/`Turn` fields match across parsers (Tasks 3,4), flags (Task 6), report (Task 7), cli (Task 8), selfcheck (Task 9). `check(session) -> list[dict]` with `{flag, message, turn}` consistent throughout. `usage_total`, `count_text`, `count_json` signatures consistent. `main(argv=None) -> int` consistent in Tasks 1,8,9.