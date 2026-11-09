# LinuxBuddy

**LinuxBuddy translates plain-English requests into Linux shell commands and
places them in your shell buffer — for you to read, edit, and run.** It never
runs anything on its own.

It is **fully offline**: no LLM, no network call, no API key at runtime. The
language understanding is classical, rule-based NLU — hand-written intent/slot
rules plus a typed-command knowledge base. (The only AI involvement was in
authoring those rules.) What you type is parsed and compiled locally, in
milliseconds, with nothing leaving your machine.

## Who it's for

Someone skilled who was handed Linux as a *tool*, not a subject to study — for
example a data scientist or ML engineer working in WSL2, expert in their field
but new to the terminal and without the time to learn it as a discipline.

It inverts the usual docs index. Instead of knowing the command's name to look
it up, you say what you want — *"find the biggest files in downloads"*, *"which
lines mention warning"*, *"what's my PATH"* — and LinuxBuddy produces the
command.

## How it works

```
request → intent + slot parse → typed argv plan → rendered shell command → your shell buffer
```

The **plan is a typed argv list**, never a string: one slot value becomes
exactly one argv element, so a filename with a space or a glob can never split
or be re-interpreted. The shell string you see is *rendered* from that plan for
display only, and is checked with a `shlex` round-trip so what's shown parses
back to the exact argv that was planned.

## Install

LinuxBuddy is a pure-stdlib Python package (3.10+) with a `lb` console script.

```bash
# from the repo root, into your environment (a venv is recommended):
pip install -e .
```

Make `lb` available on your `PATH` — either via the editable install above, or
by symlinking the venv's script:

```bash
ln -s "$PWD/.venv/bin/lb" ~/.local/bin/lb   # ~/.local/bin must be on PATH
```

Then source the shell widget from your shell rc so you get the keybinding:

```bash
# ~/.bashrc
source /path/to/linuxbuddy/shell/linuxbuddy.bash
# ~/.zshrc
source /path/to/linuxbuddy/shell/linuxbuddy.zsh
```

## Usage

Type a request on your command line, then press **Ctrl-G**. The line is
**replaced** by the suggested command — editable, cursor ready, **not run**.
Read it, change it if you like, and press **Enter** to run it. Nothing executes
without that keystroke.

You can also call it directly: `lb "find logs over 100mb"` prints the command.

**Tiered confirmation, signaled by exit code:**

| Request | Behavior | Exit code |
|---------|----------|-----------|
| Read-only (`find`, `grep`, `ls`, …) | command appears silently | `0` |
| Vague / no operation named | abstains with a short hint, no command | `1` |
| Destructive (write / delete / chmod / kill) | command appears with a warning | `3` |

The abstain is **asymmetric by risk**: a read-only request with any reasonable
interpretation gets a command (a wrong `grep` is cheap and editable), but a
destructive request that isn't a confident parse refuses — a wrong `rm` or
`chmod` is not.

## Safety model — containment

v1 is validated inside a disposable test **maze**, and the safety guarantee is
*containment*. In the default **prototype** mode, any destructive operation
(write / delete / permission change) is **refused unless the current directory
is under the maze root**. Read-only intents work anywhere.

Two environment variables control this:

- `LINUXBUDDY_MODE` — `prototype` (default) or `prod` (lifts the gate).
- `LINUXBUDDY_MAZE_ROOT` — the directory under which destructive commands are
  allowed in prototype mode.

There is **one rendering path**: LinuxBuddy always renders the genuine command
(`rm`, `chmod`, `find -delete`) — there is no "safe-rewrite" mode that would
show you something other than what runs. Safety comes from the gate and from the
fact that you press Enter, not from disguising the command.

## Coverage — 10 domains

Navigation · File discovery · File inspection · Text & logs · Workspace & shell ·
Filesystem permissions · Processes · WSL interop · Archives & backup ·
Python environments.

## Evidence

Correctness is held to a **deterministic 139-scenario sweep** that routes every
request against a fixed-timestamp test maze and (for safe commands) executes the
result. In the latest run, **134 of 139** either emit the right command or
honestly abstain, with **0 regressions** and the maze snapshot verified intact
before and after. The full per-row output is committed at
[`data/eval/sweep_results_v4.csv`](data/eval/sweep_results_v4.csv), and the test
suite (**281 tests**) passes. Because the maze has fixed timestamps and sizes,
the whole evaluation is reproducible.

## Known limits — and what's next

v1 is **rules-only, by design.** The honest residual is a small set of requests
that carry no resolvable target or operation: generic references (*"what is this
file"*, *"tail the output"*), genuinely ambiguous asks (*"sort this list"*), and
requests that would require runtime network access (*"install the requests
package"* — excluded on purpose, since nothing reaches the network at runtime).
On these, LinuxBuddy abstains rather than guess.

Those context-dependent cases are exactly the motivation for **v2**: an
attention/transformer layer for intent understanding, learned context, and a
feedback loop — a direction, not a runtime dependency of what's here. v1 stands
on its own as a complete, offline, deterministic tool.
