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

## 2026-11-05 — Task 07 (P1.2.2): triage the 360 verdicts

**What this task is.** Separate the 59 Task-06 FAILs into (a) false failures
of the *verification method* and (b) genuine dataset bugs; fix only the genuine
ones; decide the 13 EMPTY rows. Added two columns to `verify_results.csv`:
`verdict_final` and `verdict_final_reason` (every one of the 360 rows now
carries a final verdict with a one-line justification). Original `verdict`
column is left untouched for provenance. A backup of the pre-triage CSV is in
the session scratchpad.

**Headline result.**
`verdict_final`: **PASS 275 · PASS_WITH_STDERR 21 · PASS_IN_SEQUENCE 1 ·
ACCEPTED_EMPTY 13 · ENV_UNSUPPORTED 3 · SKIP 43 · UNSAFE 1 · FAIL 3** (360/360).
**True pass (PASS + PASS_WITH_STDERR) = 296/360 = 82.2%.** Counting the
correct-but-sequence/host-blocked commands too (PASS_IN_SEQUENCE + ENV), 300
of 360 reference commands are correct. **Only 3 genuine dataset defects
remain**, all the same root cause (see below).

**Step 1 — reclassified false failures (verified each against its recorded
stderr/exit, did not trust the list blindly):**
- **20 → PASS_WITH_STDERR.** `find`/`tar`/`du`/`grep -R` whose *only* nonzero
  cause is the maze's deliberate `perms/noaccess_dir` (chmod 000). Confirmed
  programmatically that each one's stderr is noaccess-only and stdout is the
  expected content. (FIND-003/006/012/013/016/019/021/024/030/037/040,
  ARCH-021/029/039, FS-024/029/034/035, TEXT-025, WORK-040.)
- **15 → PASS.** grep/cmp/diff/comm that exit 1 with empty stderr = correct
  "no match / files differ", not a crash. Confirmed empty stderr + exit 1 on
  each. (TEXT-009/011/012/017/032/034, INS-023/024, ARCH-032/034, WORK-026,
  PROC-017/029, FS-037, PY-038.)

**Step 2 — fixed the genuine dataset bugs (CSV only; re-verified each against a
freshly rebuilt maze, writes rows on a clean maze, PROC-021 with a live
runtime PID). I deliberately did NOT mutate `build_maze.sh`/the maze — a shared
byte-reproducible fixture; mutating it mid-triage would risk silent regressions
across the 244 originally-passing rows and force a full 360 re-run. The task
allowed "fix the command's target" as the alternative, so I took it.**
- **ARCH-001** — `-C "$PARENT_DIR"` tarred `project/project` (PARENT_DIR==the
  project dir; see binding note G). Fixed to `-C "$MAZE_ROOT"`. Re-verify: the
  archive is now created correctly; the only residual nonzero is the
  `noaccess_dir` artifact → **PASS_WITH_STDERR** (not clean PASS).
- **PY-003/018/024/036/037 + WORK-039** — these ran `good_script.sh` (a bash
  script) through `python3` → SyntaxError. The task suggested switching to
  `bash`, but the scenarios are inherently Python (run a Python script,
  `py_compile`, `tracemalloc`, `importtime`, env-passing). So I repointed the
  placeholder `$SCRIPT_FILE` → `$TRAIN_SCRIPT` (`scripts/train_stub.py`, the
  maze's deterministic runs-anywhere Python stub) — a faithful fix that keeps
  each scenario's Python meaning and runs green. PY-018 additionally redirects
  the script's stdout into `$OUTPUT_FILE` so its `test -f "$OUTPUT_FILE"`
  passes ("the output was produced"). All six now exit 0.
  *Correction to the task's list:* the sixth python-via-.sh row is **WORK-039**,
  not PY-039. Actual **PY-039** in the CSV is a passing `multiprocessing`
  inspection row and was left untouched.
- **PROC-021** — `$(ps -p "$PID" -o ppid=)` yields a space-padded ppid, so the
  outer `ps -p " 1234"` errored "improper list". Quoting alone doesn't help (it
  was already quoted); fixed by stripping whitespace: `… | tr -d ' '`. Exit 0.
