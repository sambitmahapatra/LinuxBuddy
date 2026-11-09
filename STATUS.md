# STATUS — LinuxBuddy

**Last updated:** 2026-11-08 (BATCH 25-27 COMPLETE: Tasks 25, 26, 27 all done)

## Where we are
V1 is feature-complete and **usable**: all 9 domains built (plus navigation now
a first-class 10th parser), the asymmetric abstain policy in force,
definite-reference resolution landed, and the shell widgets (bash + zsh) inject
commands with tiered risk confirm. **266 tests pass.**

The systematic sweep is the current quality bar: **COMMAND 132 / ABSTAIN 7**
out of 139 (up from 93/46), ~129/139 fully-right, **0 regressions**, integrity
PASS. See `data/eval/sweep_results_v2.csv`.

## Done (BATCH 25-27)
- **Task 25** routing priority — a specific intent beats `find`; fixed view/
  count/copy/history/process/perm rows + size-sign + recursive-grep bugs.
- **Task 26** navigation built as a first-class domain parser (cd_parent/home/
  previous/ancestor/child/absolute/pwd, cwd-aware). Killed the `cd -- *.log`
  glob leak, the stray `cd -` on "go up", and the `/mnt/c/Users` truncation.
- **Task 27** intent & synonym fill across six domains — env_var, disk_free,
  which/pip, pip_list, package-vs-CLI, extract, create synonyms, wsl
  (win_path/vscode/win_folders), chmod lock-down, find_perms, find_empty,
  find_recent (-mmin), count_files, recursive-grep cwd-synonyms. Also fixed two
  VIEW-preview regressions (E027 listing, E126 zip) found in the re-sweep.
- **Re-sweep** → `data/eval/sweep_results_v2.csv` (COMMAND 93→132, ABSTAIN
  46→7, 0 regressions vs v1, 39 newly fixed, integrity PASS).

## Open / next
- **Manual widget check in a REAL interactive bash** (verified non-interactively;
  a human should source it and press Ctrl-G to confirm Readline redraw).
- **4 near-miss abstains NOT in the batch's row list** (follow-up synonym
  patches, one-task-per-session): E048 "print the readme" (→ `cat README*`),
  E056 "tail the output" (vague target), E060 "what is this file" (→ `file FILE`),
  E066 "which lines mention warning" (no file named → would need a *.log guess).
- **1 pre-existing miss flagged:** E086 "what commands did i run recently" →
  `find -mtime -7` instead of `history` ("recently" routes to find before
  workspace). Not a Task-27 row.
- **Correct-by-design "abstains"/choices:** E073 "sort this list" (genuinely
  vague, no file) and E138/E139 pip-install (runtime network = invariant #1, so
  the scenario's `pip install` expected_shape is the thing that's wrong, not us).
  E110 "stop whatever's on port 8000" shows the port's process (safe) rather than
  auto-killing an unclear target.
- Phase 3 (intent-only model) not started. The ~5 generic-reference residuals
  ("sort this list", "what is this file") remain its motivation.

## Open bugs
None known. Full suite green (266). Sweep: 0 regressions, integrity PASS.
