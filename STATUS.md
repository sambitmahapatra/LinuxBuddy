# STATUS — LinuxBuddy

**Last updated:** 2026-11-08 (BATCH 25-27: Tasks 25-26 done; next 27 synonym fill)

## Where we are
V1 is feature-complete and **usable**: all 9 domains built, the asymmetric
abstain policy in force, definite-reference resolution landed, the eval cleanup
done, and the shell widgets (bash + zsh) inject commands into the buffer with
tiered risk confirm. **190 tests pass.**

## Done (this batch)
- **Task 19** find_largest (biggest/top-N files).
- **Task 20** asymmetric abstain policy (help on reads, caution on destructive);
  find_smallest; "open X" abstains cleanly. CLAUDE.md invariant #6 rewritten.
- **Task 22** definite-reference → glob (render.Raw emits globs UNQUOTED so the
  shell expands them). "the log"→*.log, "the backup"→*.tar.gz, etc.
- **Task 23** eval cleanup: wrong-routes (E004/E024/E090/E016/E018), defaults
  (E056/E058 → ss -ltnp), synonyms (stop/terminate, check-if-installed, room,
  zip up, chmod intent-words).
- **Re-sweep** → data/eval/eval_results_v2.csv. COMMAND 66→94, ABSTAIN 64→36.
  Wrong-abstains where a clear command existed: ~45 → ~9.
- **Task 18** bash widget (`bind -x`, Ctrl-G) + zsh parity + lb exit-code risk
  signaling (0 read / 3 destructive / 1 abstain).

## Systematic sweep (Task 24)
`data/eval/sweep_results.csv` — 139 scenarios routed + (safe ones) executed in
the maze. Integrity PASS (canonical maze unchanged). COMMAND 93 / ABSTAIN 46;
read-row exec ok 42 / nonzero 36. **Top finding surfaced for review:** "take me
to the logs folder" emits `cd -- *.log` (Task-22 definite-glob leaks into the
`goto` target — should be `cd logs`). Full findings in LOG.md. Capture only.

## Open / next
- **Fix the `cd -- *.log` goto leak** surfaced by the sweep (navigation `goto`
  should not pull the definite-reference glob; use the folder name).
- **Manual widget check in a REAL interactive bash** (I verified the function
  non-interactively; a human should source it in an interactive shell and press
  Ctrl-G to confirm Readline redraw feels right).
- **~9 near-miss abstains** (documented in LOG under the re-sweep entry): e.g.
  "tail the app log", "extract the backup" (default dir), "execute the analysis
  script" (execute synonym), windows-bridge phrasings. Candidate v1 synonym
  patches — left as follow-ups (one-task-per-session).
- **~14 generic-reference abstains** ("this file", "sort this list") are the
  intentional v1 residual → the motivation for the Phase-3 intent model.
- Phase 3 (intent-only model) not started.

## Open bugs
None known. Full suite green (190).
