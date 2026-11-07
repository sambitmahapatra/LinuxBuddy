# Task 15 — complete filesystem (chmod) + processes (kill)

Read `CLAUDE.md` and the Tier 3 batch rules. The gate (P2.0) exists, so these
destructive intents are now safe to add. All are gated to the maze.

## Add to filesystem_permissions: chmod intents

| Intent | Example | Command | risk_ops |
|---|---|---|---|
| `make_executable` | "make this script executable", "my script isn't executable, fix it" | `chmod u+x -- {path}` | write |
| `remove_executable` | "this text file should not be executable" | `chmod a-x -- {path}` | write |
| `set_permission` | "set this to 600", "only I should read or edit this" | `chmod {mode} -- {path}` | write |

`set_permission` slot `PERMISSION`: octal ("600", "644", "700") directly; or
map intent words — "only I can read/edit" → 600, "private" → 600, "only I can
enter" (dir) → 700. If the mode can't be determined, abstain with a hint
("what permissions? e.g. 600 for private").

## Add to processes: kill intents

| Intent | Example | Command | risk_ops |
|---|---|---|---|
| `kill_process` | "kill the stuck process", "stop the process named X" | `pkill -f -- {pattern}` | write |
| `kill_pid` | "kill process 1234" | `kill -- {pid}` | write |

The processes parser already returns `_ABSTAIN` on kill verbs (from Task 10) —
replace that with real kill intents. Keep the safety: `kill`/`pkill` are gated,
so they only emit inside the maze in prototype mode.

## Build

- Extend `kb/commands/fs.yaml` (chmod) and `kb/commands/process.yaml` (kill)
  with the new intents, `risk_ops: [write]`.
- Extend the fs and process parsers in `nlu.py` to produce these intents
  instead of abstaining.
- Reuse the gate — no new gate logic needed.

## Tests

Add to `tests/test_filesystem_read.py` (or a new test file) and
`tests/test_processes.py`:

| input | expect |
|---|---|
| "make deploy.sh executable" | make_executable (write, gated) |
| "set config to 600" | set_permission, mode=600 (write, gated) |
| "only I should read this secret" | set_permission, mode=600 |
| "kill the training process" | kill_process, pattern=training (write, gated) |
| "kill process 4821" | kill_pid, pid=4821 (write, gated) |
| a chmod/kill request with cwd outside the maze | abstain (via gate) |

## Done when

`pytest` passes (incl. regression across all 7 domains). Inside the maze:
`lb make good_script.sh executable` → `chmod u+x -- good_script.sh` runs;
from `/tmp` the same abstains via the gate. `lb kill the sleep process`
renders `pkill -f -- sleep` inside the maze (verify with the runtime sleep
process; be careful — it genuinely kills it, which is fine in the maze).
Note: filesystem and processes are now COMPLETE domains.
