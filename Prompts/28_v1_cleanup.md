# Task 28 — v1 cleanup (the last real residual) + re-sweep

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Driven by named rows in
`data/eval/sweep_results_v3.csv`. This is the final rules-v1 pass — four fixes,
then a confirming re-sweep. After this, v1 is declared.

## The four fixes

1. **E086 — history request hijacked by `find_recent` (the one misleading row).**
   "what commands did i run recently" emits `find . -type f -mtime -7`. The word
   "recently" is pulling a *command-history* request into file discovery.
   Add/repair a **history** intent: "what commands did i run", "command
   history", "recent commands", "my recent commands", "what have i run" →
   `history`. It must **beat `find_recent`** when the request is about
   *commands* (cue words: "command(s)", "did i run", "i ran") even if
   "recent/recently" is present. Don't broaden `find_recent`; add history with
   higher precedence for the command-cue.

2. **E048 — "print the readme" abstains.** Add `readme` to the definite-
   reference resolver: "the readme" / "readme" → `README*`. So "print the
   readme" / "show the readme" → `cat -- README*` (or the head-preview form you
   use for other definite file refs). Keep it consistent with the existing
   definite-ref table (Task 22).

3. **E066 — "which lines mention warning" abstains.** A "which lines
   mention X" / "lines with X" / "lines mentioning X" request is a grep. When no
   file is named, default to a **recursive grep in cwd**, consistent with the
   existing no-target grep behavior (E070/E071):
   `grep -rn -- warning .`  (not an abstain).

4. **E117/E118 — Windows path uses `$USER`, which is wrong on WSL.** The Linux
   `$USER` is almost never the Windows username, so
   `cd /mnt/c/Users/$USER/Downloads` points at a path that usually doesn't
   exist. Replace with a **glob** the shell expands to the real Windows user
   dir: `cd -- /mnt/c/Users/*/Downloads` (and `.../Documents`). Document the
   choice (glob over `$USER`) in LOG.md.

## Re-sweep (confirm, don't regress)

Re-run `Prompts/24_full_sweep.md` on the same 139 scenarios → write
`data/eval/sweep_results_v4.csv` (leave v1/v2/v3 intact). Same guards. Print the
tally and **diff the routing columns against v3** — the ONLY rows whose
`lb_stdout`/`outcome` may change are E048, E066, E086, E117, E118. If any other
row's routing changed, that's a regression — STOP and report it.

Expected: COMMAND 132 → ~134 (E048 + E066 flip abstain→command; E086 flips
wrong-command→correct; E117/E118 improve in place). Remaining abstains should be
the honest 5: E056, E060, E073, E138, E139.

## Tests & done

A test per fixed row (E086→history, E048→README* preview, E066→recursive grep,
E117/E118→glob path). Full regression — history must not steal file-discovery
rows (E036–E039 stay `find`); the readme/grep defaults must not break other
definite-ref or grep rows. `pytest` green. Commit, don't push. Document in
LOG.md, and update STATUS.md to note the residual is now the honest-5 abstains.
