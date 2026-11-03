# Task 03 — planner, renderer, and the security boundary

Read `kb/taxonomy.yaml`. Follow all invariants in `CLAUDE.md`.
This task contains the security boundary of the whole system. Treat the
renderer tests as the most important tests in the project.

## Build

### `src/linuxbuddy/planner.py`

`compile(frame) -> list[str]`  (an argv list)

- Look up the capability and intent via `linuxbuddy.kb`.
- Start from `base_argv`, append the `optional_args` fragments for each slot
  present in the frame, substituting slot values into their single element.
- Resolve `$HOME` and leading `~` to `os.environ["HOME"]` HERE, so the final
  argv holds absolute paths. Never emit `~` or `$HOME`.
- If any `{placeholder}` remains unresolved in the output, raise
  `PlanError`. A placeholder must never reach the rendered string.

### `src/linuxbuddy/render.py`

`to_shell(argv: list[str]) -> str`

- `shlex.quote` every element, join with spaces.
- THEN assert `shlex.split(result) == argv`. If it does not match, raise
  `RenderError` — never return a string that fails the round trip.

### `tests/test_render.py` — WRITE THIS FIRST

- A frame whose `path` slot is `"my file; rm -rf ~.txt"` must:
  - compile without the `;` becoming a separate argv element, and
  - render so that `shlex.split(rendered)` recovers
    `"my file; rm -rf ~.txt"` as ONE intact element.
- Same for names containing a space, a single quote, `$(whoami)`, and a
  leading `-`.

### `tests/test_planner.py`

- The frame for `"csv files over 100 megs"` compiles+renders to exactly:
  `find . -type f -name '*.csv' -size +104857600c`
- A frame with an unresolved placeholder raises `PlanError`.

## Done when

`pytest tests/test_render.py tests/test_planner.py` passes, and the
`; rm -rf ~` case is proven inert by a test you can point to.
