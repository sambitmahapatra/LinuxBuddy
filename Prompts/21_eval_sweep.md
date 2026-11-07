# Task 21 — run the evaluation sweep (capture, do NOT execute)

Read `CLAUDE.md`. This measures how `lb` responds across 130 varied natural
requests. You RUN `lb` on each request and record what it returns. You do NOT
execute the commands `lb` produces, and you do NOT judge correctness — raw
capture only. A human analyzes the result.

## Input

`data/eval/eval_requests.csv` — columns: `id, domain, goal, request`.
(Copy the provided file there if not already present.)

## Method

For each row, run the `lb` CLI with the `request` text as its argument, in a
fixed, consistent cwd (inside the maze: `testlinuxbuddy/project`, with
`bindings.env` and `runtime_setup.sh` sourced so $PORT etc. resolve). Capture:

- `lb_stdout` — exactly what lb printed to stdout (the command, or empty)
- `lb_stderr` — stderr (the abstain hint, if any)
- `exit_code` — 0 (read command) / 1 (abstain) / 3 (destructive command), per
  the new exit-code scheme if Task 18 landed; otherwise whatever lb returns
- `outcome` — a mechanical label from the above, NOT a judgment:
  `COMMAND` (stdout non-empty) or `ABSTAIN` (stdout empty / exit 1)

**Do NOT run `lb_stdout` as a command.** This sweep only records what lb
*says*, never executes it. (Several requests are destructive — kill, chmod,
rm, mkdir — and must not run.)

Run `lb` itself the same way a user would (the installed CLI). If `lb` for some
request hangs or errors, record the error in `lb_stderr` and move on; don't let
one row stall the sweep (wrap each in a short timeout).

## Output

`data/eval/eval_results.csv` — the input columns plus `lb_stdout`,
`lb_stderr`, `exit_code`, `outcome`. One row per request, all 130.

Then print a quick tally: per domain, how many COMMAND vs ABSTAIN. Nothing more
— no correctness judgment, that's the human's analysis step.

## Done when

`eval_results.csv` exists with all 130 rows captured, no command executed, and
the per-domain COMMAND/ABSTAIN tally printed. Commit it. Do not push.
