# Task 16 — domain: workspace_and_shell (scoped multi-step)

Read `CLAUDE.md` and the Tier 3 batch rules. This domain introduces
**scoped multi-step** — named fixed recipes, NOT arbitrary compound
decomposition. `cd`/`export` are fine (buffer injection; the user's shell runs
them).

## Single-command intents

### Read-only (work anywhere)

| Intent | Example | Command |
|---|---|---|
| `where_am_i` | "where am I", "what folder am I in" | `pwd` |
| `go_home` | "take me home", "back to my home folder" | `cd ~` |
| `go_back` | "go back to the folder I was in" | `cd -` |
| `goto` | "take me into the project folder", "go to src" | `cd -- {path}` |
| `list_all` | "show all files including hidden" | `ls -la` |
| `who_am_i` | "what account am I using" | `whoami && id -nG` (2-stage &&) |
| `which_shell` | "which shell is this" | `printf "%s\n" "$SHELL"` |
| `show_history` | "show the commands I used earlier" | `history` |
| `clear_screen` | "clear the screen" | `clear` |
| `check_installed` | "do I have git", "is docker installed" | `command -v -- {tool}` |

### Write (gated to maze)

| Intent | Example | Command | risk_ops |
|---|---|---|---|
| `make_dir` | "create an outputs folder", "make a data dir even if parent is missing" | `mkdir -p -- {path}` | write |

## Scoped multi-step recipe (the new capability)

| Intent | Example | Command | risk_ops |
|---|---|---|---|
| `setup_project` | "set up a project folder called X", "create a workspace with data and reports folders" | `mkdir -p -- {name}/data {name}/reports && cd -- {name}` | write |

Build `setup_project` as ONE named recipe that emits a fixed multi-command
sequence (using the existing `&&` Stages composition). Do NOT try to parse
arbitrary "do A, then B, then C" requests — that's generalized compound
support, which is V1.1. If the request doesn't match the known recipe shape
(a project/workspace setup), abstain.

The folders in the recipe can be fixed (data, reports) for V1, or extracted if
the request names them explicitly ("with data and models folders"). Keep it
simple — fixed defaults are fine; document the choice.

## Slots

`PATH` (goto, make_dir), `name` (setup_project — the project dir), `tool`
(check_installed).

## Deferred (abstain)

- `export VAR=... && cd && pwd` (env + navigate compound), `mkdir && touch &&
  date >> file` (experiment diary — 3-step with redirect), compound
  "diagnose my PATH and confirm python" → defer (compound/multi-intent).
- Arbitrary "do X then Y" → abstain (generalized compound is V1.1).

## Build

- `kb/commands/` for pwd, cd, ls, whoami, mkdir, command, history, clear
  (reads `risk_ops: [read]`, mkdir/setup `[write]`).
- Capability `workspace` in `kb/taxonomy.yaml`.
- Extend `nlu.py` with a workspace parser. Place it carefully in router order
  so navigation verbs ("go to", "take me") win appropriately.

## Tests (`tests/test_workspace.py`)

| input | expect |
|---|---|
| "where am I" | where_am_i |
| "take me home" | go_home |
| "go to the src folder" | goto, path=src |
| "do I have git installed" | check_installed, tool=git |
| "make an outputs folder" | make_dir (write, gated) |
| "set up a project folder called demo" | setup_project, name=demo (write, gated, multi-step) |
| "export the path then cd and show me python" | abstain (compound) |

## Done when

`pytest` passes (incl. regression). Inside the maze:
`lb where am I` → `pwd`; `lb do I have git installed` → `command -v -- git`;
`lb set up a project folder called demo` → the mkdir+cd recipe (gated — abstains
from outside the maze). Note: workspace is a complete domain; multi-step is
scoped to the named recipe.
