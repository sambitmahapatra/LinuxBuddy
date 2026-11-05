# Task 10 — domain: processes (read-only intents)

Read `CLAUDE.md` and the Tier 1 batch rules. Build ONLY the read-only intents.
`kill`/`pkill` are destructive — SKIP them (later tier, needs the gate).

Some intents need a 2-stage pipe (`ps ... | head`). If the planner doesn't yet
support a 2-stage pipeline, add minimal support FIRST per the batch rules.

## Intents (grounded in the real scenarios)

| Intent | Example requests | Command |
|---|---|---|
| `list_processes` | "what's running", "show everything running" | `ps aux` |
| `top_by_cpu` | "what's using the most CPU" | `ps -eo pid,comm,%cpu --sort=-%cpu | head -n {count}` |
| `top_by_mem` | "biggest memory consumers", "what's eating RAM" | `ps -eo pid,comm,rss --sort=-rss | head -n {count}` |
| `find_process` | "is python running", "find the jupyter process" | `pgrep -af {pattern}` |
| `process_on_port` | "what's using port 8080" | `ss -ltnp "sport = :{port}"` |
| `show_pid` | "show the process with PID 1234" | `ps -p {pid} -o pid,ppid,stat,%cpu,%mem,args` |

Default `count` = 10 for the top_by_* intents when no number given.

## Slots

`PROCESS` (name/pattern for find_process), `PORT` (process_on_port),
`PID` (show_pid — a number), `COUNT` (top_by_* — optional).

## Deferred (skip)

- `kill`, `pkill` — destructive, later tier.
- `top -b -n 1`, `free -h`, `/proc` inspection, compound resource dashboards —
  defer (compound or interactive).

## Build

- `kb/commands/` for ps, pgrep, ss (argv-stage, `risk_ops: [read]`).
- Capability `inspect_process` in `kb/taxonomy.yaml` with these 6 intents.
- Extend `nlu.py`: "most CPU"→top_by_cpu, "most memory/RAM"→top_by_mem,
  "is X running / find X process"→find_process (pattern=X),
  "port N"→process_on_port (port=N), "PID N"→show_pid.

## Tests (`tests/test_processes.py`)

| input | expect |
|---|---|
| "what's running" | list_processes |
| "what's using the most cpu" | top_by_cpu, count=10 |
| "biggest memory consumers top 5" | top_by_mem, count=5 |
| "is python running" | find_process, pattern=python |
| "what's using port 8080" | process_on_port, port=8080 |
| "show the process with pid 1234" | show_pid, pid=1234 |
| "kill python" | abstain/skip (destructive, not in this task) |

## Done when

`pytest` passes (incl. regression and the pipe round-trip test if you added
pipe support). Against the maze (source `runtime_setup.sh` for $PID/$PORT):
`lb what's using port <PORT>` finds the http.server;
`lb show the process with pid <PID>` shows it.
Verify against the Processes read-only maze scenarios; note pass rate.
