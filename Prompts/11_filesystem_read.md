# Task 11 — domain: filesystem_permissions (read-only intents)

Read `CLAUDE.md` and the Tier 1 batch rules. Build ONLY the read-only intents.
`chmod` is destructive — SKIP it (later tier, needs the gate).

## Intents (grounded in the real scenarios)

| Intent | Example requests | Command |
|---|---|---|
| `check_writable` | "can I write to this folder" | `test -w {path} && printf "writable\n"` |
| `check_readable` | "is this dataset readable by my account" | `test -r {path} && printf "readable\n"` |
| `check_exists` | "does config.yaml exist", "tell me if X is there" | `test -e {path} && printf "found\n"` |
| `show_permissions` | "show permissions for this directory" | `ls -ld -- {path}` |
| `show_owner` | "who owns the data", "what account owns this" | `stat -c "%U:%G" -- {path}` |
| `dir_empty` | "is this results directory empty" | `test -z "$(ls -A -- {path})" && printf "empty\n"` |
| `disk_usage` | "how big is my data folder", "what's using space in X" | `du -sh -- {path}` |

Note on `dir_empty`: the command uses a command substitution `$(ls -A ...)`.
Render it so the inner path is quoted and the structure is compiler-built, not
assembled from slot text. If that's awkward in the current AST, defer dir_empty
and document it — don't hack it in unsafely.

## Slots

`PATH` (required for all — file or directory).

## Deferred (skip)

- `chmod` (any permission change) — destructive, later tier.
- `namei -l`, `stat -f` filesystem type, `findmnt`, ACL (`getfacl`) — compound
  or specialized; defer.
- Compound audits ("timestamp AND type AND hash") → abstain.
- `$TARGET_FILE` scenarios (known dangling binding) — skip.

## Build

- `kb/commands/` for test, ls, stat, du (argv-stage, `risk_ops: [read]`).
- Capability `inspect_filesystem` in `kb/taxonomy.yaml` with these intents.
- Extend `nlu.py`: "can I write"→check_writable, "readable"→check_readable,
  "exists/is there"→check_exists, "permissions"→show_permissions,
  "who owns"→show_owner, "empty"→dir_empty, "how big/space"→disk_usage.

## Tests (`tests/test_filesystem_read.py`)

| input | expect |
|---|---|
| "can I write to the output folder" | check_writable |
| "does config.yaml exist" | check_exists |
| "is the data folder readable" | check_readable |
| "show permissions for the logs dir" | show_permissions |
| "who owns train.log" | show_owner |
| "is the results folder empty" | dir_empty (or deferred) |
| "how big is the data folder" | disk_usage |
| "make this executable" | abstain/skip (chmod, destructive) |

## Done when

`pytest` passes (incl. regression). Against the maze:
`lb can I write to the output folder` returns writable/not;
`lb how big is the data folder` returns a size;
`lb who owns train.log` returns owner:group.
Verify against the Filesystem read-only maze scenarios; note pass rate and any
deferred intents.
