# Task 04 — the `lb` command and the zsh widget

Read `kb/taxonomy.yaml`. Follow all invariants in `CLAUDE.md`.
This wires the pipeline together and puts a command in the user's buffer.

## Build

### `src/linuxbuddy/cli.py`

`main()`:
- Join `sys.argv[1:]` into the request string.
- Run `nlu.parse` -> `planner.compile` -> `render.to_shell`.
- On success: print the command to stdout and exit 0.
- On abstain (`parse` returns None) or `PlanError`: print a short message to
  stderr (`"LinuxBuddy: not sure what you mean"`) and exit 1. Print nothing
  to stdout, so a caller can trust stdout = a runnable command.

Add a `console_scripts` entry point `lb = linuxbuddy.cli:main` in
`pyproject.toml`.

### `tests/test_cli.py`

- `lb csv files over 100 megs` (invoked in-process) prints the find command
  and exits 0.
- `lb clean up my mess` prints nothing to stdout and exits 1.

### `shell/linuxbuddy.zsh`

A ZLE widget:
- Bound to a key (suggest `^g`, Ctrl-G).
- Takes the current buffer text as the request, calls `lb` with it.
- On exit 0: REPLACE the buffer with the returned command (do not run it;
  leave the cursor at the end so the user edits or presses Enter).
- On exit 1: leave the buffer unchanged and print the stderr message below
  the prompt.

Include install instructions as a comment: `source` it from `.zshrc`.

## Behavioural check (run manually, not a unit test)

After `pip install -e .` and sourcing the widget:
1. Rebuild the maze, `source testlinuxbuddy/bindings.env`.
2. `cd` into `testlinuxbuddy/project`.
3. Type `csv files over 100 megs`, press Ctrl-G. The buffer should become a
   `find` command. Press Enter. It should list the big CSV.
4. Confirm `cd ..` still works afterwards (proves the widget didn't fork a
   subshell and strand you).

## Done when

`pytest tests/test_cli.py` passes, and the four manual steps work in a real
zsh session. Report what the buffer showed at step 3.
