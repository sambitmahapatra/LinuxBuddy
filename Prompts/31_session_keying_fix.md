# Task 31 — fix multi-turn session persistence (the subshell/PPID bug)

Read `CLAUDE.md`, `STATUS.md`, `ROADMAP_V2.md`, `session.py`, recent `LOG.md`.
Branch: `v2-multiturn`. This is a **bug fix**, highest priority — the headline
multi-turn feature is broken in the real widget. Fix it and prove it live before
any feature work.

## The bug (confirmed by interactive test)

In a real shell, the 3-turn chain did NOT accumulate:
```
turn 1  find CSV files larger than 100MB   → find . -name '*.csv' -size +100M   ✓
turn 2  only the ones modified yesterday   → find . -daystart -mtime 1          ✗ dropped -name/-size
```
Turn 2 started from an EMPTY frame. Root cause: the widget binds Ctrl-G via
`bind -x` and calls `lb` inside a command substitution `$(lb …)`, which runs in a
**subshell**. The session store is keyed on `os.getppid()`, so each Ctrl-G gets a
**different, transient PID** → a different session file → no persistence. The
Task-30 test passed only because it invoked three `lb` processes with a *shared*
PPID, which the real widget does not provide.

(Note: `LINUXBUDDY_SESSION` is currently just a flag `=1`. Keying on it directly
would also make all terminals collide on one session — fix both here.)

## The fix

**Key the session on a stable, per-terminal, exported id — not on `getppid()`.**

1. **Widgets** (`shell/linuxbuddy.bash` AND `shell/linuxbuddy.zsh`): at
   source-time (top level, once per shell — NOT inside the widget function),
   replace `export LINUXBUDDY_SESSION=1` with a unique stable id, e.g.:
   ```sh
   export LINUXBUDDY_SESSION="lb-$$-$(date +%s%N)"
   ```
   `$$` is the interactive shell's PID, fixed for that terminal; the timestamp
   makes it unique across shells. Because it's exported, every `lb` call in that
   terminal — subshell, command substitution, or direct — inherits the SAME value.

2. **`session.py`**: derive the store key from `$LINUXBUDDY_SESSION` when set
   (sanitize for a filename), e.g. `~/.cache/linuxbuddy/session_<sanitized>.json`.
   Fall back to `getppid()` ONLY when the env var is absent (direct `lb` use
   without the widget). The env var, when present, is authoritative.

3. `lb --frame` and `lb --reset` must read/write that same keyed session (they
   inherit `$LINUXBUDDY_SESSION` in the shell — just confirm they use the same
   key-derivation path, not a separate one).

4. Keep the existing TTL + reset-word + cwd-change reset behavior. Add a small
   cleanup of session files older than the TTL so `~/.cache/linuxbuddy/` doesn't
   accumulate stale files (one per old shell).

## Tests (the test that WOULD have caught this)

- **Env-keyed persistence across processes:** spawn `lb` as **two separate
  subprocesses** that share the SAME `LINUXBUDDY_SESSION` env value but do NOT
  share a parent (simulate the subshell case — e.g. run each via its own
  `subprocess.run`, optionally through `bash -c '… $(lb …) …'`). Assert the frame
  from call 1 is visible to call 2. This must FAIL against the old getppid
  keying and PASS after the fix.
- **Isolation:** two different `LINUXBUDDY_SESSION` values → two independent
  sessions (no cross-talk).
- **Fallback:** with `LINUXBUDDY_SESSION` unset, lb still works single-turn.
- Re-assert the Task-30 chain test accumulates with the new keying.

## Manual re-verification (required — this is the real proof)

In a fresh bash shell (so the new widget id is set), inside the maze:
```
cd ~/linuxbuddy/testlinuxbuddy/project
find CSV files larger than 100MB      [Ctrl-G]  → find . -name '*.csv' -size +100M
only the ones modified yesterday      [Ctrl-G]  → find . -name '*.csv' -size +100M -daystart -mtime 1
show the biggest one                  [Ctrl-G]  → …filters kept… -printf '%s\t%p\n' | sort -rn | head -1
```
`lb --frame` between turns must show the frame GROWING. A reset must clear it.

## Done when

The env-keyed persistence test passes; the live 3-turn chain accumulates (report
what turn 2's buffer becomes); the 139 single-turn sweep is unchanged; TTL/reset
intact. `pytest` green. Commit on `v2-multiturn`, don't push (or push if you
prefer — your call). Document the keying change in LOG.md + STATUS.md.
