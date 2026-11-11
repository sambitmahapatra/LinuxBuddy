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

## 2026-11-05 — Task 09 (Tier 1): domain text_and_logs

**What I did.** Built `text_and_logs`: 5 read-only intents (grep + sort),
plugged a `_parse_text_and_logs` parser into the router between
file_inspection and file_discovery. TDD.

**Intents → commands** (`kb/commands/text.yaml`, capability `search_text`):
search_in_file `grep {gflags} -- {pattern} {path}`, search_recursive (same with
`-R`), count_matches (`-c`), sort_lines `sort -- {path}`, unique_lines
`sort -u -- {path}`.

**Key design decision — grep flags as ONE combined token.** The planner only
*appends* optional fragments, but grep flags must sit *before* the `--`.
Rather than teach the planner to position flags, the NLU computes a single
`gflags` token (e.g. `-nF`, `-niF`, `-RnF`, `-ciF`) and the KB puts it in one
argv element. This keeps "one placeholder per element", keeps `--`
compiler-inserted (so a pattern starting with `-` is still the pattern — an
injection guard), and keeps flag order deterministic. A hostile-pattern
round-trip test proves a `;rm -rf /` pattern stays one element.

**Pattern & flag rules (interpreted).**
- Pattern sources, in order: a quoted string; "the word/string/phrase X"; an
  explicit search verb ("search for/grep/look for/locate X", excluding vague
  tokens like "stuff"); an ALL-CAPS identifier (TODO, FIXME, API_URL); a
  log-level word (errors→error, warnings→warning, …). Plain "find X" is NOT a
  pattern source — that stays file_discovery's `find_by_name`.
- `-i` defaults ON for log-level words (error/warning/exception/…) and when the
  request asks to ignore case; otherwise OFF. `-F` (literal) and `-n` (on the
  show intents) are always set, per the task.
- recursive when the request says across/recursively/"in the project|src|
  configs"; the directory is taken from "<name> folder" or an "across/in <dir>"
  preposition.
- "find stuff" → no concrete pattern → abstain. A pattern with no concrete file
  ("how many warnings in the log") still yields the frame; the CLI abstains at
  planning (no path), as with file_inspection.

**Deferred (documented):** `tail -f` (watch) — mapping it would need the CLI to
print a "runs until Ctrl-C" note, but the CLI contract is "stdout is exactly
one command or empty", so I deferred it rather than break that contract.
Also deferred: `-v` invert, `-w`/`-x` word/whole-line, `-C` context, blank-line
regex, redirect-to-file, and sed/cut/comm/awk — Tier 2 / mini-language work.

**Tests.** `tests/test_text_and_logs.py` — the task table, hostile-pattern
round-trip, compile checks, and a prior-domains regression. **66 passed**
(was 53).

**Maze verification (Done when).** `lb show errors in train.log` →
`grep -niF -- error train.log` → 26 matching lines; `lb how many warnings in
train.log` → `grep -ciF -- warning train.log` → 39; `lb find TODO across src`
→ `grep -RnF -- TODO src` → lists the TODO hits in src/. ✓

**Pass rate vs the 40 Text-&-logs scenarios.** 8 of 40 map to the 5 intents by
command shape (TEXT-001/004/005/006/007/009/010/016). The other 32 use deferred
features above. NLU pattern extraction is reliable for quoted / "word X" /
log-keyword / ALL-CAPS patterns; arbitrary multi-word phrases need quoting.

## 2026-11-05 — Task 10 (Tier 1): domain processes + 2-stage pipe support

**What I did.** Added **2-stage pipe support** to the planner/renderer (the
batch required it before building pipe intents), then built `processes` as 6
read-only intents. TDD.

**Pipe support (new infrastructure).**
- *KB loader:* `_parse_flow_list` now splits flow-list commas **outside quotes**
  only, so a quoted `-o` field list like `"pid,ppid,stat,%cpu,%mem,args"` or
  `"pid,comm,%cpu"` stays one element instead of being shredded. (The old
  parser assumed no item ever contained a comma.)
- *planner.compile* returns a flat argv for a single command (unchanged), or a
  **list of argv lists** when the intent's KB spec has a `pipe_argv` stage.
  Each stage is built and placeholder-checked independently.
- *render.to_shell* detects a pipeline (all elements are lists) and joins the
  stages with ` | `. The `|` is compiler-inserted — never a slot, never an argv
  element — and each stage still round-trips via `shlex.split` on its own, so a
  hostile slot value in any stage stays one token.

**Intents → commands** (`kb/commands/process.yaml`, capability
`inspect_process`): list_processes `ps aux`; top_by_cpu
`ps -eo pid,comm,%cpu --sort=-%cpu | head -n {count}`; top_by_mem (same with
rss); find_process `pgrep -af {pattern}`; process_on_port
`ss -ltnp "sport = :{port}"`; show_pid
`ps -p {pid} -o pid,ppid,stat,%cpu,%mem,args`. top_by_* default count = 10.

**Decisions (interpreted).**
- *kill/pkill/killall → abstain.* Destructive, out of Tier-1 scope. The
  processes parser returns `_ABSTAIN` on a kill verb — which also stops
  "kill python" leaking to file_discovery (where "python" → `.py`). Verified
  `parse("kill python") is None`.
- *process_on_port's filter* `sport = :8080` is intentionally ONE argv element
  with spaces; the renderer quotes it (`ss -ltnp 'sport = :8080'`). A
  round-trip test asserts it.
- Router order is file_inspection → text_and_logs → processes →
  file_discovery, so process vocabulary wins before a bare word could look
  like an extension.

**Deferred (documented):** kill/pkill (destructive); `top -b -n 1`, `free -h`,
`nproc`, `watch`, `jobs -l`, and all `/proc/<pid>/*` inspection (lstart, nlwp,
fd, limits, io, status, meminfo, pressure) — compound/interactive or
file-reads, later tiers.

**Tests.** `tests/test_processes.py` — the task table, the pipe round-trip
(each stage re-tokenizes to its own argv), the quoted-filter round-trip, and a
prior-domains regression. **79 passed** (was 66).

**Maze verification (Done when; `runtime_setup.sh` sourced for $PID/$PORT).**
`lb what's using port <PORT>` → `ss -ltnp 'sport = :45739'` → shows the
http.server (python3 listening). `lb show the process with pid <PID>` →
`ps -p <PID> -o ...` → shows `sleep 300`. The pipe intent `lb what's using the
most cpu` → `ps -eo pid,comm,%cpu --sort=-%cpu | head -n 10` runs and lists top
CPU. ✓

**Pass rate vs the 40 Processes scenarios.** 7 of 40 map to the 6 intents by
command shape (PROC-001/004/007/008/009/022/027). The other 33 are the deferred
/proc/top/free/nproc/watch/jobs/kill rows.

## 2026-11-05 — Task 11 (Tier 1): domain filesystem_permissions (read-only)

**What I did.** Built `filesystem_permissions` as 6 read-only intents, closing
the Tier-1 batch. Generalised the 2-stage mechanism to also chain with `&&`.

**`&&` chaining (small generalisation of the pipe work).** The `check_*`
intents are `test … && printf …`. I introduced a single `Stages(list)` plan
container (in render.py) carrying its join operator; the planner emits
`Stages([test, printf], "&&")` for an intent whose KB spec has `and_argv`, and
`Stages([…], "|")` for `pipe_argv` (replacing the bare list-of-lists). Because
`Stages` subclasses `list`, the earlier pipe tests (`== [[…],[…]]`) still hold.
The operator is always compiler-chosen — never from a slot — so a hostile slot
can't inject a `&&` or `|`, and each stage still round-trips independently.

**Intents → commands** (`kb/commands/fs.yaml`, capability
`inspect_filesystem`): check_writable `test -w {path} && printf 'writable\n'`,
check_readable (`-r`), check_exists (`-e`, "found"), show_permissions
`ls -ld -- {path}`, show_owner `stat -c %U:%G -- {path}`, disk_usage
`du -sh -- {path}`. Target extraction handles "the <name> folder/dir" → name,
a bare `name.ext`, a slash path, and "here" → `.`.

**Decisions (interpreted).**
- *chmod → abstain* (destructive; "make this executable" / "set permissions"
  etc.). The fs parser returns `_ABSTAIN` so it doesn't leak to another domain.
- *dir_empty → DEFERRED (abstain).* The reference is
  `test -z "$(ls -A -- {path})" && printf empty` — a `$(…)` command
  substitution the flat-argv + shlex-round-trip model cannot represent safely.
  Per the task ("defer … don't hack it in unsafely"), "is X empty" abstains. A
  clean single-command alternative exists for later —
  `find {path} -maxdepth 0 -empty` — noted for Tier 2.
- *`test` takes no `--`.* POSIX `test` would treat `--` as an operand, so
  check_* deliberately omit it (matching the dataset); the path is still
  quoted to one argv element.
- *printf's `\n` is a literal backslash-n* in the argv (the KB subset parser
  does not process escapes); printf expands it at runtime. A test asserts the
  and-chain round-trips per stage.

**Tests.** `tests/test_filesystem_read.py` — the task table (incl.
dir_empty-deferred and chmod-abstain), the and-chain round-trip, and a
prior-domains regression. **92 passed** (was 79).

