# LinuxBuddy — Current Status

> The single source of truth for where the project is NOW. Overwrite this
> after every task. Keep it short. Next session reads this first.

**Last updated:** 2026-11-03 (after Task 06 / P1.2)
**Current phase:** Phase 1 — Harden (complete; ready for Phase 2)
**Branch:** v1-file-discovery

---

## Done

- Scoping, taxonomy (`kb/taxonomy.yaml`, 9 domains), 360 validated scenarios
- Test maze (`testlinuxbuddy/`) — deterministic, bindings + runtime setup
- **file_discovery domain works end to end** — 4 intents, rule-based NLU,
  planner, renderer with injection-safety proven, `lb` CLI.
- **P1.1 (Task 05) — both known bugs fixed.** Abstention gate: a defining
  slot missing → abstain, never a match-everything command. Plural/possessive
  file-type words normalize to the extension. 39 tests pass.
- **P1.2 (Task 06) — 360 reference commands verified vs the maze.** Raw
  verdicts in `data/scenarios/verify_results.csv`:
  **244 PASS · 59 FAIL · 43 SKIP · 13 EMPTY · 1 UNSAFE**. Nothing fixed —
  verdicts only. See `LOG.md` for the FAIL root-cause breakdown.
- All project docs in place (ROADMAP, WBS, HANDOVER, MAZE, CLAUDE)

## In progress

- Nothing. Phase 1 (Harden) is done.

## Next (in order)

1. **Human decision on the 360 FAILs** (see below) before trusting the dataset
   as ground truth for Phase 2 NLU tests.
2. Then **Phase 2** — build the 8 remaining domains (see WBS).

## Open bugs

- None open in `file_discovery` (both P1.1 bugs fixed).
- **Dataset (not code):** 59 reference commands exit nonzero in the maze.
  Most are two systemic patterns — ~20 whole-tree `find`/`grep -R`/`du`/`tar`
  tripping the deliberate `perms/noaccess_dir`, and ~12 `grep`/`diff`/`cmp`
  exiting 1/2 "by design" (no match / differ). A handful are genuine
  reference/binding bugs (ARCH-001/022/023/031 tar targets, PY-003/018/024/
  036/039 running a .sh via python3, PROC-021 unquoted ppid, WORK-017/021
  mkdir of an existing dir). Full list + stderr in `verify_results.csv`.

## Decisions the human still needs to make

- For each FAIL class: fix the reference command, adjust the maze/binding, or
  accept nonzero exit as expected? (Task 06 was raw-verdicts-only by design.)

## Decisions the human still needs to make

- None open. (Release audience: owner + batchmates. Model: intent-only, Phase 3.
  All settled — see ROADMAP design rules.)

## Notes / watch-outs

- Only file_discovery is built. The other 8 domains do NOT exist yet.
- `lb` lives in a uv venv; destructive-intent gate not built until P2.0.
- Owner is on bash; only the zsh widget exists.
