# Task 07 (P1.2.2) — triage the 360 verdicts

Read `CLAUDE.md`, `STATUS.md`, and the last `LOG.md` entries first.

Context: `data/scenarios/verify_results.csv` has raw verdicts from Task 06.
The 59 FAILs are mostly verification-method artifacts, NOT dataset bugs. This
task separates real bugs from false failures. Do NOT just re-run — reclassify,
then fix only the genuine bugs.

## Step 1 — reclassify false failures (in place)

Post-process `verify_results.csv`. Add a `verdict_final` column:

- **noaccess_dir artifact → PASS_WITH_STDERR.** Any FAIL whose stderr is only
  "Permission denied" on `perms/noaccess_dir` (or similar) while stdout is
  non-empty and correct. The command is right; it just hit the maze's
  deliberately-unreadable dir. (~20 rows: FIND-003/006/012/013/016/019/021/024/030/037/040,
  ARCH-021/029/039, FS-024/029/034/035, TEXT-025, WORK-040.)
- **grep/diff no-match → PASS.** Any grep/diff/cmp/comm with empty stderr and
  exit 1 — that's "no match / differs", correct behaviour, not failure.
  (~15 rows: TEXT-009/011/012/017/032/034, INS-023/024, ARCH-032/034,
  WORK-026, PROC-017/029, FS-037, PY-038.)

Verify each against its actual stderr before reclassifying — do not trust the
list blindly.

## Step 2 — fix the genuine dataset bugs (in the CSV)

These are real reference-command errors. Fix the `reference_shell_plan`, then
re-verify just those rows against the maze:

- **ARCH-001** — `-C $PARENT_DIR -- $PROJECT_NAME` produces `project/project`;
  fix the path.
- **PY-003/018/024/036/039** — running `good_script.sh` via `python3` →
  SyntaxError. It's a bash script; the reference command uses the wrong
  interpreter. Fix to `bash` / `./script.sh`.
- **PROC-021** — unquoted ppid → "improper list"; quote it.
- **WORK-017/021** — `mkdir` of an existing dir fails; add `-p` or target a
  fresh name.
- **ARCH-022/023/024/031** — reference a missing archive member / subdir
  (checkpoints, results). Either create the fixture in build_maze.sh or fix
  the command's target.

## Step 3 — decide the EMPTY rows (13)

Mostly maze content gaps (no .parquet, no .pt, no "deprecated" string) — the
commands are fine. For each: either add the content to build_maze.sh, or mark
it `ACCEPTED_EMPTY` with a one-line reason. `history`/`jobs -l` empty in a
non-interactive shell is expected — accept those.

## Step 4 — the one product decision (record, don't act)

Note in LOG.md for the human to decide later: should LinuxBuddy's generated
`find`/`grep -R` commands append `2>/dev/null` to suppress permission-denied
noise on unreadable dirs? Most hand-written finds don't. Leave it open.

## Done when

- `verify_results.csv` has a `verdict_final` column; the false-failure count
  is reclassified and the true pass rate is reported.
- The ~13 genuine bugs are fixed and re-verified PASS.
- EMPTY rows are each resolved or accepted with a reason.
- LOG.md and STATUS.md updated; committed. Do not push.

Report the true pass rate (PASS + PASS_WITH_STDERR) vs genuine remaining
failures, per domain.
