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
