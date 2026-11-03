# LinuxBuddy — working agreement

Read `kb/taxonomy.yaml` before any task. The V1 thin slice is the
**file_discovery** domain only — do not build other domains yet.

## Invariants — never violate these

- No LLM, no network, no generative model at runtime. Pure Python + stdlib
  (plus pytest for tests). If a task seems to need a model, stop and ask.
- Command plans are typed **argv lists**. The shell string is RENDERED from
  the argv for display only — it is never the execution source.
- A slot value substitutes into exactly ONE argv element, never into a
  joined command string.
- Nothing auto-executes. LinuxBuddy prints a command for the user to put in
  their shell buffer and run themselves.
- Target platform is Ubuntu on WSL2. Assume systemd is NOT running.
- Paths in the final argv are absolute. Resolve `$HOME` / `~` at compile
  time; never emit `~` or `$HOME` and rely on the shell to expand it.

## Process

- Write the failing test FIRST, then the implementation.
- One task file per session. Do the task named, nothing beyond it.
- If a task's "Done when" criterion is ambiguous, stop and ask rather than
  guessing.
- Package layout: code under `src/linuxbuddy/`, tests under `tests/`.
  Assume `pip install -e .` and `pytest` both work.

## The test fixture

`testlinuxbuddy/` is a generated maze of files for behavioural testing.
Rebuild with `./testlinuxbuddy/build_maze.sh`, source
`testlinuxbuddy/bindings.env` for path variables. Never let a test write or
delete anything outside `testlinuxbuddy/`.
