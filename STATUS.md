# STATUS — LinuxBuddy

**Last updated:** 2026-11-09 (Task 28 COMPLETE — rules-v1 declared)

## Where we are
**Rules-v1 is declared.** All 9 domains built (plus navigation as a first-class
10th parser), the asymmetric abstain policy in force, definite-reference
resolution landed, and the shell widgets (bash + zsh) inject commands with
tiered risk confirm. **281 tests pass.**

The systematic sweep is the quality bar: **COMMAND 134 / ABSTAIN 5** out of 139
(from 93/46 at Task 24), integrity PASS, **0 regressions**. See
`data/eval/sweep_results_v4.csv` (v1/v2/v3 kept for history).

## Done (Task 28 — the last real residual)
Four surgical fixes + a confirming re-sweep, test-per-row first:
- **E086** command-history no longer hijacked by `find_recent` — "what commands
  did i run recently" → `history` (broadened the workspace history intent to win
  on the command cue even with "recently"; did not touch `find_recent`).
- **E048** "print/show the readme" → `head -n 10 -- README*` (added `readme` to
  the definite-ref table).
- **E066** "which lines mention warning" → `grep -RniF -- warning .` (no file
  named → recursive grep in cwd, like E070/E071), instead of a pathless abstain.
- **E117/E118** Windows user folder → `cd -- /mnt/c/Users/*/Downloads` — a GLOB,
  not `$USER` (the Linux `$USER` is rarely the Windows account name).
- **Re-sweep** → `sweep_results_v4.csv`: routing diff vs v3 shows exactly those 5
  rows changed; every other row byte-identical. COMMAND 132→134, ABSTAIN 7→5.

## Residual — the honest 5 abstains
- **E056** "tail the output" / **E060** "what is this file" — generic target, no
  file named; a read with no resolvable reference → abstain (invariant #6).
- **E073** "sort this list" — genuinely vague, no file.
- **E138/E139** "install the requests package" / "add pandas to my environment" —
  **correct abstains**: runtime network is invariant #1. The scenario's
  `pip install` expected_shape is what's wrong, not LinuxBuddy.
These generic-reference residuals are the documented motivation for Phase 3.

## Open / next
- **Manual widget check in a REAL interactive bash** (verified non-interactively;
  a human should source it and press Ctrl-G to confirm Readline redraw).
- **Phase 3 (intent-only model)** not started. Slot extraction stays rule-based;
  the ~5 generic-reference residuals above are its motivation.
- `Prompts/29_v1_release.md` is staged (untracked) — the v1 release task.

## Open bugs
None known. Full suite green (281). Sweep: 0 regressions, integrity PASS.
