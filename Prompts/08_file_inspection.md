# Task 08 — domain: file_inspection

Read `CLAUDE.md` and the Tier 1 batch rules. Single-command intents only;
compound requests abstain.

## Intents (grounded in the real scenarios)

| Intent | Example requests | Command |
|---|---|---|
| `preview_head` | "first 20 lines of the log", "show the top of config.yaml" | `head -n {count} -- {path}` |
| `preview_tail` | "last 50 lines", "show the end of train.log" | `tail -n {count} -- {path}` |
| `count_lines` | "how many lines in access.log", "line count of this" | `wc -l -- {path}` |
| `show_size` | "size of this file in bytes", "how big is this file" | `wc -c -- {path}` (bytes) |
| `show_stat` | "when was this modified", "show the timestamp of the model" | `stat -c {fmt} -- {path}` |
| `detect_type` | "what kind of file is this", "what format is this download" | `file -- {path}` |

Defaults: `count` defaults to 10 when a preview request gives no number
("show me the log" → head -n 10). `show_stat` picks a sensible `-c` format
(e.g. `%y %A %s %n`) unless the request asks specifically for time or perms.

Slots used: `PATH` (required for all), `COUNT` (preview intents).

## Deferred (abstain or skip)

- Compound sanity-checks ("preview, count AND size" — three commands) → abstain.
- `less`, `od`, `cat` of huge files — interactive/edge; skip for now.
- Any scenario reading `$TARGET_FILE` (the known dangling binding) — skip.

## Build

- `kb/commands/` entries for head, tail, wc, stat, file (argv-stage specs,
  `risk_ops: [read]`).
- Add capability `inspect_file` to `kb/taxonomy.yaml` with these 6 intents.
- Extend `nlu.py`: route to file_inspection and extract PATH + COUNT.
  - `count`: "first/last N lines", "N lines" → N; bare "lines" → wc -l.
  - distinguish bytes ("size in bytes", "how big") → show_size, from lines.

## Tests (`tests/test_file_inspection.py`)

| input | expect |
|---|---|
| "first 20 lines of train.log" | preview_head, count=20, path=train.log |
| "last 50 lines of the log" | preview_tail, count=50 |
| "how many lines in access.log" | count_lines, path=access.log |
| "size of config.yaml in bytes" | show_size |
| "what kind of file is data.bin" | detect_type |
| "when was model.pt last changed" | show_stat (time) |
| "preview, count and size of this csv" | abstain (compound) |

## Done when

`pytest` passes (incl. file_discovery regression), and against the maze:
`lb first 20 lines of train.log` runs and shows 20 lines;
`lb how many lines in app.log` returns the count.
Verify the 6 intents against the File-inspection maze scenarios; note pass rate.
