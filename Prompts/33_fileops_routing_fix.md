# Task 33 — route file-management verbs ahead of `find` (fix Task 32 regression)

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Branch `v2-multiturn`. Small,
targeted routing fix — the file-ops intents from Task 32 are built correctly but
never get reached when a filename is present, because `find` wins first.

## Evidence (probe in the maze, `testlinuxbuddy/project`)

| request | emits now | must emit |
|---|---|---|
| move report.csv to archive | `find . -name '*.csv'` (exit 0) | `mv -- report.csv archive` (exit 3) |
| delete old.log | `find . -name '*.log'` (exit 0) | `rm -- old.log` (exit 3) |
| copy requirements.txt to archives | `find . -name '*.txt'` (exit 0) | `cp -- requirements.txt archives` (exit 3) |
| rename a.txt to b.txt | `find . -name '*.txt'` (exit 0) | `mv -- a.txt b.txt` (exit 3) |
| make a folder photos | `mkdir -p -- photos` (exit 3) ✅ | unchanged — already correct |

**Root cause:** `file_management` is checked AFTER `file_discovery` in the router,
and `find` matches on the filename/extension token, so it wins. `mkdir` survives
only because "photos" has no extension for `find` to latch onto. This is the same
`find`-greediness Task 25 fixed for the view/copy/count intents — it just was
never extended to the Task-32 verbs.

## The fix

Make the **file-management verbs win over `find`** when one is the leading/primary
verb, regardless of any filename in the request. Either check `file_management`
before `file_discovery` in the router, or guard `find` so it does not fire when
the head verb is a file-op verb.

- **File-op verb cues:** move, copy, delete, remove, rename, "get rid of",
  "put X in Y", plus bare `mv`/`cp`/`rm`. When present as the primary verb →
  `file_management`.
- **`find` keeps winning** for its own verbs: find, list, "where is", locate,
  "search for … files", "how many … files", "recently modified", "biggest".
  Do NOT regress discovery (sweep rows E024–E046).

Rendering + risk are already defined in Task 32 — this task just ensures they're
reached:
- move / rename → `mv -- SRC DST` (exit 3)
- copy → `cp -- SRC DST` (exit 3); keep "make a copy of X" → `cp -- X X.bak`
- delete → `rm -- TARGET` (exit 3), strongest warning, no auto `-f`
- mkdir → `mkdir -p -- NAME` (exit 3) — unchanged
All maze-gated (refused outside `LINUXBUDDY_MAZE_ROOT`).

## Tests (write the failing cases first)

- The four rows above emit the right destructive command at **exit 3**.
- Two-slot extraction works with filenames present ("X.ext to Y").
- Gate: each is **refused outside the maze**, allowed inside.
- **Regression (critical):** `find` still wins for discovery — "find all csv
  files", "where is settings.json", "locate train.py", "how many csv files",
  "recently modified logs" still route to `find`. `mkdir` unchanged. The older
  `backup_copy` ("make a copy of config.yaml") still works. 139 single-turn
  sweep: 0 routing diffs. Multi-turn chain still accumulates.

## Manual re-verify

```
cd ~/linuxbuddy/testlinuxbuddy/project
lb "move report.csv to archive";        echo $?   # mv -- …           exit 3
lb "delete old.log";                    echo $?   # rm -- old.log     exit 3
lb "copy requirements.txt to archives"            # cp -- …           exit 3
lb "find all csv files"                           # STILL find .      exit 0
cd ~/linuxbuddy/test_02
lb "delete something.txt";              echo $?   # REFUSED (outside maze)
```

## Done when

The four file-op cases route correctly at exit 3, discovery is unregressed,
`pytest` green, commit on `v2-multiturn`. Document in LOG.md + STATUS.md.

## Optional

Add ~8 rows (move/copy/delete/rename with filenames, + a discovery control) to
`sweep_scenarios.csv` so this class is covered by future regression sweeps —
this is the exact gap that let it through.
