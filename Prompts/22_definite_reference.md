# Task 22 — definite-reference resolution (the #1 fix)

Read `CLAUDE.md`. The eval's single biggest failure pattern (28 of 50) is this:
users say "the log", "the backup", "this file" — a definite reference, not a
filename — so the intent is recognised but the planner has no path and abstains.
Resolve typed definite references to a glob so a command is emitted.

## The fix

When an intent needs a file/path slot and the request uses a definite reference
that implies a FILE TYPE, fill the slot with a glob instead of abstaining:

| Reference in the request | Resolve to |
|---|---|
| "the log" / "the logs" | `*.log` |
| "the backup" / "the tarball" / "the archive" | `*.tar.gz` |
| "the gzip" / "the gz" | `*.gz` |
| "the zip" | `*.zip` |
| "the config" / "the config file" | `config.*` |
| "the csv" / "the csv file" | `*.csv` |
| "the script" | `*.sh` or `*.py` per domain (py for python_env, sh for workspace) |

The emitted command uses the glob, which the user's shell expands:
`show errors in the log` → `grep -niF -- error *.log`.

**Subdirectory caveat:** a bare `*.log` only matches the current directory. In
the maze, logs live in `logs/`. Choose ONE reasonable behavior and document it:
either (a) emit a recursive form for search intents (`grep -R`), or (b) accept
that the glob matches cwd and the user adjusts. Prefer whatever gives the user a
useful command most often. A command that finds nothing is still better than an
abstain — the user sees it and edits the path.

## What stays abstaining

Genuinely generic references with NO implied type — "this file", "the file",
"this list", "these names" (E037, E044-E047, E066, E075) — have no glob to
resolve to. For v1, either keep abstaining on these OR emit with a literal
`FILE` placeholder the user replaces (e.g. `sort -- FILE`). Pick one, document
it. (The typed references above are the high-value ~18; the generic ones are the
harder ~10.)

## Rows this must fix (verify each now emits a command)

file_inspection: E020, E022, E023, E026, E031
text_and_logs: E033, E034, E037, E039, E040, E044-E047
filesystem: E063, E066
archives: E079, E080, E081, E082, E083, E085, E086
python_env: E094, E096

## Tests

Add cases asserting typed definite references resolve to the glob:
- "show me the errors in the log" → `grep ... error *.log` (or recursive)
- "what's inside the backup tarball" → `tar -tf *.tar.gz` (or the resolved form)
- "how many warnings in the log" → `grep -c ... warning *.log`
- "who owns the config file" → `stat ... config.*`
Plus: a genuinely generic "sort this list" behaves per your documented choice.
Plus a full regression run.

## Done when

`pytest` passes (incl. regression). The listed rows emit commands instead of
abstaining. Re-running those requests through `lb` in the maze produces usable
commands. Document in LOG.md which references you resolved and the
subdirectory/generic-reference choices you made.
