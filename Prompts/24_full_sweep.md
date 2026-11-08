# Task 24 — full scenario sweep (route + execute, capture to CSV)

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md` first.

This is the systematic replacement for manual bug-hunting. You run `lb` on a
large, ordered scenario set **inside the maze**, record what it emits, and — for
safe commands — actually execute them and record whether they worked. A human
reviews the output CSV. **You do NOT judge correctness.** Raw capture only.

## Inputs

- `data/eval/sweep_scenarios.csv` — columns:
  `id, domain, intent, variant, risk, cwd, request, expected_shape, notes`
  (copy the provided file there if not already present.)
- The maze at `testlinuxbuddy/` (the canonical one with the known MANIFEST sha256).
- `cwd` in each row is **relative to the maze root** (`testlinuxbuddy/`).

## Two things you capture per row

1. **Routing** — what `lb` *said*: its stdout (the command, or empty), stderr
   (abstain hint), and exit code (0 read / 1 abstain / 3 destructive).
2. **Executability** — for *read* rows only, whether the emitted command
   actually *runs clean* in the maze. This is the new signal: `lb` can emit a
   command confidently that still fails (e.g. `cd -- linuxbuddy` from the wrong
   directory). We want to see that.

## Method — PHASE 1: read rows (risk == read)

Run these against the **canonical maze** (they don't mutate it).

For each read row, in order:
1. `cd` to `testlinuxbuddy/<cwd>`. If that directory doesn't exist, record
   `exec_status=skipped-no-cwd` and move on (don't fail the sweep).
2. Source `bindings.env` and `runtime_setup.sh` so `$PORT` etc. resolve.
3. Run `lb` with the `request` text as its argument. Capture:
   - `lb_stdout` (the command, or empty)
   - `lb_stderr` (abstain hint if any)
   - `exit_code`
   - `outcome` — mechanical: `COMMAND` if stdout non-empty, else `ABSTAIN`.
4. **Then execute the emitted command** to test executability, WITH GUARDS:
   - **Skip GUI / external launches** — if `lb_stdout` contains `code`,
     `explorer.exe`, `wslview`, `xdg-open`, `cmd.exe`, `powershell.exe`, or the
     row's `notes` says "do NOT execute": record `exec_status=skipped-gui`,
     do not run it.
   - Otherwise run it in a subshell from the same `cwd`, with a per-command
     `timeout` (e.g. `timeout 10s bash -c '<cmd>'`), **writing output to a temp
     file, not a pipe** (avoid the pipe-deadlock we hit before), and
     **kill the whole process group** on timeout.
   - Capture `exec_exit` (the command's exit status) and
     `exec_status` = `ok` (exit 0) / `nonzero` (ran, exit != 0) /
     `timeout` / `skipped-gui` / `skipped-no-cwd` / `skipped-abstain`.
   - `exec_output_head` — first ~200 chars of combined stdout/stderr (so the
     reviewer can see *why* something failed), newlines collapsed to spaces.
   - For ABSTAIN rows, `exec_status=skipped-abstain` (nothing to run).

   **Note:** `exec_status=nonzero` is NOT automatically a bug — a `grep` with no
   match exits 1, the chmod-000 `noaccess_dir` denies reads, etc. It's a signal
   for the human, not a verdict.

## Method — PHASE 2: destructive rows (risk == destructive)

These MUTATE the filesystem, so they must NOT touch the canonical maze.

1. Capture **routing** for every destructive row first (same as phase 1 steps
   1–3), against the canonical maze — this is read-only observation of what `lb`
   *says*, and confirms destructive requests exit 3. Do NOT execute here.
2. Then, to test executability safely: make a **throwaway copy** of the maze —
   `cp -r testlinuxbuddy /tmp/maze_destructive_run` (or rebuild via
   `build_maze.sh` into a temp dir). Run each destructive command **there**,
   from the mapped `cwd`, with the same guards (timeout, temp file, group kill).
   Use the fake PIDs in the scenarios for `kill` rows — never kill real PIDs.
   Capture `exec_exit` / `exec_status` / `exec_output_head` as in phase 1.
3. **Delete the throwaway copy** when done (`rm -rf /tmp/maze_destructive_run`).
   Verify the canonical maze is untouched: re-check its MANIFEST sha256 matches
   `5af914bd…` and record PASS/FAIL of that check in LOG.md. If it doesn't
   match, STOP and report — something wrote outside the copy.

If copying/rebuilding the maze isn't practical, fall back to **routing-only**
for destructive rows (phase 2 step 1) and mark `exec_status=skipped-destructive`.
Say which you did in LOG.md.

## Output

`data/eval/sweep_results.csv` — all input columns PLUS:
`lb_stdout, lb_stderr, exit_code, outcome, exec_exit, exec_status, exec_output_head`
One row per scenario, all 139, in the original order.

Then print a tally:
- per domain: COMMAND vs ABSTAIN
- overall: how many read rows had `exec_status=ok` vs `nonzero` vs `timeout`
- count of exit-code mismatches (risk==destructive but exit_code!=3, or
  risk==read but exit_code==3) — a quick integrity check.

Nothing more — no correctness judgment. The human does that from the CSV.

## Guards recap (lessons already paid for)

- Per-command `timeout`; temp files not pipes; kill the process group on
  timeout; one row never stalls the sweep (wrap each, record the error, move on).
- Never execute GUI/external launches.
- Never run a destructive command against the canonical maze.
- Never kill a real PID (use the scenario's fake PID).

## Done when

`sweep_results.csv` exists with all 139 rows, the canonical maze MANIFEST still
matches after phase 2, the tallies are printed, and it's committed (do NOT push).
Document in LOG.md: which phase-2 path you took, the MANIFEST re-check result,
and any row that errored the harness itself.
