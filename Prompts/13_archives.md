# Task 13 — domain: archives_backup

Read `CLAUDE.md` and the Tier 2 batch rules. Needs the gate (Task 12) done.
Read intents work anywhere; write intents are gated to the maze.

## Intents (grounded in the real scenarios)

### Read-only (work anywhere)

| Intent | Example | Command |
|---|---|---|
| `list_archive` | "what's inside my backup tarball", "show files in this zip" | `tar -tf -- {archive}` (or `python3 -m zipfile -l {zip}`) |
| `archive_integrity` | "does my gzip pass its integrity check" | `gzip -t -- {archive}` |
| `archive_size` | "how big is this project backup" | `du -h -- {archive}` |

### Write (gated to maze)

| Intent | Example | Command | risk_ops |
|---|---|---|---|
| `create_archive` | "package the project into one compressed file" | `tar -czf {archive} -C {parent} -- {name}` | write |
| `extract_archive` | "unpack this tarball into the output folder" | `mkdir -p -- {dir} && tar -xf {archive} -C {dir}` | write |
| `compress_file` | "compress this log without losing it" | `gzip -k -- {path}` | write |

Use `tar` for .tar/.tar.gz and `python3 -m zipfile` for .zip (portable, no zip
dependency). Pick by the archive's extension.

## Slots

`ARCHIVE` (the archive file), `PATH`/`PATH_DIR` (what to archive or extract to),
`EXT` where it disambiguates zip vs tar.

## Deferred (skip/abstain)

- `gzip -dc > file` (redirect), `cp -a` folder copy, compound integrity+size
  audits → defer (redirect/compound).
- `find ... -name "*.tar.gz" -o -name "*.zip"` (locate archives) — this is
  really a file_discovery query; skip here.

## Build

- `kb/commands/` for tar, gzip (argv-stage; read intents `risk_ops: [read]`,
  write intents `risk_ops: [write]`).
- Capability `manage_archives` in `kb/taxonomy.yaml`.
- Extend `nlu.py`: "what's inside/list" → list_archive; "integrity/check" →
  archive_integrity; "package/compress into" → create_archive; "unpack/extract
  into" → extract_archive; "compress this" → compress_file.
- extract_archive uses the 2-stage `&&` composition (mkdir && tar).

## Tests (`tests/test_archives.py`)

| input | expect |
|---|---|
| "what's inside backup.tar.gz" | list_archive (read, works anywhere) |
| "does data.gz pass its integrity check" | archive_integrity |
| "package the src folder into src.tar.gz" | create_archive (write, gated) |
| "unpack backup.tar.gz into output" | extract_archive (write, gated, 2-stage) |
| "compress train.log" | compress_file (write, gated) |
| gated-write intent, cwd outside maze | abstain (via the gate) |

## Done when

`pytest` passes (incl. regression). Against the maze (cwd inside it):
`lb what's inside backup_2026-01.tar.gz` lists members;
`lb package the src folder into test.tar.gz` creates it (gated — confirm it
abstains when cwd is outside the maze). Verify against Archives maze scenarios;
note pass rate and deferred rows.
