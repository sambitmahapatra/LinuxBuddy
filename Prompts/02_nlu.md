# Task 02 — rule-based NLU for file_discovery

Read `kb/taxonomy.yaml`. Follow all invariants in `CLAUDE.md`.
**No machine learning in this task.** Pure rules and regex.

## Build

### `src/linuxbuddy/nlu.py`

`parse(text: str) -> Frame | None`

A `Frame` is a dataclass: `intent: str`, `slots: dict`. Slots may contain
`path`, `ext`, `size_bytes`, `days`, `ftype`, `pattern`.

Normalization rules:
- **size**: `"100 megs"`, `"100mb"`, `"100 mb"`, `"over 100M"`,
  `"bigger than 2 gigs"` -> bytes. Use binary units: MB = MiB = 1048576,
  GB = GiB = 1073741824, KB = 1024.
- **time**: `"last 3 days"` -> 3, `"this week"` -> 7, `"today"` -> 1,
  `"last 24 hours"` -> 1.
- **ext**: `"csv files"` -> `csv`, `"python files"` -> `py`,
  `"*.log"` -> `log`, `"json"` -> `json`.
- **path**: `"here"`, `"this folder"`, `"this directory"` -> `.`;
  `"downloads"` -> `$HOME/Downloads` (leave as the literal token
  `$HOME/Downloads` — the planner resolves it); an explicit path -> itself.
  Default when unmentioned: `.`.
- **intent selection**:
  - a size expression present -> `find_by_size`
  - a time expression present -> `find_by_time`
  - a quoted name or glob or "called X" -> `find_by_name` (set `pattern`)
  - only a file type/extension -> `find_by_type`
  - nothing confident -> return `None` (abstain)

Abstention is a feature. Returning `None` on vague input like
`"clean up my files"` is correct, not a failure.

### `tests/test_nlu.py`

Assert the frame for each:

| input | expect |
|---|---|
| `"csv files over 100 megs"` | by_size, ext=csv, size_bytes=104857600, path=. |
| `"python files changed in the last 3 days"` | by_time, ext=py, days=3 |
| `"find files called config"` | by_name, pattern=config |
| `"all the log files here"` | by_type, ext=log, path=. |
| `"big files in downloads"` | path=$HOME/Downloads (size vague -> by_size or abstain; pick one and test it) |
| `"clean up my mess"` | None |

## Done when

`pytest tests/test_nlu.py` passes. Document in a comment which way you
resolved the vague-"big" case and why.
