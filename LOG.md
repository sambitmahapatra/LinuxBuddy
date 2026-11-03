# LinuxBuddy — build log

> Append-only history. Newest entries at the bottom of each day. Prose a
> person reads later, not a command transcript. `STATUS.md` holds the current
> snapshot; this holds how we got there and why.

---

## 2026-11-03 13:23 — Task 05 (P1.1): fix two bugs found by real use

**What I did.** Fixed the two known bugs in the `file_discovery` NLU, TDD
(tests first, then implementation).

*Bug 1 — silent slot dropping.* `lb show me the biggest files here` was
emitting `find . -type f` (matches everything): "biggest" is a size cue with
no numeric threshold, and the old code emitted `find_by_size` anyway, just
without a `size_bytes` slot. Added the abstention gate in `nlu.parse`: a size
cue with no number now returns `None` (abstain) instead of a thresholdless
frame. Added `nlu.abstain_hint`, which the CLI calls when `parse` returns
`None` to print a specific hint — `LinuxBuddy: how big? try "over 100MB"` —
rather than the generic "not sure what you mean". Also added a symmetric age
superlative cue (oldest/newest/latest/recent) → `how recent? try "in the
last 7 days"`, since the task groups those superlatives with the size ones.

*Bug 2 — plural extensions dropped.* `lb csvs bigger than 2 gigs` omitted
`-name '*.csv'`. Added a small explicit `_PLURAL_EXT` map (csvs→csv, logs→log,
pys→py, jsons→json, notebooks→ipynb, scripts→sh) plus a single trailing-s
fallback in `_normalize_ext` (so tsvs→tsv, pdfs→pdf come for free). "images"
is deliberately left out — ambiguous — and does not map. Not a stemmer, as the
task required.

**Decision the human should review.** Task 05's new rule ("`find_by_size`
with no `size_bytes` → abstain") and its required `"largest files" → None`
case directly reverse the *old* `test_vague_big_in_downloads` test, which
asserted that `"big files in downloads"` resolved to a thresholdless
`find_by_size`. "big" with no number is the same slot-dropping class as
"biggest", and CLAUDE.md invariant #6 (abstain over guess) backs the new
behavior, so I updated that test to assert `None` (renamed
`test_vague_big_in_downloads_now_abstains`) and reversed the stale
"vague-big resolution" rationale in the `nlu.py` module docstring. Flagging
it because it is a deliberate behavior change to a previously-passing test,
not just an addition.

**Tests.** Added to `tests/test_nlu.py`: biggest→None, largest→None,
`csvs bigger than 2 gigs`→(by_size, ext=csv, 2147483648),
`logs from today`→(by_time, ext=log, days=1); updated the vague-big test.
Added to `tests/test_cli.py`: the superlative abstain-with-hint path and the
plural-csv `-name` filter. The four original intent cases (size/time/name/
type) still pass. Full suite: **39 passed** (was 33).

**Real-shell checks (Done when).**
- `lb show me the biggest files here` → `LinuxBuddy: how big? try "over 100MB"`, exit 1 ✓
- `lb csvs bigger than 2 gigs` → `find . -type f -name '*.csv' -size +2147483648c`, exit 0 ✓

## 2026-11-03 ~15:25 — Task 06 (P1.2): verify the 360 reference commands vs the maze

**What this task is.** Not NLU verification — it checks that the ground-truth
`reference_shell_plan` for every one of the 360 scenarios actually runs
correctly against the maze. Raw verdicts only; I did NOT fix or drop any row.

**Harness.** `scratchpad/verify360.py` (kept in scratch — a throwaway
measurement tool, not product code). For each row: static safety gate, then
execute with cwd=`$PROJECT_DIR`, sourcing `bindings.env`. Results written to
`data/scenarios/verify_results.csv` (original columns + verdict, exit_code,
stdout_lines, stderr_excerpt, missing_dep).

**Safety (non-negotiable, enforced BEFORE running).** network/sudo →SKIP;
`/mnt/c` →SKIP (outside maze); GUI/external-launch (`*.exe`, `code`,
`explorer.exe`, `clip.exe`, `xdg-open`, …) and interactive (`less`/`vi`/
`watch`/`ssh`/`psql`/bare `python3`/`tail -f`) →SKIP, never executed; any
write whose resolved target is outside `~/testlinuxbuddy` →UNSAFE, not run.
Caught WORK-037 (`>> $HOME/.bashrc`) as UNSAFE. Maze rebuilt before EACH
writes row, so every writes row starts clean.