- **WORK-017/021** — `mkdir -- "$PROJECT_DIR"` failed ("File exists"); the maze
  already has the project dir. Added `-p` (task's first suggestion) so it's
  idempotent. Both exit 0.
- **ARCH-022** — `--wildcards '*checkpoint.pt'` found no member (the archive
  holds README/a/b/c.txt, no checkpoints). Retargeted the wildcard to `'*.txt'`
  — same command shape ("inspect a tar before selective extraction"), now lists
  real members, exit 0.
- **ARCH-023** — `tar -C "$RUN_DIR" checkpoints`: `runs/run_001` has no
  `checkpoints/` subdir. Retargeted to pack the run dir itself
  (`-C "$RUNS_DIR" run_001`) — "pack the run's saved artifacts". Exit 0.
- **ARCH-031** — `tar -C "$RUN_DIR" results`: no `results/` subdir. Retargeted
  to pack the run's result file (`-C "$RUN_DIR" metrics.txt`). Exit 0.
- **ARCH-024** — the task filed this under "missing archive member", but its
  real fault is a dangling `$COPIED_FILE` (`output/sales_copy.csv`) that **no
  row creates**. The scenario ("verify the copied model is identical")
  presupposes a copy, so I made it self-contained: prepend
  `cp -- "$ORIGINAL_FILE" "$COPIED_FILE"`, then the checksum+`cmp` verify
  identical bytes. Exit 0. **This changes its `risk` read-only → writes** (now
  updated in the CSV) — flagging because it moves the row under the Phase-2
  destructive-location gate.

**Step 3 — EMPTY rows (13): all marked ACCEPTED_EMPTY with a reason** (I did
not add maze content, same fixture-stability reasoning as Step 2). Three kinds:
- *Non-interactive shell (expected):* WORK-011 `history`, PROC-014 `jobs -l`.
- *Recency window vs the maze's fixed historical mtimes:* FIND-023 (-mmin
  -2880), FIND-033 (-mmin -4320). The commands are correct; byte-reproducible
  fixtures carry old timestamps, so "last N days" matches nothing.
- *Content the maze doesn't carry, command correct:* FIND-010 (no `.pt`
  checkpoints), FIND-014 (no multi-GB files by design, so `-size +1G` is
  always empty), FIND-018 (no `train_*` in processed), FIND-032 (output/ empty
  until a run writes), ARCH-014/019 (archives live in `archives/`, not the
  `backups/` dir these target — likely a binding mismatch), ARCH-015 (no
  `data/` member in the archive), TEXT-020 (no "deprecated" string in
  train.log), TEXT-026 (no BEGIN/END METRICS markers). Each is a candidate for
  a one-line `build_maze.sh` addition later if you want the scenario literal;
  none is a command bug.

**Beyond the task's explicit lists** (verified live; flagging as interpreted):
- **FS-016 → PASS** — `test -z "$(ls -A RESULTS_DIR)"` on a non-empty dir
  correctly prints nothing and exits 1 (same "expected negative" logic as the
  grep no-match class).
- **INS-035 → PASS** — the JSONL validator raises on `malformed.jsonl`'s
  deliberately-invalid line 3; a nonzero exit is exactly the intended signal
  that a bad line exists. (A friendlier reference would print the line number
  rather than a traceback — noted as optional polish, not a correctness bug.)
- **PROC-013 → PASS** — `ps --ppid "$$"` finds no children in the verification
  shell and exits 1; correct no-match.
- **TEXT-018 → PASS_IN_SEQUENCE** (new label) — reads `$OUTPUT_FILE`, which the
  writes rows ARCH-006/ARCH-025 create; absent only under isolated single-row
  verification. Correct command, missing precondition.
- **PROC-037 / PY-023 / PY-026 → ENV_UNSUPPORTED** (new label) — correct
  commands this host can't run: WSL exposes no `/proc/<pid>/io`; `pandas` isn't
  installed; `python3-venv`/`ensurepip` isn't installed. Not dataset bugs.

**Genuine remaining failures (3) — all one root cause, left for you to
decide:** INS-007, FS-022, FS-040 all read `$TARGET_FILE`
(`output/target.txt`), a write-target that **no scenario row creates** and the
maze omits — so these read-only rows have no valid operand in any order. Fix
options: rebind `TARGET_FILE` to an existing file, or create `output/target.txt`
(and a row that produces it) in `build_maze.sh`. I did not fix these — not in
the task's genuine-bug list, and the fix is a binding/fixture decision, not a
command edit.

