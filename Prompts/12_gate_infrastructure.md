# Task 12 (P2.0) — destructive-containment gate

Read `CLAUDE.md` and `ROADMAP.md` design rules. This is infrastructure, not a
domain — build it before any write/destructive intent exists.

## What it does

In **prototype mode** (the default), LinuxBuddy refuses to emit a command that
writes, deletes, or changes permissions unless the current working directory is
under the **maze root**. Read-only intents work anywhere. In **prod mode**, the
gate is off. This is the "safety by containment" rule: destructive commands
only run where damage is disposable.

## Build

### Mode + root config
- `LINUXBUDDY_MODE` env var: `prototype` (default) | `prod`. Read it in one
  place (e.g. `src/linuxbuddy/config.py`).
- `LINUXBUDDY_MAZE_ROOT` env var: the containment root. Default to
  `~/linuxbuddy/testlinuxbuddy` (expanded). This is where destructive commands
  are allowed in prototype mode.

### The gate
- `src/linuxbuddy/gate.py`: `check(plan, cwd) -> None | AbstainReason`.
- A plan's risk is `risk_ops` from the KB (already present on intents). A plan
  is "destructive" if its risk_ops include any of `write`, `delete`,
  `privilege`.
- Logic:
  - mode == prod → always allow.
  - mode == prototype, plan read-only → allow.
  - mode == prototype, plan destructive, cwd resolved-absolute is under
    MAZE_ROOT → allow.
  - mode == prototype, plan destructive, cwd NOT under MAZE_ROOT → ABSTAIN
    with a clear message: `LinuxBuddy (prototype): destructive commands only
    run inside the test maze. cd into <MAZE_ROOT> first.`
- Resolve cwd and MAZE_ROOT to real absolute paths (resolve symlinks) before
  the under-root check, so `..` or a symlink can't slip the gate.

### Wire it
- In `cli.py`, after the planner compiles and before rendering/printing, call
  `gate.check(plan, os.getcwd())`. On abstain, print the message to stderr,
  exit 1, print nothing to stdout.

## Tests (`tests/test_gate.py`)

- prototype + a write plan + cwd outside maze → abstain.
- prototype + a write plan + cwd inside maze → allowed.
- prototype + a read plan + cwd anywhere → allowed.
- prod + a write plan + cwd anywhere → allowed.
- cwd given as `MAZE_ROOT/../outside` (path traversal) → treated as outside,
  abstain. (This test matters — prove the resolve step works.)

## Done when

`pytest tests/test_gate.py` passes incl. the traversal test, all prior tests
green, and manually: a (future) destructive `lb` command abstains outside the
maze and works inside it. Since no destructive intent exists yet, test the gate
with a stub/fake write plan.
