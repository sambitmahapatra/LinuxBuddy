# LinuxBuddy — Current Status

> The single source of truth for where the project is NOW. Overwrite this
> after every task. Keep it short. Next session reads this first.

**Last updated:** 2026-11-05 (after Task 07 / P1.2.2)
**Current phase:** Phase 1 — Harden (complete; ready for Phase 2)
**Branch:** v1-file-discovery

---

## Done

- Scoping, taxonomy (`kb/taxonomy.yaml`, 9 domains), 360 validated scenarios.
- Test maze (`testlinuxbuddy/`) — deterministic, bindings + runtime setup.
- **file_discovery domain works end to end** — 4 intents, rule-based NLU,
  planner, injection-safe renderer, `lb` CLI. Both known bugs fixed (P1.1).
- **P1.2 (Task 06) — 360 reference commands verified vs the maze.** Raw
  verdicts only: 244 PASS · 59 FAIL · 43 SKIP · 13 EMPTY · 1 UNSAFE.
- **P1.2.2 (Task 07) — the 360 verdicts triaged.** `verify_results.csv` now
  has `verdict_final` + `verdict_final_reason` on every row.
  **True pass (PASS + PASS_WITH_STDERR) = 296/360 (82.2%).** Final tally:
  PASS 275 · PASS_WITH_STDERR 21 · PASS_IN_SEQUENCE 1 · ACCEPTED_EMPTY 13 ·
  ENV_UNSUPPORTED 3 · SKIP 43 · UNSAFE 1 · **FAIL 3**. 14 genuine dataset bugs
  fixed in the CSV and re-verified; 35 false failures reclassified; 13 EMPTY
  accepted with reasons. See `LOG.md` for the full breakdown.

## In progress

- Nothing. Phase 1 (Harden) is done and the dataset is now trustworthy ground
  truth for Phase 2 NLU tests (modulo the 3 open rows below).

## Next (in order)

1. (Optional) Resolve the **3 genuine remaining FAILs** (dangling
   `$TARGET_FILE`) and decide whether to make the 13 ACCEPTED_EMPTY scenarios
   literal via small `build_maze.sh` additions — see below.
2. Then **Phase 2** — build the 8 remaining domains (see WBS).

## Open bugs / dataset issues

- **3 genuine dataset defects remain** (same root cause): INS-007, FS-022,
  FS-040 all read `$TARGET_FILE` (`output/target.txt`), which **no scenario row
  creates** and the maze omits. Fix = rebind `TARGET_FILE` to an existing file,
  or create it (+ a producer) in `build_maze.sh`. Not fixed in Task 07 (it's a
  binding/fixture decision, not a command edit).
- No open bugs in `file_discovery` code.

## Decisions the human still needs to make

1. **`2>/dev/null` on generated find/grep/du/tar?** Should LinuxBuddy's
   *generated* recursive commands suppress permission-denied stderr (the cause
   of all 21 PASS_WITH_STDERR rows)? Trade-off and context in `LOG.md`
   (Task 07, Step 4). **Left open.**
2. **The 3 dangling-`TARGET_FILE` rows** — rebind or add fixture? (above)
3. **13 ACCEPTED_EMPTY scenarios** — leave accepted, or add small maze content
   (`.pt` checkpoints, a "deprecated"/METRICS block in train.log, `train_*`
   files, archives in `backups/`) to make them return real output? Each is a
   one-line `build_maze.sh` change; none is a command bug.

## Notes / watch-outs

- **ARCH-024 changed risk read-only → writes** in Task 07 (now does a `cp`
  before verifying) — it falls under the Phase-2 destructive-location gate.
- **Task 07 fixes are CSV-only; the maze (`build_maze.sh`) was NOT changed**,
  to keep the fixture stable. PY-003/018/024/036/037 + WORK-039 were repointed
  from `good_script.sh` to `scripts/train_stub.py` (`$TRAIN_SCRIPT`).
- Only `file_discovery` is built. The other 8 domains do NOT exist yet.
- `lb` lives in a uv venv; destructive-intent gate not built until P2.0.
- Owner is on bash; only the zsh widget exists.
- Verification host gaps (not dataset bugs): no `pandas`, no `python3-venv`,
  WSL kernel has no `/proc/<pid>/io` → 3 ENV_UNSUPPORTED rows.
