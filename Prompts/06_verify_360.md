# Task 06 — verify the 360 scenarios against the maze

Read `CLAUDE.md`. This measures what actually works. No fixing — raw
verdicts first.

## What this is NOT

This is not evaluating LinuxBuddy's NLU. The thin slice only understands
file_discovery. This task checks the **reference commands in the CSV** run
correctly against the maze — i.e. that the ground-truth dataset is sound.
(LinuxBuddy NLU verification comes later, per-domain, as domains are built.)

## Setup

```
cd ~/linuxbuddy
./testlinuxbuddy/build_maze.sh
source testlinuxbuddy/bindings.env
source testlinuxbuddy/runtime_setup.sh    # exports PID, PORT, GPU_ID
```

## Method

For each row in `data/scenarios/LinuxBuddy_360_WSL2_Terminal_Scenarios.csv`,
run `reference_shell_plan` with cwd = `$PROJECT_DIR`. Classify:

- **PASS** — exit 0, output consistent with the request
- **EMPTY** — exit 0 but no output where the request implied some
- **FAIL** — non-zero exit
- **SKIP** — needs something absent (network, /mnt/c write, a real service);
  record what was missing
- **UNSAFE** — would modify something outside `~/testlinuxbuddy`; DO NOT run,
  just report

## Safety — non-negotiable

- Never run anything whose target resolves outside `~/testlinuxbuddy`.
  Check before executing.
- Never run `sudo`. Mark SKIP.
- Never write to `/mnt/c`. Mark SKIP.
- `risk=network` rows: do not execute, mark SKIP.
- Long-runners (tail -f, servers): wrap in `timeout 5`; exit 124 with output
  = PASS.
- Rebuild the maze before any batch that follows a `writes` test, so each
  batch starts clean.

## Output

Write `data/scenarios/verify_results.csv`: original columns plus `verdict`,
`exit_code`, `stdout_lines`, `stderr_excerpt`, `missing_dep`.

Then print a summary: counts per verdict, broken down by domain, and the
full list of FAIL and EMPTY rows with their stderr.

Do NOT fix any rows. Raw verdicts only — I decide what to fix or drop.

## Done when

`verify_results.csv` exists for all 360 rows and the per-domain summary is
printed.
