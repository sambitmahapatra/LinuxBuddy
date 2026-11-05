# Task 14 — domain: python_environments

Read `CLAUDE.md` and the Tier 2 batch rules. Needs the gate (Task 12).
This domain is messy — be disciplined about what to build vs defer.

## Intents (grounded in the real scenarios)

### Read-only (work anywhere)

| Intent | Example | Command |
|---|---|---|
| `python_version` | "python version and where it lives" | `python3 --version && command -v python3` |
| `check_package` | "is pandas available", "does numpy import" | `python3 -c 'import importlib.util as u; print(u.find_spec("{pkg}") is not None)'` |
| `where_python` | "where does my python executable live" | `command -v python3` |

### Write (gated to maze)

| Intent | Example | Command | risk_ops |
|---|---|---|---|
| `run_script` | "run this script", "run the analysis" | `python3 -- {script}` | write |
| `check_syntax` | "check this script for syntax errors" | `python3 -m py_compile -- {script}` | write (makes .pyc) |

## Slots

`PATH` (script), package name (for check_package — a PATTERN-like token).

## Deferred — DO NOT build (document why)

- **venv create + pip install / upgrade / download** — need NETWORK. Skip.
- **venv activate / deactivate** (`source .../activate`, `deactivate`) — change
  SHELL STATE, can't run as a subprocess. A shell-function approach is possible
  but it's later work. Skip for now.
- **http.server** — long-running. Skip.
- **compileall / unittest discover over a dir, cd && run** — compound. Defer.
- Interactive `python3` REPL — not a command to emit. Skip.

Be strict: this domain's clean single-command intents are few (5). That's fine
— build those correctly and defer the rest with clear reasons. Do not try to
make venv-activate or pip work in V1.

## Build

- `kb/commands/` for python3 (argv-stage). Read intents `risk_ops: [read]`,
  run/compile `risk_ops: [write]`.
- Capability `python_env` in `kb/taxonomy.yaml`.
- Extend `nlu.py`: "python version" → python_version; "where is python" →
  where_python; "is X available / does X import" → check_package (pkg=X);
  "run this script / run X.py" → run_script; "check syntax / py_compile" →
  check_syntax.

## Tests (`tests/test_python_env.py`)

| input | expect |
|---|---|
| "what python version do i have" | python_version |
| "where does python live" | where_python |
| "is pandas available" | check_package, pkg=pandas |
| "run train.py" | run_script (write, gated) |
| "check main.py for syntax errors" | check_syntax (write, gated) |
| "install the requirements" | abstain (network, deferred) |
| "activate the venv" | abstain (shell state, deferred) |

## Done when

`pytest` passes (incl. regression). Against the maze:
`lb what python version do i have` runs;
`lb is numpy available` returns True/False;
`lb check src/main.py for syntax errors` runs (gated). Verify against Python
maze scenarios; note pass rate and the (many) deferred rows — this domain's low
single-command coverage is expected and correct.