**Step 4 — the one product decision (recorded, NOT acted on).** Should
LinuxBuddy's *generated* `find`/`grep -R`/`du`/`tar` commands append
`2>/dev/null` to suppress the permission-denied noise from unreadable dirs
(like the maze's `noaccess_dir`)? For: cleaner output, exit stays meaningful to
a new user. Against: hand-written finds rarely do this, and silencing stderr
can hide real "permission denied" problems the user *should* see. This is the
single cause of the 21 PASS_WITH_STDERR rows. **Left open — your call.**

**Re-verification harness.** Throwaway scripts in the session scratchpad
(`reverify2.sh` + `triage.py`); not product code, not committed. Each fixed
writes row was run on a freshly rebuilt maze; the maze was rebuilt clean at the
end (archive fixture confirmed back to README/a/b/c.txt).

## 2026-11-05 — Task 08 (Tier 1): domain file_inspection

**What I did.** Built the second domain, `file_inspection`, as 6
single-command read-only intents (TDD, tests first). Introduced the Phase-2
**NLU router** that every later domain will plug into.

**Router (new in nlu.py).** `parse()` is now a router over `_ROUTER`, a tuple
of domain parsers tried in order. Each parser returns a `Frame` (matched),
`None` (not my domain — try next), or the `_ABSTAIN` sentinel (this *is* my
domain but the request is compound/underspecified — stop, abstain, do NOT let a
later domain guess at one fragment). `file_discovery` stays LAST so a bare
extension like "json" still routes to `find_by_type`. The old `parse` body is
now `_parse_file_discovery`; its behaviour is unchanged (all 39 prior tests
still pass).

**Intents → commands** (`kb/commands/inspect.yaml`, capability `inspect_file`,
all `risk_ops: [read]`): preview_head `head -n {count} -- {path}`,
preview_tail `tail -n {count} -- {path}`, count_lines `wc -l -- {path}`,
show_size `wc -c -- {path}` (bytes), detect_type `file -- {path}`, show_stat
`stat -c {fmt} -- {path}`. Preview `count` defaults to 10. `show_stat` picks
`%y %n` for a time-focused ask, `%A %n` for a permission ask, else
`%y %A %s %n`.

**Decisions (interpreted — flagging per CLAUDE.md).**
- *Compound → abstain, via broad nouns.* "preview, count and size of this csv"
  must abstain, not resolve to one part. I detect compound by counting *broad*
  action categories (preview/count/size/type/stat) present as literal nouns —
  independent of whether a precise intent cue fired — and abstain at ≥2. That
  stops the request falling through to file_discovery's "csv" → find_by_type.
- *The stat `fmt` is one argv element with spaces* (e.g. `%y %A %s %n`). That
  is the design working as intended: one slot value → one argv element, and
  the renderer quotes it (`stat -c '%y %A %s %n' -- f`). A round-trip test
  asserts it.
- *Deferred:* `less`/`od`/`nl`/`cat -A`/`sha256sum`/`cmp`/`diff`/`sed`/`python`
  one-liners and all multi-command "sanity check" rows — Tier 1 is
  single-command only. `wc -w` (word count, INS-011) is not one of the six
  task intents, so "how many words" is not mapped.
- *No concrete file named* ("last 50 lines of the log") → the intent is
  recognised but the frame carries no `path`, so the CLI abstains at
  planning. Verification uses real filenames, where it compiles and runs.

**Tests.** `tests/test_file_inspection.py` — the task table (incl. the
compound-abstain case), preview defaults, planner/render incl. the spaced-fmt
round-trip, and a file_discovery regression. **Full suite: 53 passed** (was 39).

**Maze verification (Done when).**
- `lb first 20 lines of train.log` → `head -n 20 -- train.log`; run in the
  maze it prints exactly 20 lines. ✓
- `lb how many lines in train.log` → `wc -l -- train.log` → 1988. ✓
- `lb size of config.yaml in bytes` → `wc -c` → 155; `lb when was model.pkl
  last changed` → `stat -c '%y %n'` → the mtime. ✓

**Pass rate vs the 40 File-inspection maze scenarios.** The 6 intents map
cleanly onto **5** of the 40 rows (INS-005/010/012/015/031). The other 35 are
compound/multi-command or use utilities deferred for Tier 1 (od, nl, cat -A,
sha256sum, cmp, diff, sed, less, python one-liners). Low coverage is expected:
this domain is mostly compound in the dataset. The six intents themselves are
correct end-to-end against the maze.