**Maze verification (Done when; run from $PROJECT_DIR / the file's dir).**
`lb can I write to the output folder` → `test -w output && printf 'writable\n'`
→ prints `writable`. `lb how big is the data folder` → `du -sh -- data` →
`5.2M data`. `lb who owns train.log` → `stat -c %U:%G -- train.log` →
`sambi:sambi`. `lb does config.yaml exist` → prints `found`. ✓

**Pass rate vs the 40 Filesystem scenarios.** Only **1** of 40 matches by
command shape (FS-007 `ls -ld`). The dataset's FS domain is dominated by
`find … -perm`, chmod, mv/cp/touch/ln (writes), readlink, `stat -f`, findmnt
and umask — all deferred (destructive or specialised). The six built intents
answer the simpler "can I write/read", "who owns", "how big", "does it exist",
"show permissions" questions; they're verified correct end-to-end against the
maze even though the maze's FS sampling barely exercises them.

## Tier 1 batch — summary

All four domains (08–11) built, each tested and committed separately; no push.
file_discovery regression intact throughout. **92 tests pass.** Router now
dispatches: file_inspection → text_and_logs → processes → filesystem →
file_discovery (bare-extension fallback). Planner/renderer gained safe 2-stage
`|` and `&&` composition. New domains cover their task intents; maze
scenario-coverage is modest by design because Tier 1 is single-command-only and
the dataset's inspection/processes/filesystem rows are largely compound,
`/proc`-based, or destructive (all deferred to later tiers).

## 2026-11-05 — Task 12 (P2.0): destructive-containment gate

**What I did.** Built the containment gate that every write/delete/chmod intent
will pass through — infrastructure before the first write domain (Tier 2). TDD.

**New modules.**
- `src/linuxbuddy/config.py` — one place for the two env vars. `mode()` →
  "prototype" (default) | "prod" (anything not exactly "prod" is prototype —
  fail safe toward containment). `maze_root()` → `LINUXBUDDY_MAZE_ROOT`
  (default `~/linuxbuddy/testlinuxbuddy`) resolved to a **real absolute path**
  (symlinks + `..` collapsed). Read live so tests/callers can set env per call.
- `src/linuxbuddy/gate.py` — `check(risk_ops, cwd) -> None | message`. A plan
  is destructive if its `risk_ops` include any of write/delete/privilege.
  prod → allow; prototype + read-only → allow; prototype + destructive + cwd
  under maze root → allow; otherwise abstain with
  `LinuxBuddy (prototype): destructive commands only run inside the test maze.
  cd into <MAZE_ROOT> first.` The under-root test resolves BOTH cwd and root
  with `realpath` then uses `os.path.commonpath`, so a `..` path or a symlink
  pointing out of the maze is correctly treated as outside.

**Design choice (interpreted).** The task wrote `check(plan, cwd)`. I made the
first argument the plan's **risk_ops list** itself — that *is* "a plan's risk"
per the task, it decouples the gate from the plan's argv representation, and it
makes the stub "fake write plan" in tests simply `["write"]`. The CLI gets the
real risk_ops from the KB via a new `planner.risk_ops(intent)` helper.

**Wiring (`cli.py`).** Pipeline is now parse → compile → **gate.check** →
render → print. The gate runs after compile and before render/print, so a
destructive command never reaches stdout from the wrong directory. Read intents
are unaffected (risk_ops `[read]` → allowed everywhere).

**Tests (`tests/test_gate.py`).** All five required cases plus two extra:
prototype-write-outside → abstain; prototype-write-inside (and root itself) →
allow; prototype-read-anywhere → allow; prod-write-anywhere → allow; **path
traversal** (`maze/project/../../outside`) → abstain; **symlink out of maze** →
abstain; mixed `["read","write"]` → destructive. **99 passed** (was 92).

**Manual gate check (Done when).** No destructive intent exists yet, so I
exercised it two ways: (a) read intents still emit from `/tmp` (outside the
maze) — `lb show errors in train.log` works there, confirming reads aren't
gated; (b) a stub `["write"]` plan through `gate.check` abstains from `/tmp`
with the maze message and returns `None` from
`testlinuxbuddy/project`. The default root resolved to
`/home/sambi/linuxbuddy/testlinuxbuddy`. The full CLI write-path is exercised
end-to-end by Task 13's `create_archive`.

## 2026-11-05 — Task 13 (Tier 2): domain archives_backup

**What I did.** Built `archives_backup` as 7 intents (3 read-only, 4 gated
writes) — the first domain to WRITE files, so the P2.0 gate (Task 12) now does
real work. `kb/commands/archive.yaml`, capability `manage_archives`. TDD.

**Intents → commands.**
- Read (anywhere): `list_archive` → `tar -tf {archive}`; `list_zip` →
  `python3 -m zipfile -l {archive}` (chosen by a `.zip` extension);
  `archive_integrity` → `gzip -t -- {archive}`; `archive_size` →
  `du -h -- {archive}`.
- Write (gated to the maze): `create_archive` →
  `tar -czf {archive} -C {parent} -- {name}` (parent defaults to `.`, name is
  the "<x> folder" being packaged); `extract_archive` →
  `mkdir -p -- {path} && tar -xf {archive} -C {path}` (the 2-stage `&&` chain);
  `compress_file` → `gzip -k -- {path}` (`-k` keeps the original).

**The `--` / tar bug (caught in maze verification, not by the unit test).** My
first cut emitted `tar -tf -- backup.tar.gz` and the unit test asserted it. But
`tar -f` takes the *immediately following* token as the archive name, so tar
read `--` as the filename and failed ("Cannot open --"). The dataset's
reference (`tar -tf "$ARCHIVE_FILE"`) correctly omits `--`. Fixed
`list_archive` to `tar -tf {archive}` and corrected the test to match the real
command. `create`'s `-czf {archive}` is fine ({archive} follows `-f`), and its
`-- {name}` terminator is valid because it precedes a file *operand* (exactly
dataset ARCH-001). This is a good example of why maze verification is required
even when unit tests pass — the test had encoded my wrong assumption.

**Routing.** `_parse_archives` sits before `_parse_filesystem` so
"how big is <archive>.tar.gz" → `archive_size` rather than the folder-oriented
`disk_usage`, and before `file_discovery` so a `.tar.gz`/`.zip` token isn't
swallowed as a `find -name` type query. Verb precedence inside the parser:
extract → create → list → integrity → bare-compress → size. A bare "compress
X" is `compress_file`; "compress X **into** Y.tar.gz" is `create_archive`
(the "into <archive>" cue).

**Deferred (documented, abstain or skip).** zip create (`zipfile -c`) and zip
extract (`zipfile -e`) — built the tar equivalents only; `gzip -dc > file` and
`tar -xOf … > file` (redirects can't round-trip); `cp -a`/`cp -n` folder copies
(writes, but a plain copy, not an archive op); `gzip -l` (original-size report,
a distinct intent); `tar --exclude …` / `--sort` / `--wildcards` member filters
(compound/specialised); locate-archives `find -name '*.tar.gz'` (that's
file_discovery). All deferred cleanly; none hacked in.

**Tests (`tests/test_archives.py`).** The task's example table, the zip-list
variant, the extract `&&` round-trip, risk_ops read/write per intent, and that
each write intent is refused by the gate from `/tmp`. Plus a prior-domains
regression. **108 passed** (was 99).

**Maze verification (Done when; run inside the maze).**
`lb what's inside backup_2026-01.tar.gz` → `tar -tf backup_2026-01.tar.gz` →
lists README.md/a.txt/b.txt/c.txt. `lb package the src folder into test.tar.gz`
→ `tar -czf test.tar.gz -C . -- src` → **created** test.tar.gz (members
`src/…`). From `/tmp` the same request **abstains** with the gate message
(exit 1, empty stdout). Extract and compress both execute end-to-end inside the
maze (`gzip -k` confirmed to keep the original). ✓

**Pass rate vs the 40 Archives scenarios.** 7 of the 22 single-command rows are
produced exactly (ARCH-001/002/004/008/009/012/013). ARCH-022 shares the
`tar -tf` prefix but adds a `--wildcards '*.txt'` member filter I don't emit, so
it is NOT counted. The remaining single-command rows are zip create/extract,
redirects, folder copies, member-filtered/deterministic tar, and locate-archive
finds — all deferred as above; 18 rows are multi-command. `extract_archive` has
no exact single-command maze row (ARCH-010 is a *zip* extract), but it's
grounded in the task table and verified end-to-end.

## 2026-11-05 — Task 14 (Tier 2): domain python_environments

**What I did.** Built `python_environments` as 5 intents (3 read, 2 gated
writes), closing the Tier 2 batch. `kb/commands/python.yaml`, capability
`python_env`. This domain is mostly network / shell-state / long-running, so
the disciplined move was to build the small clean core and abstain on the rest.

**Intents → commands.**
- Read (anywhere): `python_version` → `python3 --version && command -v python3`
  (2-stage `&&`); `where_python` → `command -v python3`; `check_package` →
  `python3 -c 'import importlib.util as u; print(u.find_spec("{pkg}") is not None)'`.
- Write (gated): `run_script` → `python3 -- {path}`; `check_syntax` →
  `python3 -m py_compile -- {path}` (writes a .pyc).

**Slot/injection notes.** The script slot is keyed `path` (not the task's
`{script}`) so the planner resolves `~`/`$HOME` for it like every other path.
`check_package` splices `{pkg}` into the `python3 -c` **Python** code — one
argv element, quoted whole by the renderer so it never re-splits in the shell.
The NLU restricts `pkg` to `[A-Za-z0-9._-]`, so it can't carry a quote to break
out of the Python string; a test asserts the rendered `-c` string round-trips
through `shlex.split` unchanged. The KB's stdlib YAML-subset parser handled the
single-quoted `-c` scalar (quotes/parens/`;`/spaces, no comma, no colon) fine.

**Routing — python before text (important).** "check main.py for syntax
errors" contains "errors", which the text domain would otherwise grab as a grep
pattern. Placing `_parse_python` before `_parse_text_and_logs` makes it
`check_syntax` instead. The python parser only fires on specific cues
(version / where / package-probe / run-a-.py / syntax), so it doesn't steal
genuine text/other queries — the full suite confirms no regression.

**Deferred → abstain (documented).** pip install/upgrade/download and venv
*create* (network); venv activate/deactivate (shell state — can't be a
subprocess); `http.server` (long-running); `compileall`/`cd && run`/module run
(compound); the bare `python3` REPL. The parser returns the abstain sentinel
for the pip/venv/server families so a fragment can't fall through to another
domain.

**Tests (`tests/test_python_env.py`).** The task table, the `&&` chain, the
`-c` round-trip, pip/venv abstention, risk_ops per intent + gate refusal from
`/tmp`, and a prior-domains regression. **119 passed** (was 108).

**Maze verification (Done when).** `lb what python version do i have` →
`python3 --version && command -v python3` → `Python 3.14.4` + `/usr/bin/python3`.
`lb is numpy available` → the importlib probe → `False` (numpy isn't installed
on this host — the probe correctly returns False, not an error; same for
pandas). `lb check src/pipeline.py for syntax errors` →
`python3 -m py_compile -- src/pipeline.py`, exit 0 inside the maze. `lb run
train.py` from `/tmp` abstains via the gate (exit 1, empty stdout). ✓

**Pass rate vs the 40 Python scenarios.** 6 of 22 single-command rows share the
command shape; of those, `where_python` (PY-002), `check_package` (PY-005,
PY-014) and `check_syntax` (PY-024) are exact-intent matches. PY-020/PY-023 use
the same `python3 -c` shape but are really *list-packages* / *package-version*
intents (via importlib.metadata) that I did NOT build. `python_version` and
`run_script` are grounded in the task table but have no plain single-command
maze row — the maze's run rows all carry env-vars/`-u`/`-X`/redirects, and its
version rows are the metadata intents above. The rest (REPL, venv
activate/deactivate, pip install/upgrade/download/freeze, compileall, venv-python
invocations, module run, env-var/redirect script runs, package-file location)
are all deferred per the task; 18 rows are multi-command. Low single-command
coverage here is expected and correct, exactly as the task noted.

## Tier 2 batch — summary

Gate + two write-capable domains, each tested and committed separately; no push.
**119 tests pass**, no regression across the six built domains. The P2.0
containment gate (`config.py`/`gate.py`) now guards every write intent: in
prototype mode a `risk_ops`-destructive plan is refused unless cwd is under the
maze root, verified live for archives (create/extract/compress) and python
(run/py_compile) — emits inside the maze, abstains outside. Router now:
file_inspection → python → text_and_logs → processes → archives → filesystem →
file_discovery. Seven domains built (file_discovery + Tier 1's four + Tier 2's
two); remaining: workspace_and_shell (multi-step) and wsl_interop (GUI), plus
the optional cheap follow-on now that the gate exists — chmod (filesystem) and
kill/pkill (processes).

## 2026-11-07 — Task 15 (Tier 3): chmod (filesystem) + kill (processes)

**What I did.** Completed two Tier-1 domains with their destructive intents,
now that the P2.0 gate exists. No new gate logic — the intents carry
`risk_ops: [write]` and the existing gate does the rest. TDD.

**filesystem_permissions — chmod (3 intents, gated).** `make_executable` →
`chmod u+x -- {path}`; `remove_executable` → `chmod a-x -- {path}`;
`set_permission` → `chmod {mode} -- {path}`. Mode resolution: an octal
(`600`/`644`/`700`) is used directly; else an intent phrase maps —
"only I can read/edit"/"private"/"only me" → 600, "only I can enter" → 700.
If neither the mode nor the target file can be determined, the parser abstains
(and `abstain_hint` now says *"what permissions? e.g. 600 for private"*).
Target extraction reuses the fs target finder, plus a chmod-object fallback
(the noun after set/chmod/make, or the object of read/edit) so "set config.yaml
to 600" and "only I should read secret.txt" resolve their file.

**processes — kill (2 intents, gated).** `kill_process` → `pkill -f -- {pattern}`;
`kill_pid` → `kill -- {pid}`. A digit right after a kill/process/pid word →
`kill_pid`; otherwise a process name ("named/called/matching X", "kill the X
process", "kill X") → `kill_process`. A bare "kill the process" (no name/pid)
abstains rather than emit a match-everything `pkill`. Generic words
(process/the/it/…) are blocked from becoming a pkill pattern.

**Replaced the old abstains.** Task 10/11 returned `_ABSTAIN` on any kill/chmod
verb; those sentinels are gone, replaced by the real intents. The two old tests
were updated: `test_kill_abstains` → now asserts `kill_process`;
`test_chmod_abstains` → kept as `test_chmod_no_target_abstains` ("make this
executable" still abstains, now because no file is named, not because chmod is
unsupported).

**Tests.** Added to `tests/test_filesystem_read.py` (make/remove exec, octal,
intent-word private, no-mode hint, gating) and `tests/test_processes.py` (named,
pid, unspecified-abstain, gating). **129 passed** (was 119), no regression.

**Maze verification (Done when).** Inside the maze: `lb make good_script.sh
executable` → `chmod u+x -- good_script.sh` runs (exit 0); a fresh `644` file
became `-rwxr--r--` after the emitted command, proving the bits change. From
`/tmp` the same request abstains via the gate. `lb kill the sleep process` →
`pkill -f -- sleep`; `lb kill process 4821` → `kill -- 4821`; both abstain from
`/tmp`. The kill path was executed end-to-end against a process I spawned
myself (`kill -- <pid>` genuinely terminated it) to avoid collateral from a
broad `pkill`. ✓

**filesystem_permissions and processes are now COMPLETE domains.** Only
dir_empty remains deferred in filesystem (needs `$(...)`).

## 2026-11-07 — Task 16 (Tier 3): domain workspace_and_shell (scoped multi-step)

**What I did.** Built `workspace_and_shell`: 10 read intents, 1 gated write
(make_dir), and the first **scoped multi-step recipe** (setup_project).
`kb/commands/workspace.yaml`, capability `workspace`. TDD.

**Intents → commands.** where_am_i `pwd`; go_home `cd ~`; go_back `cd -`; goto
`cd -- {path}`; list_all `ls -la`; who_am_i `whoami && id -nG` (2-stage `&&`);
which_shell `printf "%s\n" "$SHELL"`; show_history `history`; clear_screen
`clear`; check_installed `command -v -- {tool}`; make_dir (gated)
`mkdir -p -- {path}`; setup_project (gated) `mkdir -p -- {name}/data
{name}/reports && cd -- {name}`.

**Scoped multi-step — deliberately ONE fixed recipe.** setup_project emits a
fixed mkdir+cd sequence via the existing `&&` Stages composition; the subfolders
are fixed defaults (data, reports) for V1. It is NOT general "do A then B"
decomposition (that's V1.1): a workspace verb combined with a compound marker
("then"/"&&"/"after that") returns the abstain sentinel, and "export … then cd …"
abstains.

**Planner: compile-time ~/$SHELL resolution (invariant #5).** Added
`_resolve_literal` so a whole argv element that is `~`/`$HOME`/`$SHELL`/`$USER`
is resolved at compile — `cd ~` emits `cd /home/sambi`, `printf … "$SHELL"`
emits the resolved shell path. Only exact-match whole elements are resolved
(never a `$` substring), so it can't corrupt a pattern; existing argv is
unaffected.

**Two routing disambiguations (and a latent bug fixed).**
- *"installed" vs "available".* Moved "installed"/"do I have" OUT of the python
  and filesystem parsers: a *tool* is "installed" / "do I have X" →
  check_installed (`command -v`), a *package* is "available"/"importable" →
  python check_package. So "is docker installed" (tool) and "is pandas
  available" (package) now route correctly.
- *Latent substring bug.* file_inspection tested `"count" in low`, which fired
  on "ac**count**" — so "what account am I using" was mis-read as count_lines.
  Fixed that and the sibling checks ("size"/"bytes"/"preview"/"format") to use
  word boundaries. (Good catch from a workspace test; it affected any phrase
  containing those substrings.)

**Router.** workspace sits after filesystem (file-ish queries stay with
filesystem) and before file_discovery (it catches navigation/shell verbs that
file_discovery would otherwise abstain on).

**Tests (`tests/test_workspace.py`).** where_am_i, go_home (~ resolved, no bare
~ emitted), goto, check_installed, who_am_i `&&`, which_shell ($SHELL resolved),
make_dir (gated), the setup_project recipe (gated), compound abstention, and a
prior-domains regression. **139 passed** (was 129).

**Maze verification (Done when).** `lb where am I` → `pwd`; `lb do I have git
installed` → `command -v -- git` → `/usr/bin/git` (the `--` works); `lb set up a
project folder called demo` → `mkdir -p -- demo/data demo/reports && cd -- demo`
— ran in a subshell, created demo/ + demo/data + demo/reports. make_dir and
setup_project both abstain from `/tmp`. Also confirmed `take me home` →
`cd /home/sambi` (no ~) and `which shell is this` → `printf '%s\n' /bin/bash`. ✓

**workspace_and_shell is a complete domain** (multi-step scoped to the named
recipe; general compound is V1.1).

## 2026-11-07 — Task 17 (Tier 3): domain wsl_interop — ALL 9 DOMAINS COMPLETE

**What I did.** Built the final domain, `wsl_interop` — 8 read-only intents,
the WSL/Windows bridge no other tool helps with. `kb/commands/wsl.yaml`,
capability `wsl_interop`. TDD. This completes Phase 2 (all 9 domains).

**Intents → commands.** open_explorer `explorer.exe .`; goto_cdrive `cd /mnt/c`;
goto_home `cd ~`; path_to_linux `wslpath -u -- {winpath}`; path_to_windows
`wslpath -w -- {path}`; copy_to_clipboard `pwd | clip.exe` (2-stage pipe);
cdrive_space `df -h /mnt/c`; home_space `df -h ~`.

**Deferred — nested `$(...)` (abstain).** "take me to my windows downloads/
desktop/documents", "where my Windows user folder lives", and cp-to-windows all
need `cd $(wslpath $(cmd.exe …))` / powershell lookups, which the flat-argv +
round-trip model can't represent safely. The parser returns the abstain
sentinel for those (a known V1 limit; candidate for a V1.1 WSL path resolver).

**Routing.** wsl fires only on WSL/Windows/C-drive/clipboard/explorer/wslpath
cues, so it never steals generic navigation. It sits BEFORE filesystem — "how
much space does ubuntu have left" contains "how much space", which filesystem's
disk_usage would otherwise grab (and then abstain, finding no folder target);
putting wsl first routes it to home_space. It's also before workspace so
"windows downloads" abstains instead of becoming a bad `goto`.

**Tests (`tests/test_wsl_interop.py`).** open_explorer, goto_cdrive,
path_to_linux (C:\ winpath extraction), path_to_windows, copy_to_clipboard pipe
round-trip, cdrive_space, nested-$() abstention, all-read-only, and a
prior-domains regression (confirms "take me home"/"go to src" still route to
workspace, not wsl). **148 passed** (was 139).

**Verification (Done when).** Script-verified against real WSL:
`lb convert 'C:\Users\sambi' to a linux path` → `wslpath -u -- 'C:\Users\sambi'`
→ `/mnt/c/Users/sambi`; `lb how would /home/sambi/linuxbuddy look on windows` →
`wslpath -w` → `\\wsl.localhost\Ubuntu\…` (the `--` works with wslpath);
`lb free space on C drive` → `df -h /mnt/c` (301G disk); `lb how much space does
ubuntu have left` → `df -h /home/sambi`. **Hand-tested only (NOT executed by the
script, per the task's explorer-cascade warning):** `open this folder in
explorer` → `explorer.exe .`; `put my path on the windows clipboard` →
`pwd | clip.exe`; `take me to the C drive` → `cd /mnt/c`. Nested
"windows downloads" abstains. ✓

## Tier 3 batch — summary / PHASE 2 COMPLETE

All 9 domains are built. Tasks 15–17 each tested + verified + committed
separately; no push. **148 tests pass**, no regression. Tier 3 added: the
destructive chmod/kill intents (completing filesystem + processes), the
workspace domain with the first scoped multi-step recipe (setup_project), and
the wsl_interop bridge. The planner gained compile-time ~/$HOME/$SHELL/$USER
whole-element resolution; a latent "account"→count substring bug was fixed.

Final router order: file_inspection → python → text_and_logs → processes →
archives → wsl → filesystem → workspace → file_discovery. Reads work anywhere;
every write/destructive intent (archives create/extract/compress, python
run/compile, chmod, kill, mkdir, setup_project) is gated to the maze by the P2.0
containment gate. **Next: install + dogfood, then decide Phase 3 (the LinearSVC
intent model) and generalized multi-step from real use — not speculatively.**

## 2026-11-07 — Task 21: evaluation sweep (raw capture, no execution)

**What I did.** Ran `lb` on all 130 requests in
`data/eval/eval_requests.csv` from a fixed cwd (`testlinuxbuddy/project`, with
`bindings.env` + `runtime_setup.sh` sourced, torn down after), capturing
stdout/stderr/exit/outcome into `data/eval/eval_results.csv`. The harness runs
`lb` only — it NEVER executes what lb prints (several requests are destructive).
Capture only; no correctness judgment (that's the human's step).

**Mechanical tally (COMMAND = stdout non-empty, ABSTAIN = empty):** 66 COMMAND,
64 ABSTAIN across 130. Per domain — archives 1/8, edge_cases 0/7,
file_discovery 13/6, file_inspection 6/7, filesystem 10/6, processes 11/4,
python_env 7/6, text_and_logs 2/13, workspace 12/1, wsl_interop 4/6
(COMMAND/ABSTAIN).

**Notes for the human's analysis (mechanical, not verdicts).** exit codes are
0 (command) / 1 (abstain) only — the Task-18 exit-3-for-destructive scheme is
not present, so destructive commands emitted inside the maze show exit 0. The
high-ABSTAIN domains (text_and_logs 13, archives 8, edge_cases 7) are where the
human should look first; e.g. phrasings like "terminate the sleep process" (vs
"kill") abstain. All raw rows are in the CSV for review.

## 2026-11-07 — Task 19 (v1-finish): find_largest intent

**What I did.** Added `find_largest` to file_discovery — "biggest/largest/top N
files", a top dogfooding gap that used to abstain. Read-only, no threshold:
`find {path} -type f -printf '%s\t%p\n' | sort -rn | head -n {count}`. TDD.

**N-stage pipe.** Generalised the planner's composition from 2 stages to an
arbitrary `|` chain: a spec may declare `pipe_argv`, `pipe2_argv`, `pipe3_argv`
(all `|`) → `Stages([base, …], "|")`. `&&` stays a single `and_argv`. render's
`Stages` already joined N stages, so no render change. Chose the `find -printf`
form (files-only, exact) over `du -ah` (includes dirs); `%s\t%p\n` keeps literal
\t/\n (find expands them), each stage round-trips, `|` is compiler-inserted.

**Routing.** find_largest fires on an explicit superlative (`top N`, `N
largest`, `by size`, `most space`) OR a large-direction cue (big/huge/largest…)
with a plural/space context and no numeric threshold — so "biggest files",
"which files are huge", "largest files in data" all emit, while "how big is this
file" (singular, no "files") still abstains and "files over 100mb" stays
find_by_size. count: "top N"/"N largest" → N, else 10. path: a "X folder" noun,
an explicit path, or "in <known-dir>", else `.`. Added an `_FLARGE_RE` guard to
file_inspection so "top N files by size" isn't grabbed as show_size.

**Superseded old tests.** Task 05 had enforced abstain-on-thresholdless-size
(to avoid match-everything `find . -type f`). find_largest is bounded by
`head`, so that concern is moot; updated 4 tests (test_nlu×3, test_cli×1) and
the find.yaml intent-count test to the new emit-a-command behavior.

**Tests.** `tests/test_find_largest.py` (incl. the 3-stage pipe round-trip).
**156 passed.**

**Maze verification (Done when).** `lb show me the biggest files here` →
`find . -type f -printf '%s\t%p\n' | sort -rn | head -n 10`, which lists
`./data/raw/huge_dataset.csv` (120MB) at the top. `lb top 3 files by size` →
count=3. `lb files over 100mb` → unchanged `find … -size +104857600c`. ✓

## 2026-11-07 — Task 20 (v1-finish): asymmetric abstain policy

**What I did.** Made abstention asymmetric by risk, per dogfooding (the tool
abstained too readily on SAFE requests — itself a failure for a Linux-new user).

**Policy (CLAUDE.md invariant #6 rewritten, nlu docstring fixed).** Read-only +
a reasonable interpretation → emit (use defaults, glob-resolve references); a
wrong grep/find is cheap. Read-only + no operation named ("fix this", "do the
thing") → abstain. Destructive + anything less than a confident parse → abstain
(unclear target/mode still refuses). Updated invariant #6 and removed the stale
"abstain over guess (universally)" framing from the nlu module docstring and the
Task-05 gate note (the gate still governs find_by_size/time/name; superlatives
are handled before it).

**Concrete conversions.**
- Size superlatives on a read now emit (Task 19 did biggest/largest;
  this task adds `find_smallest` — the ascending twin, `sort -n`, for
  "smallest/tiny files"). Dropped the stale `size_cue` gate (it didn't even list
  "smallest") in favour of the direction cue + plural/space context + no
  threshold.
- **"open <file>" mis-route killed.** `lb open huge_dataset.csv` used to emit
  `find . -name '*.csv'` (searched instead of acting). "open" is ambiguous on
  WSL and a reliable action needs nested $() (deferred), so per the task's
  fallback I abstain cleanly rather than emit a wrong command. ("open … in
  explorer" still routes to wsl open_explorer, which is checked earlier.)

**What still abstains (the safety asymmetry, unchanged).** chmod/kill/mkdir with
an unclear target or mode, and genuinely vague reads.

**Tests (`tests/test_asymmetric_abstain.py`).** reads emit (biggest/big,
smallest→find_smallest), "open X" abstains, vague reads abstain, destructive-
unclear abstains. **161 passed.**

**Maze verification.** `open huge_dataset.csv` → abstain (no stray find);
`smallest files` → `find … | sort -n | head`; `do the thing` → abstain;
`make this executable` → abstain. ✓

## 2026-11-07 — Task 22 (v1-finish): definite-reference resolution (#1 fix)

**What I did.** The eval's biggest failure pattern (28/50): users say "the log",
"the backup", "the config" — a definite reference, not a filename — so the intent
is recognised but there's no path and the planner abstained. Now a TYPED
definite reference resolves to a glob and a command is emitted.

**The glob must be UNQUOTED (new `render.Raw`).** The emitted command is
`grep -niF -- error *.log` — the user's SHELL expands `*.log`. But render quotes
every argv element (shlex.quote("*.log") → '*.log', which would NOT expand). So
I added `render.Raw(str)`: a TRUSTED shell-literal (a glob WE generated) that
render emits verbatim, guarded by a safe charset, and still proving the whole
command round-trips (`shlex.split(rendered) == argv`). Raw is only ever produced
by the planner/nlu from a recognised reference — never from a user slot. The
planner preserves Raw through slot resolution and re-wraps a whole element that
resolves to a Raw value; find's own `-name '*.csv'` stays NON-Raw (quoted —
find does its own globbing, the shell must not).

**References resolved** (`_definite_glob`): the log(s)→`*.log`; the
backup/tarball/archive→`*.tar.gz`; gzipped archive / the gz→`*.gz`; the
zip→`*.zip`; the config→`config.*`; the csv→`*.csv`; (python) the
script→`*.py`. Wired into the shared `_detect_path_arg` (so file_inspection,
text, filesystem, compress all get it), the archives parser (archive-type globs
for list/integrity/size/extract — NOT create, where a glob output name is
nonsense), and a python script helper.

**Documented choices.** (1) Subdirectory: a bare glob matches CWD only; from the
project root `*.log` may match nothing (logs live in logs/) — accepted, a
command the user edits beats an abstain; I did NOT force searches recursive.
(2) GENERIC references with no implied type ("this file", "sort this list") have
no glob → they KEEP abstaining (recognise the op, no file → compile fails →
CLI exit 1). That ~10-row residual is the documented motivation for the v2
attention model.

**Tests (`tests/test_definite_reference.py`).** the log→`grep … *.log`, warnings
count, the backup tarball→`tar -tf *.tar.gz`, gzipped archive→`gzip -t -- *.gz`,
the config file→`stat … config.*`, run the script→`python3 -- *.py`, the
Raw-round-trip, generic-still-abstains, and concrete-filename-unaffected.
**170 passed.**

**Maze verification.** In logs/: `errors in the log` → `grep -niF -- error *.log`
lists real ERROR lines; `how many warnings in the log` → `grep -ciF -- warning
*.log` → train.log:39. In archives/: `the backup tarball` → `tar -tf *.tar.gz`;
`gzipped archive` → `gzip -t -- *.gz`. `who owns the config file` →
`stat -c %U:%G -- config.*`; `run the script` → `python3 -- *.py`. `sort this
list` abstains. ✓

## 2026-11-07 — Task 23 (v1-finish): eval cleanup (wrong-routes, defaults, synonyms)

**What I did.** The smaller, specific fixes the eval exposed — grouped as the
prompt laid out. All verified end-to-end in the maze and covered by
`tests/test_eval_cleanup.py` (16 row-anchored tests).

**A. Wrong commands (priority — these emitted misleading commands).**
- E004 "which files are huge" emitted `command -v -- files` (!). Tightened
  workspace check_installed with a `_NOT_A_TOOL` stoplist (files/file/one/…) so
  the interrogative "which" can't become a tool name → now `find_largest`.
- E024 "print config.yaml" emitted a `find`. Added a NARROW display-verb preview
  in file_inspection (`print|cat|display|dump` + a concrete file, no log/search
  cue) → `head -n 10 -- config.yaml`. Kept it narrow after "show"/"read" first
  stole "show distinct rows", "only I should read X", "show …contents…zip" — so
  those verbs are excluded; "open" stays a Task-20 abstain.
- E090 "is numpy installed" emitted `command -v -- numpy` (always fails). Added a
  known-Python-package set; a known pkg → importlib `check_package`, an unknown
  token ("is docker installed") → workspace `command -v`.
- E016 "recently modified logs" dropped the time part — `_detect_time` now
  returns a 7-day default for "recently/lately/recent" → keeps `-mtime -7`.
- E018 "where is settings.json" globbed to `*.json` — `_detect_name` now also
  captures a concrete `name.ext` (extension must start with a letter so "3.11"
  isn't caught) → `find . -name settings.json`.

**B. Defaults.** E056/E058 "what's on my port" / "what's listening" (no number)
→ new `list_listening` intent = `ss -ltnp`, instead of abstaining.

**C. Known synonyms.**
- kill: "stop"/"terminate"/"end" + "… process" → kill_process (E060/E062). Gated
  by a `_KILL_TRIGGER_RE` that requires "process", so "stop the server" is NOT
  swept in.
- check_installed: "check if X is installed", "is X there/available" (E111).
- "room" → "space" synonym in the WSL space cue (E119 → home_space).
- archives: "zip up"/"bundle" already cued create; added source-name extraction
  ("zip up the project" → name=project, output project.tar.gz) (E084).
- chmod intent-words (E075/E077/E078): broadened `_PRIV_READ_RE` to "only I
  should be able to read/edit"; `_chmod_target` now resolves "the/this script" →
  `*.sh` and a generic "this file"/"only I" reference → a `FILE` placeholder the
  user fills. DECISION/CAVEAT: this is the one place a destructive intent emits
  against a placeholder rather than abstaining — justified because the MODE is
  unambiguous from the intent words, it's the enumerated Task-23 set, and the
  containment gate still blocks it outside the maze. A bare "make this
  executable" (no file noun / privacy cue) STILL abstains (Task 20 preserved).

**Tests.** `tests/test_eval_cleanup.py` (16) + regressions (stop-non-process not
kill, can-i-read stays check_readable, unknown-tool stays command -v). Full
suite **186 passed**. Maze: all 15 named rows now produce the intended command
(or correct abstain); the 3 wrong-command rows no longer mislead.

## 2026-11-07 — Re-run eval sweep → eval_results_v2.csv (after Tasks 19-23)

Re-ran the Task-21 harness (same method: run `lb` per request from the maze cwd,
CAPTURE only, never execute lb's output) to a NEW file so v1↔v2 can be compared.
`data/eval/eval_results.csv` (Task 21 baseline) is kept; v2 is the new file.

**Headline:** COMMAND 66 → **94**, ABSTAIN 64 → **36** (of 130). +28 requests now
produce a command.

Per-domain (COMMAND / ABSTAIN): archives 8/1, edge_cases 0/7, file_discovery
19/0, file_inspection 9/4, filesystem 14/2, processes 15/0, python_env 7/6,
text_and_logs 4/11, workspace 13/0, wsl_interop 5/5.

**Wrong-abstain analysis (the number that matters).** Of the 36 abstains:
- **Correct by design (13):** edge_cases E124-E130 (7 — "fix this", "help", …);
  deferred python E097/E098/E099/E100 (network / venv shell-state / long-running
  server); deferred filesystem E073 "is the output folder empty" (needs $());
  E120 "convert this windows path to linux" (no C:\ path supplied).
- **Generic-reference residual (~14) — the DOCUMENTED v2 motivation.** "this
  file" / "this" / "it" / an untyped noun with no resolvable glob: E025, E030,
  E031, E034, E036, E037, E038, E040, E043, E044, E045, E046, E047, E066. Task 22
  deliberately keeps these abstaining; the v2 attention model is meant to resolve
  the referent.
- **Near-miss phrasing gaps where a clear command DID exist (~9):** E023 "tail
  the app log" (word between "the"/"log" dodged the glob), E086 "extract the
  backup" (no destination dir), E094 "execute the analysis script" ("execute"
  not a run synonym + "analysis script"), E096 "does this script compile"
  (phrasing), E042 "search the whole project for deprecated" (recursive grep),
  E116/E121/E122/E123 windows-bridge phrasings.

**Net "wrong abstain where a specific v1 command was available": ~9** (the
near-miss group), down from ~45 at the Task-21 baseline. The ~14 generic-ref
rows are intentional v1 residual (not counted as wrong), and 13 are correct by
design. The ~9 near-misses are candidate v1 synonym patches but are OUT OF SCOPE
for the named Task-23 rows — left as documented follow-ups rather than chased
here (one-task-per-session discipline).

## 2026-11-07 — Task 18 (v1-finish): bash widget + exit-code risk signaling

**Why.** The #1 dogfooding finding: a printed command a Linux-new user must
retype is useless. The command must land IN the shell buffer, ready for Enter.

**lb risk signaling (cli.py).** stdout stays EXACTLY the command; risk is now in
the exit code: 0 = read-only, 3 = destructive (write/delete/privilege, via the
existing `gate.is_destructive`), 1 = abstain (unchanged). A destructive plan
denied by the containment gate still returns 1 (nothing on stdout).

**shell/linuxbuddy.bash (new).** A `bind -x` Ctrl-G widget: reads
`READLINE_LINE`, runs `lb` (only lb — never its output), and tiers on the exit
code — read → replace buffer, cursor to end; destructive → replace buffer AND
print "⚠ destructive — review, then press Enter" above the prompt; abstain →
leave the typed line untouched and show the hint. Install comment included.

**shell/linuxbuddy.zsh (updated to parity).** Same three tiers (it previously
only replaced the buffer on exit 0 and showed stderr otherwise) — added the
destructive warning path and kept the abstain-hint path.

**Tests.** `tests/test_cli_exit_codes.py`: read → 0, destructive (prod mode) →
3 with `chmod u+x -- run.sh` on stdout, destructive denied outside maze → 1 +
empty stdout, abstain → 1. Full suite **190 passed**.

**Manual check (bash, sourced widget, invoked non-interactively from the maze):**
1. "find big csv files" → buffer = `find … | sort -rn | head -n 10`, no warning.
2. "make run.sh executable" → buffer = `chmod u+x -- run.sh`, warning printed
   above the prompt.
3. "fix this" → buffer UNCHANGED, hint "not sure what you mean" below.
4. "go home" → buffer = `cd /home/sambi` (lands in the buffer; the user's own
   shell runs the cd — the reason for buffer injection over a subprocess).

**Report (read vs destructive buffer):** a read request fills the buffer silently
with the command; a destructive request fills the buffer with the real command
(`chmod u+x -- run.sh`) AND surfaces the ⚠ warning — the command is editable and
never auto-runs. This is the task that turns "built" into "usable".

## 2026-11-07 — Task 24: full scenario sweep (route + execute) → sweep_results.csv

**What I did.** Ran the 139-row `data/eval/sweep_scenarios.csv` through `lb` from
inside the maze, capturing BOTH routing (what lb says) and executability (does
the emitted read command actually run clean). Capture only — no correctness
judgment; the human reviews `data/eval/sweep_results.csv`.

**Phase-2 path taken: throwaway copy** (`cp -a testlinuxbuddy
/tmp/maze_destructive_run`). Destructive ROUTING captured against the canonical
maze (confirms exit 3); destructive EXECUTION run against the copy, then the copy
deleted.

**Harness safety fix (paid for on the first run).** The first run was killed
mid-sweep (exit 144): executing E108 "stop the python process" ran
`pkill -f python`, which scans the WHOLE SYSTEM and killed the harness itself —
the maze copy does not sandbox pkill. Fix: never EXECUTE kill-family commands
(`pkill`/`killall`/`kill <pid>`); their routing is still captured, execution is
marked `skipped-kill-unsafe` (3 rows: E107/E108/E109). Canonical maze was
verified intact after that aborted run before continuing. Filesystem/archive
destructive commands (chmod/tar/cp) ARE cwd-contained and were executed in the
copy safely.

**Integrity re-check: PASS.** My content snapshot of the canonical maze
(path/type/mode/size over 2323 entries, volatile runtime files excluded) was
identical before and after: `06ecdaa3…` → `06ecdaa3…`. MANIFEST.txt sha
`89ba5fc4…` unchanged. NOTE: the prompt referenced `5af914bd…` as the expected
MANIFEST sha; the actual committed MANIFEST.txt hashes to `89ba5fc4…`, so the
prompt value appears stale — I used an unchanged-before/after content snapshot as
the real integrity signal rather than a hard-coded constant.

**Tallies.** COMMAND 93 / ABSTAIN 46. Read-row executability: ok 42, nonzero 36,
skipped-abstain 39, skipped-gui 3. exit-code↔risk mismatches: 10.

**Signals for the human (NOT fixed here — capture only):**
- `cd -- *.log` for E001 "take me to the logs folder" and similar: Task 22's
  definite-reference glob leaks into the navigation `goto` target (should be
  `cd logs`). A real routing finding the sweep caught — candidate follow-up task.
- Many `nonzero` read rows are benign: `find` prints "Permission denied" on the
  intentional chmod-000 `project/perms/noaccess_dir` (exits 1 but lists the rest);
  a grep with no match exits 1.
- The 10 mismatches are mostly destructive intents lb ABSTAINS on (pip_install
  E138/E139; some archive/chmod rows → exit 1), plus E137 "run train.py"
  (run_script is a gated write → exit 3 though the scenario labels it read) and
  E110/E127 routed to reads. All expected signals, left for human analysis.

Committed `sweep_results.csv` + `sweep_scenarios.csv`. Not pushed.

## 2026-11-08 — Task 25 (BATCH 25-27): routing priority + parsing bugs

Driven by `sweep_results.csv`. The silent-wrong-command fixes (a confident wrong
command is worse than an abstain), done first.

**A. `find` was a greedy catch-all.** Root cause: when a view/count/copy/perm/
process request happened to contain a filename or glob and no specific parser
claimed it, it fell through to file_discovery's `find`. Fix = make the specific
parser claim it (find stays the last-resort fallback):
- file_inspection: broadened the view cue (`show me/peek at/what's in/…`, gated
  by `_VIEW_DEFER_RE` so unique/sort/perms/folder/process/archive-ext requests
  are NOT stolen) → E047 `head config.yaml`, E050 `head *.log`, E052 `head
  data.csv`; extended tail/head to no-number "last lines" → E054 `tail *.log`.
- text: "remove duplicate(s)" → unique (E075 `sort -u`); line-count defers to
  grep-count when a log word is present → E069 `grep -ciF warning`.
- filesystem: "who can read X" → show_permissions (E096 `ls -ld`).
- processes: "list the <name> processes" → find_process (E101 `pgrep -af
  python`; reasonable + editable, chosen over a bespoke `ps|grep` intent).
- archives: new `copy_file` intent — "make a copy of X"/"duplicate X" → `cp -- X
  X.bak`, **risk write → exit 3** (E127). Guarded against clipboard / windows.
- reverse misroute: dropped "locate" from the grep search-verbs — it's a
  DISCOVERY verb → E035 `find . -name train.py`.

**B. Four parsing bugs.**
1. E088 "what's today's date" emitted grep garbage: the contraction apostrophe
   was read as a 'quoted' grep term. Grep-quote detection is now whitespace-
   bounded; added a `date_time` intent (workspace) → `date`.
2. E071 recursive grep duplicated the pattern into the path slot: a recursive
   grep with no explicit dir now uses `.`, never the `_detect_path_arg` fallback
   (which grabbed the quoted pattern) → `grep -RnF -- deprecated .`.
3. E042 size comparator was inverted/hardcoded `+` in the KB. Direction now
   chosen in nlu (`_size_sign`: under/less/smaller → `-N`, else `+N`); the
   size_bytes slot carries the sign, KB template is `{size_bytes}c`. "under 1kb"
   → `-1024c`; E040/E041 "over" stay `+`.
4. E019 absolute-path truncation (`cd /mnt/c`) — DEFERRED to Task 26 (navigation
   rebuild) per the prompt; not fixed twice.

**C. Housekeeping.** The stale MANIFEST sha constant (`5af914bd…`) lives in
MAZE.md (not CLAUDE.md); corrected to the current `89ba5fc4…`.

**Tests.** `tests/test_routing_priority.py` (16) + updated 3 size-slot tests to
the new signed representation. Full suite **206 passed**. Maze-verified all named
rows; confirmed find still wins for genuine discovery and grep neighbors
(E064/E067/E068) unchanged.

## 2026-11-08 — Task 26 (BATCH 25-27): navigation domain built properly

Navigation was never a real domain — it won on accidents in workspace, leaked
the Task-22 glob into `cd`, and emitted `cd -` for "go up". Built
`_parse_navigation` as a first-class parser, inserted after wsl and before
filesystem/workspace, and removed the go_home/go_back/goto/where_am_i branches
from workspace (navigation owns all cd/pwd now — which also kills the glob leak,
since the old workspace goto used `_detect_path_arg`).

**Resolution order (first match wins — directional words beat name matching):**
1. cd_parent — up/back/parent/"up N levels" → `cd ..` / `cd ../..` (new KB
   intent `cd_parent` with an `updots` slot; word-number map for "two"→2).
   E009 "take me to the parent folder" → `cd ..` (not `cd -- parent`).
2. cd_home — home/"take me home" → `cd ~` (→ absolute $HOME at compile).
3. cd_previous — "where i was"/"previous dir" → `cd -`. Guarded so "go up" and
   "project root" never reach it (fixes the stray `cd -` on E010/E016).
4. cd_ancestor — target that is a segment of `os.getcwd()` → `cd` to that
   ABSOLUTE ancestor path (E015 `cd -- /…/project`, E017 `cd -- /…/testlinuxbuddy`).
5. cd_child — a bareword dir (not an ancestor) → `cd -- X` (E001-E005). "open
   the X folder" → cd (E004).
6. cd_absolute — an explicit `/path`, captured WHOLE (E019
   "/mnt/c/Users" → `cd -- /mnt/c/Users`, fixing the Task-25-deferred truncation).
7. pwd — "where am i"/"current directory" → `pwd`.

**Bugs killed.** (1) Glob leak (E001): navigation extracts its own directory
target via `_NAV_GOTO_RE` — never the definite-reference glob — so "take me to
the logs folder" → `cd -- logs`, not `cd -- *.log`. (2) Stray `cd -` (E010/E016)
via the cd_previous guard.

**Disambiguation.** A target with a file extension (`open config.yaml`) is NOT a
directory → navigation returns None (stays a Task-20 abstain, not `cd`). "back
up the project" has no goto verb and no parent cue → not cd (archives' concern).
"windows …" requests defer to wsl. Narrowed `_WSL_CDRIVE_RE` to the "C drive"
WORD so an explicit `/mnt/c/Users` path falls through to cd_absolute; the
C-drive word rows (`cd /mnt/c`, `df -h /mnt/c`) still work.

**Tests.** `tests/test_navigation.py` (26, cwd-aware cases monkeypatch
`nlu.os.getcwd`), incl. the two collision tests. Full suite **232 passed**. All
E001-E023 maze-verified from their mapped cwds.

## 2026-11-08 — Task 27 (BATCH 25-27): intent & synonym fill + re-sweep

Closed the synonym/intent gaps the Task-24 sweep surfaced, across six domains.
New KB intents: `env_var` (echo $VAR), `cd_parent` already added in T26,
`disk_free` (df -h), `find_empty` (find -empty -type), `find_perms`
(find -perm), `find_recent` (find -mmin), `count_files` (find | wc -l),
`pip_list`, `extract_tar`/`extract_zip` (single-stage extract, no dir),
`open_vscode` (code .). Rows fixed (all verified in the maze):

- **env_var** E076-E078: "what's my PATH" → `echo $PATH`. The $VAR is a
  render.Raw so it stays UNQUOTED and the shell expands it. Enabled by two
  supporting changes: `_SAFE_RAW_RE` now allows `$ { }` (command substitution
  still can't form — `(` `)` backtick and space stay excluded), and the planner
  `_sub` no longer runs `_resolve_literal` on a Raw value (so `$HOME` stays
  `$HOME`, not the resolved path). The grep ALLCAPS heuristic now skips known
  env-var names so "what's my PATH" isn't grabbed as a literal grep for "PATH".
- **disk_space** E079/E081: whole-system "how much space is left" / "running out
  of disk" → `df -h` (a named folder still → `du`).
- **which / pip** E085: "which pip am i using" → `command -v pip` (checked in the
  python domain before the install-abstain, which matched a bare "pip").
- **pip_list** E134/E135 → `pip list`.
- **package vs CLI** E129/E130 (pandas/torch → importlib check_package);
  E132 "check if docker is there" → `command -v docker` (python now claims the
  non-package CLI case so filesystem's "is there" → check_exists can't steal it).
- **extract** E123/E124: "extract the tarball" → `tar -xzf *.tar.gz`; "unzip the
  archive" → `unzip *.zip` (exit 3). Removed downloads/desktop/documents from
  `_WSL_NESTED_RE` so they resolve instead of deferring.
- **create synonyms** E120/E122: "make a backup of the project" / "compress the
  results" → `tar -czf <name>.tar.gz …`.
- **wsl** E113/E114 (wslpath -w defaults path to "."), E116 (code .),
  E117/E118 (`cd /mnt/c/Users/$USER/Downloads`, $USER emitted unquoted as Raw).
- **filesystem** E094 "lock down the key file" → `chmod 600 FILE` (exit 3);
  E097/E098 world-writable/readable → `find . -perm -002/-004`.
- **processes** E100 "show my processes" → `ps aux`.
- **text** E065/E070: recursive grep where "the code"/"all files" are
  cwd-synonyms → path ".", not a literal subdir.
- **file_discovery** E039 "last hour" → `-mmin -60`; E043/E044 find_empty;
  E045/E046 count_files (`find … | wc -l`). file_inspection now defers a count
  when "files" (plural) is present (that's a file-count, not a line-count).

**Two VIEW-preview regressions caught in the sweep and fixed** (from Task 25's
view cue): "show me all the log files" was previewing (head) instead of listing
(E027), and "list the contents of the zip" was `head`-ing a binary zip (E126).
The VIEW block now defers when "files" (plural, a listing) or an archive glob is
the target.

**Re-sweep → data/eval/sweep_results_v2.csv** (139 rows, same harness as T24,
integrity PASS, canonical maze unchanged 2323 entries / sha 89ba5fc4…).
COMMAND **93 → 132**, ABSTAIN **46 → 7**. Row-by-row vs v1: **0 regressions**
(no COMMAND→ABSTAIN), 39 newly fixed, 24 commands improved. Correctness vs
expected_shape: ~118 exact-tool + ~11 review-but-correct (importlib, pgrep,
zipfile, $USER paths, python3) ≈ **~129/139 fully right** (target was 115-125).

**Remaining 7 abstains:** E138/E139 (pip install) are CORRECT abstains —
runtime network is invariant #1, the scenario's `pip install` expected_shape
violates it. E073 "sort this list" is a genuinely-vague residual (no file). The
other four (E048 "print the readme", E056 "tail the output", E060 "what is this
file", E066 "which lines mention warning") are near-misses NOT in Task 27's row
list — left as follow-ups per one-task-per-session. **Pre-existing non-Task-27
miss flagged:** E086 "what commands did i run recently" → `find -mtime -7`
instead of `history` ("recently" pulls it into find before workspace).

---

## 2026-11-09 — Task 28 (v1 cleanup: the last real residual) + re-sweep

The final rules-v1 pass. Four surgical fixes driven by named `sweep_results_v3`
rows, then a confirming re-sweep (`sweep_results_v4.csv`, v1/v2/v3 untouched).
Wrote a test per fixed row FIRST (`tests/test_v1_cleanup.py`), then the code.

**The four fixes (all in `nlu.py`):**

1. **E086 — history request hijacked by `find_recent`.** "what commands did i
   run recently" emitted `find . -type f -mtime -7`: the word "recently" pulled
   a command-history request into file discovery. Broadened `_WS_HISTORY_RE`
   (workspace, which already runs before file_discovery) to catch the command
   cues — "what commands did i/have i …", "commands did i run", "recent
   commands", "what have i run", and "commands i run". It now wins on the
   command cue even with "recent/recently" present. Did NOT broaden
   `find_recent`. → `history`.

2. **E048 — "print the readme" abstained.** Added `the readme` / bare `readme`
   → `README*` to the Task-22 definite-reference table (`_DEFINITE_GLOBS`). The
   existing file_inspection VIEW-preview path then picks it up:
   "print/show the readme" → `head -n 10 -- README*` (the head-preview form used
   for every other definite file ref — kept consistent rather than special-
   casing `cat`).

3. **E066 — "which lines mention warning" abstained.** It parsed to
   `search_in_file` with no path → `{path}` unresolved → PlanError (effectively
   an abstain). Added `_LINES_GREP_RE` ("which lines", "lines mentioning/with/
   containing/matching …") and, in `_parse_text_and_logs`, when a grep pattern
   is found but NO file is named, route those to a recursive grep in cwd —
   consistent with the no-target grep behaviour (E070/E071): `grep -RniF --
   warning .` (`-i` because "warning" is a case-word). A named file still routes
   to a single-file `search_in_file`.

4. **E117/E118 — Windows user folder used `$USER`.** `cd /mnt/c/Users/$USER/…`
   is wrong on WSL: the Linux `$USER` is almost never the Windows account name,
   so that path usually doesn't exist. **Decision: a glob over `$USER`.**
   Switched to `cd -- /mnt/c/Users/*/Downloads` (and `.../Documents`). The `*`
   is emitted unquoted (render.Raw) and the shell expands it to the real Windows
   user dir — one editable command beats a path that resolves to nothing.
   Updated the two tests that pinned the old `$USER` form (test_synonym_fill
   E117/E118, test_wsl_interop test_windows_user_folder_resolves).

**Re-sweep (`data/eval/sweep_results_v4.csv`):** COMMAND 132 → **134**, ABSTAIN
7 → **5**, integrity PASS (snapshot 06ecdaa3…, 2323 entries, MANIFEST unchanged).
Diffed the routing columns (lb_stdout/lb_stderr/exit_code/outcome) row-by-row
against v3: **exactly the 5 intended rows changed** (E048 + E066 abstain→command,
E086 wrong-command→`history`, E117/E118 `$USER`→`*`), every other row byte-
identical. 0 regressions.

**Remaining 5 abstains are the honest residual** (as predicted): E056 "tail the
output" and E060 "what is this file" (generic target, no file named), E073 "sort
this list" (genuinely vague), E138/E139 pip-install (runtime network =
invariant #1 — a correct abstain; the scenario's `pip install` expected_shape is
what's wrong, not us). These generic-reference residuals remain the documented
motivation for the Phase-3 intent model.

**Tests:** 281 pass (was 266; +15 in test_v1_cleanup.py). History does not steal
file-discovery rows (E036–E039 stay find; "last hour" stays find_recent), and
the README/lines-grep defaults don't break other definite-ref or grep rows.

**v1 is declared.** No LLM/network at runtime, typed argv the plan, one-slot-one-
element, nothing auto-executes, absolute paths — all invariants intact. Committed
(not pushed).

---

## 2026-11-09 — Task 29 (declare v1 — release artifacts)

Docs/release task, no code changes. Run after Task 28's re-sweep came back clean
(134/139, 0 regressions). Wrote the artifacts that make v1 a real, documented
release.

- **Version → 1.0.0** in `pyproject.toml`, and exposed `linuxbuddy.__version__ =
  "1.0.0"` in a newly-created `src/linuxbuddy/__init__.py` (the package had an
  empty init before).
- **README.md** rewritten from empty — the front door. Covers, in order: what it
  is (offline, no-LLM, rule-based, command-to-buffer-for-review), who it's for
  (the WSL2 data scientist handed Linux as a tool), how it works (request →
  intent/slot → typed argv plan → shlex-checked render → buffer), install
  (editable install or venv symlink to ~/.local/bin/lb; source the bash/zsh
  widget), usage (Ctrl-G replaces the line, editable, not run; tiered confirm by
  exit code 0/1/3), the containment safety model (LINUXBUDDY_MODE /
  LINUXBUDDY_MAZE_ROOT, one rendering path), the 10 domains, the evidence (139-
  scenario sweep, link to sweep_results_v4.csv, 281 tests, reproducible), and
  the honest known-limits → v2 motivation. Prose + short lists, no marketing.
- **CHANGELOG.md** new, Keep-a-Changelog style, single [1.0.0] entry.
- **STATUS.md** marks the milestone: v1.0.0 rules engine COMPLETE, final sweep
  number, the honest-5 residual, and the forward pointer to v2.

**Honesty note on numbers:** the task prompt's template quoted "266 tests" and
"~134/139" (written before Task 28). I used the ACTUAL current figures —
**281 tests**, **134/139 sweep (v4)** — per the report-faithfully rule, and
noted reproducibility precisely (routing byte-identical v2==v3; Task-28 cleanup
changed only its 5 intended rows v3→v4) rather than the template's shorthand.
The CHANGELOG tag link points at the real origin
(github.com/sambitmahapatra/LinuxBuddy), not a placeholder.

`pytest` still green (281). **Committed as `release: v1.0.0`. NOT tagged, NOT
pushed** — ready for the human to tag `v1.0.0` and push.

---

## 2026-11-09 — Task 30 (v2 Phase 1 spike: multi-turn 3-chain, NO model)

Started v2 on a new branch `v2-multiturn` (v1.0.0 line kept pristine). This is
the thin slice: prove the multi-turn *mechanic* with a session frame + rules-
based delta detection, rendering through the UNCHANGED v1 pipeline. **No
transformer/torch/embeddings** — the encoder is Phase 2.

**Note on docs:** `Prompts/30` says to read `ROADMAP_V2.md`; that file does not
exist in the repo. The frame shape is specified inline in the task, so I built to
that and did not invent a roadmap doc. Flagging for the human.

**The target chain works end-to-end** (verified as 3 *separate* `lb` processes in
one bash shell in the maze, sharing a PPID via the disk store):
```
find CSV files larger than 100MB
  -> find . -name '*.csv' -size +100M
only the ones modified yesterday
  -> find . -name '*.csv' -size +100M -daystart -mtime 1
show the biggest one
  -> find . -name '*.csv' -size +100M -daystart -mtime 1 -printf '%s\t%p\n' | sort -rn | head -1
```

**Frame shape** (`src/linuxbuddy/session.py`, `SessionFrame` dataclass):
`op, targets{}, filters{}, modifier, cwd, history[], updated_at, shell_id`.
`targets` holds `path` + the `-name` glob; `filters` holds `size` (+100M) and
`mtime`; `modifier` ∈ {None, max-by-size, count}. Methods: `merge(delta)` (accum-
ulates without clobbering), `to_command_plan()` (returns a plain v1 `Frame`),
`is_stale(ttl)`, `reset()`, plus `from_request()` / (de)serialization.

**Rendering reuses v1 whole.** Added a KB file `kb/commands/session.yaml`
(capability `session_compose`, intents `session_find` / `session_find_biggest` /
`session_count`) that uses the SAME contract as find.yaml — ordered
`optional_args` (name, size, mtime) + `pipe_argv` stages. `to_command_plan()`
emits a `Frame(session_*)` that the existing `planner.compile` → `render.to_shell`
→ `gate` handle unchanged. The `-printf '%s\t%p\n' | sort -rn | head -1` compose
is built via the Stages/pipe mechanism, never a hand-concatenated string.

**Store** (disk-backed, since each Ctrl-G is a fresh process): key = parent shell
PID (`os.getppid()`); file `<cache>/session_<PPID>.json`, `<cache>` =
`$LINUXBUDDY_CACHE_DIR` or `~/.cache/linuxbuddy`. **TTL = 10 min.** Cleared on the
reset words (start over / reset / never mind / forget it / scratch that) and on a
**cwd change** since the frame was written (a `cd` means fresh context). A
missing/corrupt file loads as empty (never raises).

**`-daystart` decision:** "modified yesterday" → `-daystart -mtime 1` (the whole
previous calendar day), "today" → `-daystart -mtime 0`. `-daystart` anchors
`-mtime` to midnight, matching the human calendar sense; plain `-mtime 1` means
24–48h ago relative to *now*, which is not "yesterday".

**Dialogue-act detector** (`classify`, rules): reset → self-contained-new (op
verb + a composable query: a type glob / size / day — beats refine/operate, so
"find all json files" mid-chain REPLACES the frame) → operate (biggest/largest →
max-by-size; count them / how many → count) → refine (a bare constraint, or a
leading only/just/and, with no new op verb; extracts size/day/ext as a delta and
merges, keeping existing slots) → new-if-composable → **fallback to the v1 single-
turn path** (the safe default; a non-find request like "what's my PATH" always
falls back). "new" is based on MY extractor, not v1's router — v1 sends "find CSV
files…" to grep (uppercase CSV), but the session composes it correctly.

**Opt-in, so single-turn is untouched.** Multi-turn engages only when
`LINUXBUDDY_SESSION` is set; the shell widgets (bash + zsh) now export it, so
Ctrl-G is session-aware while a direct `lb "..."` — including the 139-sweep — runs
the unchanged v1 body. CLI also gains `lb --frame` (print the frame) and
`lb --reset` (clear it).

**Tests:** `tests/test_session.py` — 21 tests: merge no-clobber, TTL/reset,
disk round-trip, cwd-reset, corrupt-file tolerance, the act classifier, and the
full 3-turn chain / reset-mid-chain / unrelated-new-replaces through the real
`cli.main`. Full suite **302 pass** (was 281).

**Regression:** re-ran the 139-scenario sweep single-turn → `sweep_results_v5.csv`.
Diffed routing (lb_stdout/stderr/exit_code/outcome) vs v4: **0 changes**, integrity
PASS. Single-turn behaviour is byte-identical.

Committed on `v2-multiturn` (not pushed).

## 2026-11-09 — Task 31 (v2 bugfix): key the session on an exported per-terminal id, not getppid()

**The bug (headline multi-turn feature was broken in the real widget).** An
interactive test showed the 3-turn chain did NOT accumulate: turn 2 ("only the
ones modified yesterday") came back as `find . -daystart -mtime 1`, dropping the
`-name '*.csv' -size +100M` from turn 1. Root cause: the Ctrl-G widget runs `lb`
inside a `$(lb …)` command substitution — a **fresh subshell with a new PID every
press** — and the store was keyed on `os.getppid()`. So each turn got a different
`session_<PPID>.json` and never saw the previous frame. The Task-30 tests passed
only because they drove three `lb` processes with a *shared* PPID, which the real
widget never provides.

**The fix.** Key the session on a stable, exported, per-terminal id.
- **Widgets** (`shell/linuxbuddy.bash` + `.zsh`): at source time (once per shell,
  top level), `export LINUXBUDDY_SESSION="lb-$$-$(date +%s%N)"`. `$$` is the
  interactive shell's PID (fixed for the terminal); the nanosecond stamp makes it
  unique across terminals. Being exported, every `lb` in that terminal — subshell,
  command substitution or direct — inherits the SAME value. (This also fixes the
  old `=1` value, which would have collided ALL terminals onto one session.)
- **`session.py`**: `store_key()` now returns the sanitized `$LINUXBUDDY_SESSION`
  when set (authoritative), falling back to `os.getppid()` only when it is absent
  (a direct `lb` with no widget). `_sanitize_key()` maps anything outside
  `[A-Za-z0-9._-]` to `_` and caps at 128 chars, so no `/` or space can reach the
  store path. `--frame`/`--reset` were already on the `store_key()` path, so they
  pick up the new keying for free.
- **Cleanup**: `save()` now calls `_cleanup_stale()` (best-effort, never raises),
  reaping `session_*.json` whose mtime is older than the TTL, so one dead file per
  closed terminal doesn't pile up in `~/.cache/linuxbuddy`.

TTL + reset-word + cwd-change reset behaviour unchanged.

**Tests first (the test that WOULD have caught this).** Added 6 tests to
`tests/test_session.py`:
- `test_env_keyed_persistence_across_subshells` — runs each `lb` as a forked child
  of a *fresh bash per call* (a two-statement `bash -c` body defeats bash's
  single-command exec optimization, so getppid genuinely differs per call) while
  sharing one `LINUXBUDDY_SESSION`. Asserts turn 2 accumulates. This FAILS under
  the old getppid keying (turn 2 would emit `find . -daystart -mtime 1`) and
  PASSES after the fix — it reproduces the real subshell scenario.
- `test_distinct_session_ids_do_not_cross_talk` — two different ids → no leakage
  (terminal B's day phrase starts its own query, carrying none of A's csv/size).
- `test_unset_session_still_single_turn` — unset env → single-turn, no file
  written.
- `test_store_key_prefers_env_and_sanitizes`, `..._falls_back_to_ppid_when_unset`,
  `test_cleanup_reaps_stale_session_files`.
Full suite: **308 pass** (was 302).

**Live re-verification (the real proof).** In one bash shell with the widget's
exported id, running `lb` through actual `$(lb …)` subshells inside the maze
(`testlinuxbuddy/project`):
- turn 1 `find CSV files larger than 100MB` → `find . -name '*.csv' -size +100M`
- turn 2 `only the ones modified yesterday` →
  `find . -name '*.csv' -size +100M -daystart -mtime 1`  ← **the dropped filters
  are now kept; this is the exact symptom that was broken.**
- turn 3 `show the biggest one` →
  `find . -name '*.csv' -size +100M -daystart -mtime 1 -printf '%s\t%p\n' | sort -rn | head -1`
- `lb --frame` grows across turns; `never mind` clears it (frame gone afterward).
Each `$(lb …)` is a distinct subshell PID, so this exercises exactly the path the
getppid keying broke.

**Regression.** Re-ran the 139-scenario single-turn sweep →
`data/eval/sweep_results_v6.csv`. COMMAND 134 / ABSTAIN 5, integrity PASS.
Routing diff (lb_stdout/stderr/exit_code/outcome) vs v5: **0 changes** — single-
turn is byte-identical (the fix only touches the session path, which single-turn
never enters).

**Note for the human.** `ROADMAP_V2.md` (referenced by this prompt's "read first")
still does not exist — built to the inline spec as in Task 30; worth writing as a
separate task. The widget keying was verified via `$(lb …)` subshells, which is
the mechanism Ctrl-G uses; a human pressing Ctrl-G in a fully interactive bash is
the one remaining manual confirmation (the Readline redraw), but the persistence
bug itself is now covered by an automated cross-process test.

Committed on `v2-multiturn` (not pushed).

## 2026-11-10 — Task 32: file-management intents (move/copy/delete/mkdir) + nested navigation

Two dogfooding gaps, all deterministic rules (no model). Branch `v2-multiturn`.

**Part A — new `file_management` domain (all destructive-tier).** New KB
`kb/commands/fileops.yaml` (`manage_files`): `move_file` → `mv -- {path} {dest}`
(risk write), `delete_file` → `rm -- {path}` (risk delete). copy and mkdir were
NOT re-added — a KB intent name must be unique across capabilities, so I REUSE
the existing `copy_file` (archive.yaml) and `make_dir` (workspace.yaml). New NLU
parser `_parse_file_management`, inserted in the router just before
`_parse_archives` (so move/delete/mkdir win first while copy still reaches the
archives branch). Everything renders through the unchanged v1 planner/render/gate
(shlex round-trip, `--` guard) and exits 3, maze-gated.

- **move/rename/put**: `_FM_MOVE_RE` captures `<verb> <src> <to|into|in> <dest>`
  off the original (case-preserving) text. The source must be a CONFIDENT target
  (quoted / slash path / `name.ext` / a typed definite-ref) or we fall through —
  a bare type-less word as a source is not confident, and invariant #6 says a
  destructive op with a less-than-confident parse must not emit. dest is cleaned
  to a single dir/file token.
- **copy**: generalized the existing archives copy branch to take a destination —
  `copy X to Y` → `cp -- X Y`; with no dest, the old `cp -- X X.bak` duplicate.
  (`_dest_after` finds a `to/into Y`.) The clipboard/windows/mnt guards are
  unchanged, so "copy to clipboard"/"copy … to windows" still defer to wsl.
- **delete**: `delete/remove/rm/get rid of/trash` + a resolvable target → `rm --`.
  Guarded so "remove the executable bit" stays chmod a-x, and "remove
  duplicates/blank lines" stay the text-domain ops (which also route first). A
  delete verb that owns the sentence but names no resolvable target ABSTAINS
  (`delete everything` / `remove them`) — never a guessed `rm`.
- **mkdir**: handle the noun-then-name phrasings the old `_WS_MKDIR_RE` missed —
  "make a folder X" / "create a directory X" / "new folder X" → the existing
  `make_dir`. name-then-noun ("make a logs folder") still falls through to
  workspace. Yields "project/workspace" phrasing to workspace's setup_project.

**Definite-ref additions (Task-22 table):** "the OLD logs" now resolves (allowed
an optional adjective: `the (old )?logs?` → `*.log`); "the image/picture/photo" →
`*.{jpg,png}`, a brace-expansion glob emitted as a trusted Raw.

**Delete-safety decision (documented in fileops.yaml):** plain `rm -- X`, NO `-f`
and NO `-i`. `-f` would silently swallow the one natural signal we keep (a file
that isn't there should error, not be forced past); `-i` is redundant for a tool
whose entire model is review-before-Enter. The exit-3 warning + maze gate +
manual Enter are the safety net.

**Planner fix (needed by the image glob):** the unresolved-`{placeholder}` guard
now SKIPS `Raw` elements. `*.{jpg,png}` is a legitimate brace-expansion glob, but
`_PLACEHOLDER_RE` read `{jpg,png}` as an unresolved template slot and raised. A
genuinely-unresolved `{slot}` is always a plain (non-Raw) str, so skipping Raw is
safe — render's `_SAFE_RAW_RE` already permits `{ } ,`.

**Part B — nested navigation ("X inside Y").** Added to `_parse_navigation`
(before the plain goto): `_NAV_NESTED_RE` matches `<goto-verb> X <inside|within|
under|in> Y`.
- Y an ANCESTOR of cwd → resolve Y's absolute path + X → `cd -- <Yabs>/X`.
- Y a CHILD dir of cwd and X under it → relative `cd -- Y/X` (checked with
  os.path.isdir).
- else → abstain (a fuzzy elsewhere-on-disk Y is a future find-based resolver;
  don't guess).
- **Repeated-segment disambiguation (found by the live test):** from
  `~/linuxbuddy/src/linuxbuddy`, "test_02 inside linuxbuddy" must mean the OUTER
  repo root (test_02 lives there), but a plain nearest-ancestor (`max(idx)`)
  picked the inner `linuxbuddy`. Fixed: among repeated Y occurrences, prefer the
  one whose `<anc>/X` actually exists, else nearest. Single-occurrence behavior
  (the common case) is unchanged.

**Tests (first):** `tests/test_file_ops_nested_nav.py`, 32 tests — a render +
exit-3 case per intent, the containment gate (refused outside the maze / emitted
inside), definite-ref cases ("move the image to photos", "remove the old logs"),
the unclear-target abstains, the chmod-not-rm guard, and Part B (ancestor
absolute, the "in" connector, unresolvable abstains, child relative, existing nav
unregressed). Full suite **340 pass** (was 308).

**Regression:** 139-scenario single-turn sweep → `sweep_results_v7.csv`. COMMAND
134 / ABSTAIN 5, integrity PASS, **0 routing diffs vs v6** (the new intents
aren't in the 139; the router/definite-ref changes shifted nothing existing).
Multi-turn chain (Task 31) still accumulates — verified live and via the full
suite.

**Manual (maze):** move/copy/delete/mkdir inside the maze emit + warn (exit 3);
the same outside are refused (exit 1). "go to test_02 inside linuxbuddy" from
`src/linuxbuddy` → `cd -- /home/sambi/linuxbuddy/test_02`.

**Note:** the optional ~10 sweep-coverage rows for the new intents were NOT added
(prompt marks them optional) — a good small follow-up so future sweeps regress
these too. `ROADMAP_V2.md` still absent (built to the inline spec).

Committed on `v2-multiturn` (not pushed).

## 2026-11-10 — Task 33: file-management verbs win over `find` in the SESSION path

Bugfix on `v2-multiturn`. The four file-ops from Task 32 emitted `find …`
(exit 0) instead of `mv`/`rm`/`cp` (exit 3) — but ONLY in the real widget.

**Raw results first (per CLAUDE.md).** Probed before touching code:
`nlu.parse("move report.csv to archive")` already returns `move_file`, and the
single-turn CLI already emits `mv -- report.csv archive` (exit 3). The bug
reproduces only when `LINUXBUDDY_SESSION` is set — i.e. the multi-turn path the
Ctrl-G widget uses, which the owner's bash exports.

**So the prompt's stated root cause was wrong.** It said `file_management` is
checked AFTER `file_discovery` in the router. It isn't — Task 32 already put
`_parse_file_management` before `_parse_file_discovery`, and single-turn routing
is correct. The real culprit is `session.classify()`: its `_composable()` test
treats ANY request carrying a filename extension as a new `find`-by-type query,
so "delete old.log" → act `new` → `SessionFrame.from_request` → `find . -name
'*.log'`. `mkdir "photos"` survived only because it has no extension — but
`"make a folder logs"` was ALSO hijacked ("logs" reads as `.log`), a case the
prompt's probe missed.

**Fix (session.py).** A new `_FILEOP_LEAD_RE` matches a file-management verb at
the HEAD of the request — move/copy/rename/delete/remove/trash/put/get rid of,
bare mv/cp/rm, "make a copy", and the mkdir phrasings (make/create/new/add a
folder|dir|directory). When it matches, `classify()` returns `("fallback", {})`
BEFORE the composable-find checks and before operate/refine — so the v1
single-turn path handles it (routing move/copy/delete/rename to file_management,
and "remove the executable bit"/"remove duplicate lines" to chmod/text). It sits
after the reset check so "never mind, delete X" still resets. Discovery verbs
(find/list/locate/where/how many/recently modified/biggest) are disjoint from
this set, so discovery is untouched. Anchored at the head so "find files to
move" stays a find.

**Test-hygiene fix (tests/conftest.py).** An autouse fixture unsets
`LINUXBUDDY_SESSION` for every test by default; session tests opt back in via
`monkeypatch.setenv` (which runs after it). Without this, running `pytest` from
the owner's widget-active bash routed the single-turn CLI tests through the
session path and failed 6 of them spuriously — the SAME environment that hid
this bug. The suite is now deterministic with or without the env var.

**Tests (written first, RED before the fix).** `tests/test_session_fileops_routing.py`,
28 tests: classify returns `fallback` for file-op leads both with and without an
active frame (so a mid-chain "delete old.log" is a fresh destructive op, not a
refine); discovery stays `new`; refine/operate still fire with a frame;
end-to-end through the real `cli.main` in session mode the four rows emit the
right destructive command at exit 3, mkdir (photos AND logs) and backup_copy
work, a file-op is refused outside the maze (exit 1, empty stdout); and the
discovery control + 3-turn chain still accumulate. 15 of the 28 failed before
the fix, all green after. Full suite **368 pass** (was 340), identical with and
without `LINUXBUDDY_SESSION` set.

**Regression — the 139-row single-turn sweep: 0 routing diffs vs v7.** Re-ran lb
single-turn over all 139 scenarios (LINUXBUDDY_SESSION unset) and diffed
lb_stdout/lb_stderr/exit_code/outcome against `sweep_results_v7.csv`: byte-
identical (the fix only touches the session path).

**Manual re-verify (real `lb`, widget session id set, in the maze).** `move
report.csv to archive` → `mv -- report.csv archive` (3); `delete old.log` → `rm
-- old.log` (3); `copy requirements.txt to archives` → `cp -- requirements.txt
archives` (3); `rename a.txt to b.txt` → `mv -- a.txt b.txt` (3); `make a folder
photos|logs` → `mkdir -p -- …` (3); `make a copy of config.yaml` → `cp --
config.yaml config.yaml.bak` (3). Discovery in fresh sessions still routes to
`find` (exit 0). `delete something.txt` outside the maze → refused (exit 1).

**Optional sweep rows — added, with an honest caveat.** Appended E140–E147 to
`sweep_scenarios.csv` (6 file-ops + mkdir + a discovery control) and regenerated
`data/eval/sweep_results_v8.csv` (147 rows, COMMAND 142 / ABSTAIN 5; the first
139 copied verbatim from v7 since routing is identical; the new destructive rows
are `skipped-destructive-unsafe` in the exec phase so the maze isn't mutated).
**Caveat:** these are SINGLE-TURN rows and would NOT have caught this bug —
single-turn was never broken. The actual regression guard for this class is the
new session test file. The sweep rows are still worth it as the single-turn
coverage of the Task-32 intents that Task 32 flagged as missing.

Committed on `v2-multiturn` (not pushed).

## 2026-11-10 — Task 34: copy synonyms + no-destination copy (last manual synonym patch)

Small synonym fix on `v2-multiturn`. "create a copy of X" / "duplicate X" /
"make a duplicate of X" / "back up X.ext" were not recognized as copy intents and
fell through to the greedy find/grep fallback.

**Raw results first.** Probed before editing: `create a copy of sales.csv` →
`find . -name sales.csv`; `back up config.yaml` → `find … config.yaml`;
`create a copy of MANIFEST.txt in this folder` → `grep -nF -- MANIFEST
MANIFEST.txt`. The grep theft is specific to an ALL-CAPS filename stem
(`_ALLCAPS_RE` turns "MANIFEST" into a grep pattern) — that's why sales.csv /
config.yaml fell to `find` but MANIFEST.txt was grabbed by `_parse_text_and_logs`
(which runs before archives). `duplicate report.csv` already rendered `cp` in
single-turn but was classified `new` (hijacked to find) in the session path.

**Fix — three coordinated edits so both paths agree.**
1. `_ARC_COPY_RE` (nlu): added `(?:make|create) (a|an)? (copy|duplicate) of X`,
   and `back up X.ext` (single file only — a bare `[\w./-]+\.\w+`, so "back up
   the project" has no extension and still falls through to `create_archive`).
   Kept the existing bare `duplicate X` and `copy X.ext` alts and the
   clipboard/windows/mnt guard.
2. `_parse_text_and_logs` (nlu): after the distinct/sort checks AND only once a
   grep pattern exists, bail (`return None`) when `_ARC_COPY_RE` matches — so the
   MANIFEST all-caps case defers to the copy parser. Placed AFTER distinct/sort
   so "remove duplicate lines" stays `unique_lines` (the first placement, at the
   top, regressed E075 — caught by the suite, moved down).
3. `_FILEOP_LEAD_RE` (session): added `duplicate`, `back up`, and
   `(make|create) (a|an)? (copy|duplicate)` as lead verbs, so the session path
   also falls back to single-turn for these (which now renders `cp`).

No-destination copy was already handled: the copy call site defaults `dest` to
`src + ".bak"` when there's no "to/into Y", and "in this folder"/"here" don't
match the `to|into` destination regex, so they correctly yield the `.bak` copy.
All copy variants are writes → exit 3, maze-gated (unchanged pipeline).

**Tests (written first, RED before the fix).** `tests/test_copy_synonyms.py`,
21 tests: the new cues render `cp` single-turn; "make a copy of X" and "copy X to
Y" unchanged; discovery / folder-backup (tar) / dedup unregressed; the session
`classify` falls back for every copy-synonym lead (with and without a frame);
end-to-end exit-3 in session mode for the three evidence rows; refused outside
the maze. 12 of 21 were RED before the fix.

**Results.** Full suite **389 pass** (was 368; +21), identical with and without
`LINUXBUDDY_SESSION`. 147-row sweep (the 139 + Task-33's E140–E147): **0 routing
diffs vs v8** — no existing routing shifted (no new results file needed).

**Manual (real `lb`, widget session, in maze).** All three evidence rows + every
copy synonym → `cp -- X X.bak` (or `cp -- X Y`) at exit 3; `copy a.txt to b.txt`
→ `cp -- a.txt b.txt`; `find all csv files` → `find` (0); `back up the project` →
`tar -czf project.tar.gz -C . -- project` (3, folder archive); `remove duplicate
lines from notes.txt` → `sort -u -- notes.txt` (0, not hijacked to copy);
`create a copy of sales.csv` outside the maze → refused (exit 1).

**This is the last hand-written synonym patch.** The remaining phrasing tail
(unseen verbs/paraphrases) is deliberately NOT chased with more rules — it is the
Phase-2 intent-encoder's job (the honest-5 residual + the long synonym tail are
its motivation). Future "the tool didn't understand X" reports of this shape
should be logged as encoder training signal, not patched individually.

Committed on `v2-multiturn` (not pushed).

## 2026-11-10 — Task 35: autonomous adaptive stress test (testing only, no src changes)

Built `tests/stress_test.py` — a 5-agent stress harness that generates its own
test cases and adapts, rather than iterating a fixed list. **No LinuxBuddy source
was touched** (testing only, per the task). One run = 170 tests; outputs
(`stress_test_results.csv`, `stress_test_report.md`) are gitignored as ephemeral.

**The agents.** (1) Environment Builder grows a 35-item tricky tree under
`testlinuxbuddy/stress/` — 5-level nesting, spaces in dir+file names, ALL-CAPS,
dotfiles, a symlink, a real `tar.gz`, a ~2MB file, similar-name families
(report / report_final / report_backup) — each item documented with the hazard it
probes. (2) Explorer runs 87 single-turn requests across every domain, several
phrasings per operation, each stamped with the expectation a reasonable user
holds (read⇒0, destructive⇒3, vague/nonsense⇒abstain). (3) Adversary (51 probes)
reads the Explorer's *actual* failures and computes its probes from them —
rewording abstained reads to map the boundary, running synonym ladders, and a
gate-leak battery outside the maze. (4) Session Tester runs 9 multi-turn chains
(32 rows) verifying accumulation, reset, new-replaces, isolation, off-topic
resilience, and the vague-size no-op. (5) Judge analyses everything and writes the
report, separating bugs-to-fix from Phase-2-encoder territory.

**Calibration first (the honest part).** Before writing the judge I probed real
`lb` across domains so expectations match reality, and caught myself: my first
judge flagged `erase scratch.tmp → find …` as "DANGER: destructive flagged
read-only." That was backwards — an *unrecognised* destructive verb safely
**degrades to a read-only find**; it is a synonym gap, not a risk. Fixed the judge
so WRONG_EXIT fires only when a genuinely destructive-family command (`rm`/`mv`/…)
is emitted at rc=0. Also fixed two false positives where my expectation was wrong,
not lb's output: `remove duplicate lines → sort -u` and session `how many →
find … | wc -l` are both correct.

**Results (170 tests, 84.1% behaved as a reasonable user expects, 0 gate leaks).**
- **Bugs to fix (5, all routing/rendering, all read-only so low-risk):**
  `where are the python scripts → command -v python3` (python-installed check
  steals it); `list all python files → ls -la` (list_all beats find_by_type);
  `show the permissions of notes.txt → head -n 10` and `show me the stats … →
  head` (inspection verbs misroute to preview); `check the syntax of main.py →
  find` (py_syntax phrasing not recognised).
- **Rules ceiling / Phase-2 corpus (22):** abstained reads
  (`what processes are running`, `list everything here`,
  `where are the spreadsheets`, `what changed in the last day`, …) plus
  unrecognised destructive verbs that degraded safely to a find
  (`erase/nuke/wipe/discard/del/throw away`, `clone/replicate`, `set up a
  folder`). The delete-synonym boundary: recognised = delete/remove/get rid
  of/trash; not = erase/nuke/wipe/discard/del/throw away.
- **Session: 32/32, all 9 chain properties held** — accumulation, reset,
  isolation (two `$LINUXBUDDY_SESSION` ids don't interfere), off-topic turns
  leave the frame intact and refinable. `delete them` coreference correctly
  abstains (invariant 6), which the harness scores as the safe outcome.
- **Containment:** 10/10 destructive ops refused outside the maze. **New
  observation worth a look:** `delete ../../../etc/hosts` run *inside* the maze
  emits `rm -- ../../../etc/hosts` at rc=3 — the gate is cwd-based by design and
  does not inspect the *target*, so a `..` target escapes the maze. Not a breach
  of the current gate contract (and `lb` never executes), but a real hardening
  item for prod mode. Flagged in the report, not "fixed" (would change a settled
  design rule — for the human to decide).

The two "bug" classes that look like misroutes (#3/#5 above) are arguably
synonym gaps that happen to emit a wrong read rather than abstain; the report
lists them under routing because lb emitted a *specific* wrong command, which is
more actionable than a silent abstain.

Full existing suite still **389 pass** (unchanged — no src edits). Committed on
`v2-multiturn` (not pushed); output files gitignored.

## 2026-11-11 — Task 36: v2 Phase 0 — training-data generation (data only, no src/KB changes)

Built the labeled corpus the Phase-1 intent encoder will train on. **No LinuxBuddy
source, rules, or KB contents were modified** — added a new `src/linuxbuddy/ml/`
package (generator + label builder) and `data/` artifacts. No torch/transformers.
Generator is reproducible: `python -I -m linuxbuddy.ml.make_dataset` (fixed seed
20261111); `tests/test_data.py` green (12 tests); full suite **401 pass** (389 + 12).

**Part A — the frozen label space (`data/label_space.json`).** Enumerated intents
straight from `load_kb()` (the planner's `_lookup` space): **85 intent ids**, plain
globally-unique KB keys (NOT domain-dotted — e.g. `copy_file`, not
`file_management.copy`; the task's dotted example was illustrative). Plus 5
dialogue acts (new/refine/operate/reset/fallback, exactly what `session.classify`
returns) and `_ABSTAIN`. Carried an intent→domain map for stratification.

**The drift guard fired — reported, reconciled with sign-off.** `sweep_scenarios.csv`
labels rows in a different, coarser vocabulary (59 labels) than the KB; **57 of 59
don't match by name**. Per the task I STOPPED and reported rather than silently
remapping. The owner approved reconciling, with the governing rule: *a row's label
= the KB intent id that actually FIRES for that utterance at runtime*. So I built
`data/sweep_intent_map.json` by **running `lb`** on the phrasings, not by name —
e.g. `cat`→`preview_head` (verified: "show me config.yaml" → `head -n 10`; there is
no cat/view intent in the KB, confirmed by grep + `nlu.py:662`), `cd_*`→`goto`/
`go_back`, per-row `kill`→`kill_pid`/`kill_process`, `resource`→`top_by_*`,
`extract`→`extract_tar`/`extract_zip`. E110 "stop whatever's on port 8000" fires
`ss -ltnp` (process_on_port, a read) — labeled by what fires, noted as a divergence
(no kill-by-port intent exists). The 5 sweep ABSTAIN rows (honest-5: E056/E060/E073/
E138/E139) → `_ABSTAIN`. The reconciliation is an auditable committed file; the
regression floor is untouched (the 147-row sweep compares emitted commands, not
intent labels).

**Part B — single-turn (204 raw).** Sources: `sweep` (147, reconciled), `stress_gap`
(27, hand-labeled from the Task-35 gaps — the misrouted/abstained reads + the
destructive synonyms labeled with the intent they SHOULD hit: clone→`copy_file`,
erase→`delete_file`, "set up a folder"→`make_dir`), `stress_abstain` (12) +
`hand_abstain` (18) → `_ABSTAIN`. Raw abstain 17.2%.

**Part C — multi-turn (49 turns, 20 chains).** ROADMAP_V2.md does not exist (noted
in STATUS), so the golden chain C001 is authored directly; 8 chains reconstructed
from the Task-35 session run; 11 hand-authored (HC*) to top up thin acts (reset/
operate/new-replaces/cross-domain), since the stress agents under-explored the
multi-turn edge. Acts imbalanced by design: new 23 / operate 9 / refine 7 / reset 6
/ fallback 4 — Phase-2 should weight the loss. `prev_frame` accumulates per turn.

**Part D — augmentation (train-only, group-level, seeded).** Deterministic bank in
`data/synonyms.json` (synonym sub, filler/politeness, word dropout, filename/ext
swap — the last never on `_ABSTAIN`). Cap ≤4 per positive seed, ≤2 per abstain
(filler/dropout only). Applied AFTER the split to train seeds only, so no variant
of a val example can leak.

**Part E — split + files.** Group-level 80/20 stratified by intent (seeds, then
their augmentations, stay on one side; whole chains for mt). Final single-turn
**train 688 / val 55** (`_ABSTAIN` 12.2% / 12.7% — in the 8–20% band); mt **train 40
/ val 9 turns**. Files: `train.jsonl`, `val.jsonl`, `train_mt.jsonl`, `val_mt.jsonl`,
the two `*.raw.jsonl`, `label_space.json`, `sweep_intent_map.json`, `synonyms.json`,
`DATA_CARD.md`.

**Coverage reality (for Phase-1 watchlist).** **27 of 85 intents have ZERO
single-turn data** (the sweep+stress simply never exercised them — e.g.
`python_version`, `who_am_i`, `which_shell`, `show_size`, `show_owner`,
`find_process`, `find_smallest`, extract/archive reads, the `session_*` trio which
the mt set covers instead). The encoder cannot be a fallback for these until the
corpus grows; the rules still handle them. 45 more intents have <3 raw train seeds.
Both lists are in the DATA_CARD for the confusion matrix. Showed the owner the class
balance before Phase-1 commits to the encoder (their requested gate).

Committed on `v2-multiturn` (not pushed). **data/ files ARE tracked** (training
input, belongs in git) — unlike the ephemeral stress outputs.

## 2026-11-11 — Task 37: v2 Phase 1 spike — zero-shot bi-encoder (measurement only)

Measured how far a *pretrained* MiniLM gets with good descriptions, before
spending any GPU-minute. **No fine-tuning, no GPU, no rules/router/planner/KB
changes.** The rules engine stays pure-stdlib: all ML lives in an isolated
`.venv-ml` (uv-managed Python 3.12 + CPU torch), so `lb`'s Python-3.14 venv is
untouched. Full suite **402 pass + 4 skipped** in the main venv (the 4 model tests
skip where sentence-transformers isn't installed; all 5 pass in `.venv-ml`).

**VERDICT: NEEDS FINE-TUNING.** Operating point T\*=0.275 (desc-only anchors, the
knee of gap×nonsense). The embedding space is roughly right but not wireable as-is.

**Headline numbers (honest, after removing anchor leakage — see below):**
- Gap set (the 27 stress-test rules-ceiling phrasings): **23/27 (85%) recovered at
  top-1** at T\*. The 4 misses are neighbouring-intent confusions
  (find_by_type↔run_script/list_all, make_dir↔setup_project), not weak descriptions.
- Val ceiling: **top-1 58%, top-3 77%** (48 covered rows). Top-3 ≫ top-1 ⇒ the
  space groups correctly but can't separate at rank 1.
- Nonsense abstain: **69% correct (31% false-positive)** at T\*. **Nonsense is NOT
  separable by an absolute cosine threshold** — FP only drops below ~15% near
  T=0.55, where gap recovery collapses to ~26%. The top1−top2 **margin did not
  help** (best margin = 0). This abstain softness is the main blocker.

**Why NEEDS FINE-TUNING (not GOOD ENOUGH, not just better descriptions):** both
failure modes — soft top-1 and non-separable nonsense — are concentrated between
*adjacent* intents, exactly what a contrastive fine-tune on the Task-36 labeled
pairs pulls apart. More description tuning hits diminishing returns (the misses are
semantic neighbours, not vocabulary gaps).

**An integrity catch worth recording.** My first run looked great (gap 96%, val
77%) — because several `examples:` anchors in intent_descriptions.yaml were
*verbatim copies of the gap/val test utterances* (erase scratch.tmp, "list
everything here", etc.): teaching-to-the-test. I added a leakage check (16 exact
collisions found), replaced every colliding anchor with a non-test paraphrase
(synonyms stay in the *descriptions*, which is the legitimate place to bank them),
and re-ran. The honest numbers above are post-fix. Lesson banked for Phase-3.

**Description strategy:** compared desc-only vs desc+examples. Post-leak-fix,
**desc-only wins on gap recovery** (85% vs 59%); desc+ex edges val top-1 (65% vs
58%). Report keeps both.

**Deliverables:** `kb/intent_descriptions.yaml` (all 85 intents, durable reusable
artifact — descriptions fold in the synonyms the rules miss: erase/nuke/wipe→delete,
clone/replicate→copy), `src/linuxbuddy/ml/zeroshot.py` (pure matcher, abstain by
threshold+margin), `src/linuxbuddy/ml/eval_zeroshot.py` (harness: val/gap/nonsense +
threshold & margin sweep), `tests/test_zeroshot.py`, `requirements-ml.txt` (pinned:
sentence-transformers 5.7.0, torch 2.15.0+cpu), `zeroshot_spike_report.md`. The
27 zero-data intents all have descriptions (reachable zero-shot); none appear in
the 55-row val set, so they're not directly measured — kept description-served,
to be judged by a broader Phase-1 eval / the targeted collection pass.

**Next (if approved):** contrastive fine-tune the bi-encoder on the Task-36 pairs
(the 688 train rows / augmented set), re-run THIS harness to measure the lift,
then wire as the rules fallback. `eval_cache.jsonl` + `.venv-ml/` are gitignored
(ephemeral); the descriptions file, report, code and tests are tracked.

Committed on `v2-multiturn` (not pushed).

## 2026-11-11 — Task 38: v2 Phase 1 — base-model bake-off + contrastive fine-tune

The Siamese step (rubric concept #2). Still measurement + model work only: **no
rules/router/planner/KB changes**, nothing wired into `lb`. All ML in `.venv-ml`.
Suite **403 pass + 8 skipped** (main venv; the ML tests run in `.venv-ml`, 10 pass).

**VERDICT: WIREABLE.** The fine-tuned MiniLM-L6 clears every bar. Base = Part-A
winner `all-MiniLM-L6-v2`; abstain = a train-fit threshold (T\*=0.55), with the
logistic gate (option b) equivalent.

**Part A — bake-off (5 bases, zero-shot, each with its documented input convention;
`bakeoff_report.md`).** No base separated nonsense zero-shot: best feasible was
MiniLM-L6 at **FP 31% @ gap 85%**; MiniLM-L12 and bge-small similar; gte-small and
e5-small-v2 could not even be thresholded (cosines compressed high → FP ~100%).
Winner by the task's criterion (lowest FP at gap≥80%, tie val top-1) =
**`all-MiniLM-L6-v2`** — also the smallest/fastest for CPU deployment. bge-small had
the best top-3 ceiling (85%), noted as runner-up. → fine-tuning warranted.

**Part B — fine-tune (`models/ft-minilm-l6/`, gitignored).** MultipleNegativesRanking
Loss (in-batch negatives = the Siamese contrastive objective) on utterance↔description
+ utterance↔utterance pairs. **seed 42, 3 epochs, lr 2e-5, batch 32** (2 epochs left
val top-1 at 67%, under the bar; 3 crossed it — selected on val). Abstain = **option
(b)**: a balanced logistic gate on `[max_sim, margin]`. Justification: MNRL contracts
the space (nonsense can still score high in absolute cosine), but after fine-tuning
the *margin* becomes discriminative, so a 2-feature gate (or, it turns out, a plain
train-fit threshold) separates abstain — the Task-37 blocker is gone.

**GPU:** attempted a CUDA build for the RTX 3050, but torch 2.15.0 has no wheel on the
pytorch cu124/cu126 indexes for this env; per the task's "don't rabbit-hole" guidance,
trained on **CPU** (~1041 pairs × 3 epochs, under a minute). Deployment is CPU
inference regardless.

**Part C — three states, all on held-out data (`finetune_report.md`):**
| state | gap rec. | nonsense FP | val top-1 | val top-3 |
|---|---|---|---|---|
| MiniLM-L6 zero-shot | 19% | 0% | 26% | 76% |
| fine-tuned + threshold | 93% | 3% | 72% | 89% |
| fine-tuned + gate | 93% | 3% | 72% | 89% |

Read the zero-shot row honestly: with a train-fit threshold forced to low FP, recovery
*collapses* (gap 19%, val 26%) — the zero-shot space simply can't be thresholded,
which is why fine-tuning was needed. Fine-tuned clears FP<15% @ gap≥80%, val top-1≥70%.

**Zero-data guardrail (12 untrained intents, 24 utterances, tracked probe):** top-3
**88% → 96%** (top-1 62% → 71%) — the zero-data tail was NOT degraded; it improved.

**Two integrity catches, both fixed before reporting:**
1. The Task-36 split had salted `train.jsonl` with **21 of the 27 gap phrasings** (+2
   val rows). Training on them would make "gap recovery" a training-set number.
   `build_pairs()` and the gate now exclude all gap/val utterances via
   `heldout_texts()`; a test asserts it. Gap recovery stayed **93% even held-out** —
   fine-tuning genuinely generalizes to the rules-ceiling phrasings.
2. Nonsense FP is measured on a fresh, hand-authored nonsense probe + the 7 held-out
   val abstains (clean for all three states, incl. the gate); threshold operating
   points are fit on TRAIN, not on the eval nonsense set — so all three states are
   measured identically. (A first pass had tuned T on the eval set; corrected.)

**Determinism:** two independent CPU train+eval runs gave byte-identical eval numbers
(seed 42).

**Deliverables:** `ml/bakeoff.py`, `ml/finetune.py`, `ml/finetune_eval.py`,
`tests/test_finetune.py`, `data/zero_data_probe.jsonl`, `data/nonsense_probe.jsonl`,
`bakeoff_report.md`, `finetune_report.md`; `kb/intent_descriptions.yaml`/`zeroshot.py`
gained per-model input conventions. `requirements-ml.txt` += accelerate/datasets/
scikit-learn. Checkpoint `models/` gitignored (regenerates from script + seed + data).

**Next (if approved):** wire the fine-tuned encoder as the rules fallback in `lb`
(the WIREABLE next task) — encoder runs only after the rules abstain; threshold
T\*=0.55 as the abstain gate; intent-only (slots stay rule-based).

Committed on `v2-multiturn` (not pushed).

## 2026-11-11 — Task 39: wire the fine-tuned encoder as the rules fallback (hybrid)

First task to touch `lb`'s runtime. Single-turn, intent-only. Main suite **408
pass + 11 skipped**; `.venv-ml` **18 pass**. All five guardrails verified.

**The seam (one point):** `cli._run_single_turn`, where the rules return `frame is
None`. Refactored the compile→gate→render tail into `_emit_frame(frame, info)` so a
rule frame and an encoder frame take the IDENTICAL safe pipeline. On abstain,
`hybrid.classify_fallback(request)` is consulted; if it returns a frame, it flows
through `_emit_frame`, else the normal v1 abstain prints. The session/multi-turn
path is untouched (it already delegates to `_run_single_turn` for its fallback).

**Guardrail results:**
1. **Rules first / 0 regressions.** `tests/test_hybrid.py` runs the 147-row sweep
   encoder-on vs -off: **0 diffs on every rule-handled row** (rc≠1). The encoder is
   only consulted on true abstains, so rule-handled/misrouted rows can't change.
2. **Intent, not command.** The encoder returns an intent id; a new rule-reusing
   slot filler (`hybrid.fill_slots`, reusing nlu's own `_detect_*` detectors) builds
   the Frame; the EXISTING planner/renderer/gate build and vet the command. The
   security boundary did not move.
3. **Read/destructive asymmetry (the key safety call).** Two thresholds in
   `ml_config.yaml`: `t_read=0.55` (= Task-38 T\*), `t_destructive=0.68` +
   `margin_min=0.05`. A destructive intent below its bar (or with no extractable
   concrete target) abstains honestly — never a guessed rm/mv/chmod. **Safety metric:
   destructive-on-nonsense = 0 / 22** (and 0/22 nonsense fired ANY command). Also
   applied invariant #6 in the filler: a find_* whose defining slot (ext/days/size/
   name) isn't extracted abstains rather than emit a match-everything `find .`.
4. **Graceful degradation.** Missing checkpoint/deps or `LINUXBUDDY_ENCODER=0` →
   pure v1 (one-line stderr note at most, no traceback). In the main Python-3.14
   venv the encoder is simply absent, which the whole suite exercises.
5. **Off the fast path.** `hybrid`'s top-level imports are stdlib-only; torch/ST are
   lazy-imported ONLY on the abstain path (a subprocess test asserts `torch` not in
   `sys.modules` after a rule hit). The 85 description embeddings are disk-cached
   (`IntentIndex.cached` → `models/ft-minilm-l6/index_desc.npz`).

**Confidence surfacing:** when a command came from the encoder, a one-line stderr
hint ("interpreted (language model) — review…", a stronger line for destructive).
stdout stays EXACTLY the command, so the widget buffer contract is unchanged.

**End-to-end eval (`hybrid_eval_report.md`, through real `lb`):**
- Coverage: of 14 rules-abstain probe phrasings (gap set + honest-5), the hybrid
  resolves **10** to meaningful bounded commands (ls -la, ps aux, `find . -name
  '*.csv'`, `find . -type f -mtime -1`), correctly leaving 4 abstained (honest-5 /
  match-everything).
- Safety: 0 destructive on nonsense; gate integrity intact (encoder-chosen
  destructive refused outside the maze, exit 3 inside — a test asserts both).
- **Latency: fast path ~0.12 s (v1, no ML import); cold abstain path ~10 s** per
  fresh process (torch import + model load dominate; the embedding cache can't help
  per-process). **Too slow for a snappy widget on abstain** — flagged; recommended
  follow-up is a resident helper (load once, serve many), explicitly NOT built here.

**Config/kill switch:** `ml_config.yaml` (`encoder.enabled/model_path/t_read/
t_destructive/margin_min`); `LINUXBUDDY_ENCODER=0` forces pure-rules.

**Housekeeping:** gitignored the stray 126MB `test_02/` and Windows `*:Zone.Identifier`
files; committed the `Prompts/31–37` task specs (38/39 were never saved as files).

**Milestone:** this is a good checkpoint. Committed on `v2-multiturn`.

## 2026-11-11 — Task 40: cut abstain-path latency (ONNX, torch-free hot path)

Pure performance task — same behaviour, much faster cold start. **No intent
decision, threshold, gate, rule, or router change.** Main suite **409 pass + 13
skipped**; `.venv-ml` **21 pass**. All five Task-39 guardrails re-verified.

**Part A — profile first (know the enemy).** Broke down the ~10 s cold abstain
path on the WSL box:

| stage | cost |
|---|---|
| import numpy | 165 ms |
| import torch | 1248 ms |
| import transformers | 1140 ms |
| **import sentence_transformers** | **4527 ms** |
| load checkpoint weights | 187 ms |
| encode utterance (warm) | 5 ms |
| cosine match (85 vecs) | 0.1 ms |

The strong prior held: **imports are ~7.1 s of the ~10 s; inference is ~5 ms.**
So the win is dropping the torch/transformers/ST imports, not quantizing the model.

**Part B — export to ONNX.** `ml/onnx_export.py` exports the fine-tuned MiniLM body
with `torch.onnx.export` (optimum's exporter is incompatible with torch 2.15 — it
imports a symbolic torch removed — so I bypassed it) and int8-quantizes with
`onnxruntime.quantization`. Pooling + normalization are reimplemented in the numpy
wrapper to match the SentenceTransformer exactly: mean-pool over the attention mask,
then L2-normalize. The 85 description embeddings are re-embedded through the ONNX
path into `index_onnx.npz` (the matrix must come from the same model that scores
utterances).

**Part C — torch-free runtime.** `ml/onnx_encoder.py` (`OnnxEncoder` +
`OnnxIntentIndex`) imports only `onnxruntime` + `tokenizers` + `numpy`, lazily on
the abstain path. `hybrid.classify_fallback` now loads `OnnxIntentIndex.cached`
instead of the torch `IntentIndex`; the checkpoint check is now the `.onnx` file.
The heavy trio (torch/transformers/ST) never loads at runtime at all — kept in
`.venv-ml` only for the one-time export and the eval reference.

**Part D — fidelity (the gate on this task).** int8 dynamic quant measured per-pair
cosine **min 0.958** vs the torch reference — below the 0.999 bar — so per the spec
I fell back to **fp32 ONNX**, which measured **cosine 1.00000 (min and mean)** on a
15-utterance sample. Decision parity: on a fixed probe set the ONNX hybrid makes the
**same emit/abstain decision and same intent as the torch hybrid, 15/15**. The
shipped precision is fp32 (the latency win is the dropped imports; fp32 vs int8
inference differs by ~0 ms here, so there's no reason to trade away exactness).
Both fidelity and parity are asserted by new tests.

**Part E — re-measure.** Cold abstain path (fresh process): **~258 ms**, down from
~10 s (**~40× faster**), well under the ~2 s target. Fast rule-hit path: ~49 ms,
still importing none of the ML stack (test extended to assert torch/transformers/
sentence_transformers/onnxruntime all absent after a rule hit). **Decision: no
daemon / resident helper needed** — the hybrid is now dogfoodable.

**Guardrails re-verified:** 147-sweep rule-handled rows byte-identical on/off (0
diffs); encoder returns an intent only (planner/gate unchanged); thresholds
unchanged (t_read 0.55 / t_destructive 0.68 / margin 0.05) and destructive-on-
nonsense still 0/22; degradation now also covers onnxruntime/tokenizers/.onnx
absent → pure v1 (the main Python-3.14 venv has neither numpy nor onnxruntime, so
the whole 409-test suite IS the degradation proof, plus an explicit
artifact-absent test); fast path imports none of the ML stack.

**Deps/artifacts:** `requirements-ml.txt` adds onnxruntime, tokenizers, onnxscript
(export tooling), with the regenerate command. The `.onnx` + `index_onnx.npz` live
under `models/` (already gitignored). optimum was installed during dev but is NOT
required (and downgraded transformers 5.22.2→4.53.3, which ST 5.7 and all tests
tolerate).

**Milestone:** good checkpoint. Committed on `v2-multiturn`.

## 2026-11-11 — Task 41: inspection + 587-scenario dogfood + remaining-work proposal

Inspect + measure + propose — **no implementation** (no rules/encoder/router/KB/
threshold changes, no retraining). Deliverables: `asbuilt_summary.md`,
`tests/dogfood500.py` (harness), `dogfood500_diversity.md`, `v2_remaining_proposal.md`.

**Precondition confirmed:** the live `lb` (from `.venv`, which now has numpy +
onnxruntime + tokenizers, torch-free) reaches the encoder — `lb "what processes are
running"` → `ps aux` with the "interpreted (language model)" marker. The dogfood
tests the real hybrid, not pure rules.

**As-built (read from code):** two NLU paths — single-turn `nlu.parse` (ordered
router; file_discovery is the catch-all last) and multi-turn `session.classify`
(rules dialogue-act) + compositional `SessionFrame`; both render through the same
`compile → gate → render`. The encoder is consulted **only on a single-turn
abstain**. Corrected a prior assumption: single-turn DOES compose type+size and
type+time (the ext slot rides the precedence return); it drops only the **second of
{size,time}** (size wins) and the **second extension** ("csv and json").

**Dogfood — 587 scenarios, leakage-clean vs train (0 dups), all 85 intents (27/27
zero-data), diversity self-audited:**
- **Behaved-as-expected 443/587 = 75.5%** (CORRECT 382 + ABSTAIN_OK 61).
- **Safety intact: 0 GATE_LEAK**; 11/12 outside-maze destructive refused (12th
  safely degraded to a read); no destructive at wrong exit — the asymmetric-abstain
  invariant holds in the wild.
- **MISROUTE_SILENT_DROP = 99 (17%)** — the dangerous class: 88 "filename-hijack"
  (unrecognised op verb + a named file → the catch-all emits `find`/`grep` at rc 0,
  e.g. `delete error.log` → `grep error error.log`), + 11 constraint-drops.
- **ABSTAIN_GAP 38 (6.5%), WRONG_TARGET 4, ENCODER_MISFIRE 2, OVEREAGER 1.**
- **Central finding:** the encoder fired on only **31/587 (5.3%)** and was right
  **27/31 (87%)** — hamstrung because it's consulted only on abstain, while the
  dominant failure is the rules emitting a *confident wrong command*. The #1 lever
  is a rules **coverage-check** (abstain instead of guessing → hand the miss to the
  encoder), not a better encoder.
- **Multi-turn: 48/49 chain turns correct** — the rules session layer is solid.

**Proposal (awaits your review before any build):** (1) rules robustness, lead with
the coverage-check; (2) **defer** the learned dialogue-act head (only ~40 multi-turn
turns; rules work at 98%); (3) continual-learning pipeline — the missing graded
concept, seeded by this 587-set + a runtime feedback log; (4) submission polish
(attention-viz, real rules-vs-hybrid eval, `v2.0.0` tag) after (1); (5) packaging —
an `[ml]` extra in `pyproject.toml`, pure-rules still default. Recommended order:
1 → 5 → 3 → 4 → 2.

**Housekeeping:** the ephemeral `dogfood500_results.csv` is gitignored (like the
Task-35 stress CSV); the generator, diversity audit, as-built, and proposal are
committed. **Not pushed, nothing implemented** — awaiting review. 6 prior commits
(Tasks 35–40) + this = 7 unpushed on `v2-multiturn`.

## 2026-11-11 — Task 42: workstream #1a, the rules coverage-check

First v2 implementation after the proposal. Thin slice of workstream #1 — ONLY the
coverage-check (multi-constraint slot-filling #1b and definite-reference #1c are
separate, deliberately left out so this change's effect is measurable alone).

**Froze the eval first.** Extracted the 587-scenario dogfood into a static
`data/eval/dogfood_eval.jsonl` (eval-only, never migrated into train, in a path
clearly separate from train). `dogfood500.py` now reads this frozen file
(`load_eval`) rather than the generators, so the benchmark can't drift when the
generators are edited; `--freeze` regenerates it deliberately. Spot-audited the
labels (MISROUTE/ABSTAIN_GAP + debatable rows like "wipe the terminal"→clear_screen,
"back up notes.txt"→copy_file, "toss out scratch.tmp"→delete_file): all sound, none
wrong. Left the one quibble (echo $USER is a valid who_am_i render that the judge
scores strictly, ~1 row) untouched so the measurement isn't tuned to flatter.

**The fix.** The 587-dogfood's dominant failure was MISROUTE_SILENT_DROP (99/587,
17%), mostly the "filename-hijack": an unrecognised op verb + a concrete filename →
a catch-all emits a confident wrong find/grep at exit 0, which never reaches the
encoder (consulted only on abstain). Two surgical rule changes, no encoder/
threshold/gate/router change:
- `_discovery_requested()` — positive evidence discovery/search was actually asked
  (a discovery verb/phrase, plural "files", a glob, or a size/time cue). The
  `find_by_name` branch of `_parse_file_discovery` now gates on it: a bare filename
  with no discovery cue returns None (abstain → encoder) instead of `find -name`.
- `_grep_pattern()` filename-awareness — an all-caps token or log word that is part
  of a filename (README.md, error.log) is a file, not a grep pattern (a "." guard
  after the match). So "delete error.log" now routes to delete_file and "arrange the
  lines of README.md in order" to sort_lines, instead of a spurious grep. Also
  stopped a search verb capturing an article ("look for a file named X" → was
  `grep a`).

**Measured delta (baseline on HEAD vs after, both on the frozen eval):**

| judgment | before | after | Δ |
|---|---|---|---|
| CORRECT | 382 | 403 | +21 |
| MISROUTE_SILENT_DROP | 99 | 51 | −48 |
| ABSTAIN_GAP | 38 | 62 | +24 |
| ENCODER_MISFIRE | 2 | 5 | +3 |
| encoder firings (reach) | 31 | 50 | +19 |

Transition analysis: every change came OUT of the MISROUTE bucket (48 removed → 21
CORRECT, 24 honest ABSTAIN_GAP, 3 ENCODER_MISFIRE). **0 CORRECT regressions** —
genuine discovery (find/where/locate/how-many/grep) is byte-unchanged; the +24
ABSTAIN_GAP are freed hijacks where the encoder didn't confidently recover, now an
honest "not sure" rather than a wrong command the user can't judge (exactly the
asymmetric-abstain philosophy). **147-sweep: 0 routing diffs. GATE_LEAK: 0.** All
414+ tests green, including the new `tests/test_coverage_check.py`.

**Residual (51 MISROUTE) belongs to later tasks:** other-parser grabs (file_inspection
head, navigation/workspace cd, who_am_i echo) and the constraint-drop / bare-name
classes — #1b and #1c. Logged, not fixed here (per the brief: "if you find yourself
composing constraints, stop").

**Housekeeping:** added an `[ml]` optional extra to `pyproject.toml` (onnxruntime,
tokenizers, numpy) so `pip install -e '.[ml]'` reproduces the hybrid; pure-rules
stays the default (degradation tests prove it). `v2_remaining_proposal.md` is the v2
plan of record (stale `ROADMAP_V2.md` was never committed). `*:Zone.Identifier` was
already gitignored. Three separate commits (eval freeze / coverage-check /
housekeeping). **Not pushed** — 9 unpushed on `v2-multiturn` (35–42); push after #1
fully lands + the v2.0.0 tag.

**(Later, same day) Pushed to GitHub** at Sambit's request: `origin/v2-multiturn`
advanced f81e942 → e0343a8, so Tasks 41–42 (the 4 commits) are now on the remote
alongside 35–40. Branch in sync with origin.

## 2026-11-11 — Task 43: DESIGN PROPOSAL — attention-based context retention

Research/design task — **no implementation**, nothing in src/rules/encoder/gate/
session/KB/model changed. Ran AFTER Task 42 was merged+pushed. Deliverable:
`attention_context_proposal.md`, grounded in the code and a throwaway probe
(`experiments/task43_attention/probe.py`, run against the real fine-tuned torch
model in `.venv-ml`). Awaits review before any build.

**Why the task:** the project's grade headline is "attention for context-aware
multi-turn," but today context retention is done entirely by the rules-based
`SessionFrame` accumulator + rules `classify()` (48/49 on the dogfood chains) — there
is no attention in the multi-turn path. Attention exists only as a black box inside
the MiniLM bi-encoder on the single-turn fallback, never visualized. The task: figure
out how to make attention do real, visible multi-turn work without the 49-turn data
problem and without regressing the 48/49 rules path.

**Probe findings (the evidence that shaped the recommendation):**
1. **Cross-turn attention is real & visualizable.** On "find the csv files → only the
   ones modified yesterday → show the biggest one", turn-3 tokens put 0.71 of their
   attention mass on turns 1–2 (layer 3 head 1). Token-level, the pronoun **"one"**
   attends to **"files" (0.626)** and **"csv" (0.20)** from turn 1 — attention
   literally resolving coreference across turns. The showcase figure exists
   (`attention_map.svg`). This is the grade centerpiece and it's genuinely there.
2. **Context helps resolve elliptical objects (zero-shot).** "count them" alone is a
   4-way near-tie (count files/matches/lines?); "find the python files. count them"
   → count_files 0.794 clear. "only the ones modified yesterday" sharpens
   0.691→0.872.
3. **Cautionary — naive whole-embedding concatenation REGRESSES the act decision.**
   "show the biggest one" alone ranks session_find_biggest #1 (0.608); with the full
   history prepended it drops to #4 and find_by_time (the turn-2 filter) rises to #1
   (0.775). Mean-pooling blends the turns, so the short operate turn gets outvoted by
   the filter-heavy history. So the *cheapest* approach ("concatenate, match the
   whole embedding") is the wrong way to pick the act/intent — the rules get this
   right at 48/49.

**Recommendation:** spectrum **option 1.5** — attention owns the one thing it
demonstrably wins and the rules can't: **cross-turn coreference/reference
resolution** ("one/them/the ones" → which prior target), reusing the existing
fine-tuned encoder zero-shot (no new training), plus the attention-map figure. The
rules `SessionFrame` keeps state accumulation and dialogue-act/modifier detection
(the 48/49 path the probe shows the encoder would regress). Dialogue-act head stays
deferred (49 turns; refine 7 / fallback 4). Full option 3 (bespoke current→history
cross-attention head) named as the "standout" stretch goal but deferred behind data
+ regression risk. Proposed thin-slice spike: a dev-time reference-resolver that
pools the *current-turn span* (sidestepping finding 3), measured against the rules on
a NEW frozen held-out multi-turn chain eval (the analogue of the frozen 587). Honest
"what attention buys": robustness to phrasings the regex misses (turns that today
fall to fallback→abstain), learned coreference, and interpretability — not
necessarily beating the rules on in-vocabulary chains.

**Safety:** stated explicitly in the proposal — multi-turn destructive ("delete
them") still goes through the same gate + exit-3 + human-review; attention resolves
the referent, it never lowers the bar to run `rm`; an unclear destructive referent
still abstains (invariant #6). The probe confirmed the encoder still recognises
delete_file from context, so nothing is lost.

**Housekeeping:** probe + figures live in `experiments/task43_attention/` (not wired
in; pytest testpaths=["tests"] excludes it; __pycache__ gitignored). Committed the
proposal + probe + both SVGs on `v2-multiturn`. **Not pushed** (awaiting Sambit).