**Two faithfulness calls (interpreted — please sanity-check).**
1. Plans run against the *system* `python3`, not the lb `.venv` — a reference
   command models a real user's shell; venv-only `python3` gave false FAILs.
2. *No* `set -o pipefail` — a user pastes into default bash, where a
   pipeline's status is the last command's. With pipefail, `find|sort`
   hitting the maze's `noaccess_dir` and `sort|uniq|head` SIGPIPE invented
   failures the real shell never reports.
   Also: EMPTY means "exit 0 but nothing on stdout where output was implied";
   rows that redirect stdout to a file (`grep … > f`) or use silent `cmp -s`
   are PASS, not EMPTY.

**The hang (first attempt) and fix.** The first writes run stalled ~35 min
silently. Cause: `subprocess` capture-pipe deadlock — on the timeout path
`communicate()` blocks forever if a launched process keeps the pipe open.
Rebuilt the runner: stdin=/dev/null, per-row `timeout -k 2 10` (hard 10s),
stdout/stderr to temp FILES (not pipes), each row in its own process group
which is SIGKILLed afterward, a 20s Python backstop, and one progress line
(id+verdict) per row. Second run completed clean, exit 0.

**Results (raw): 244 PASS · 59 FAIL · 43 SKIP · 13 EMPTY · 1 UNSAFE** (360/360).
Per domain in the printed summary / `verify_results.csv`.

**FAIL breakdown by root cause (for triage — I fixed nothing):**
- ~20: whole-tree `find`/`grep -R`/`du`/`tar` over `$PROJECT_DIR` exit nonzero
  solely because the maze's deliberate `perms/noaccess_dir` (chmod 000) can't
  be traversed. stdout is otherwise correct. ONE systemic cause. Decision for
  you: add `2>/dev/null` to those refs, or accept nonzero exit as expected.
- ~12: `grep`/`cmp`/`diff`/`history|grep` exit 1/2 by design (no match / files
  differ). Semantically "found nothing"/"they differ", not a crash.
- Genuine reference/binding bugs worth fixing in the dataset:
  * ARCH-001 `tar -C $PARENT_DIR -- $PROJECT_NAME`: PARENT_DIR==PROJECT_DIR,
    so it tars `project/project` → "Cannot stat".
  * ARCH-023/031 `tar -C $RUN_DIR checkpoints|results`: no such subdir in
    run_001.
  * ARCH-022 `tar --wildcards '*checkpoint.pt'`: member not in the archive.
  * PY-003/018/024/036/039 run `$SCRIPT_FILE` (= `good_script.sh`, a SHELL
    script) through `python3`/`py_compile` → SyntaxError. SCRIPT_FILE binds a
    .sh but these rows assume a .py.
  * PROC-021 `ps -p "$(ps -p $PID -o ppid=)"`: unquoted cmd-subst yields a
    space-padded ppid → ps "improper list".
  * WORK-017/021 `mkdir $PROJECT_DIR`: dir already exists in a fresh maze →
    "File exists" (scenario wants a NEW dir but binds the existing one).
- A few read-only rows reference `output/` artifacts (TARGET_FILE,
  OUTPUT_FILE, COPIED_FILE, NEW_EXPORT) that only exist after a writes step;
  in isolation they're absent → FAIL (INS-007, TEXT-018, ARCH-024, FS-037).
- Environment-dependent: PROC-013/017/029/037 (process-tree/zombie/CUDA-env/
  `/proc/pid/io` quirks), PY-023/026/038 (pandas metadata / venv activate exit
  / venv-stub freeze diff).

**SKIP (43):** 14 windows `.exe` interop, 12 `/mnt/c`, 7 network, 3 `$HOME`
(outside maze), 2 `python3.11` absent, 1 numpy, 1 pandas, 1 `deactivate` not a
command, 1 GUI, 1 `/mnt/[a-z]` glob. **UNSAFE (1):** WORK-037 `>> ~/.bashrc`.

**Note for the human.** The ~20 `noaccess_dir` FAILs and ~12 grep/diff
exit-code FAILs are arguably "working as intended" depending on whether a
reference command is expected to exit 0. That's your call (the task said you
decide what to fix or drop); the raw verdicts are in `verify_results.csv`.
