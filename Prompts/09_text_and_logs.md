# Task 09 — domain: text_and_logs

Read `CLAUDE.md` and the Tier 1 batch rules. All read-only. grep dominates
this domain (23 of 40 rows).

## Intents (grounded in the real scenarios)

| Intent | Example requests | Command |
|---|---|---|
| `search_in_file` | "find the word convergence in this report", "show errors in the log" | `grep -nF {flags} -- {pattern} {path}` |
| `search_recursive` | "find TODO across the source files", "where is X used in src" | `grep -RnF {flags} -- {pattern} {dir}` |
| `count_matches` | "how many warnings in this log", "count the errors" | `grep -cF {flags} -- {pattern} {path}` |
| `sort_lines` | "put these names in alphabetical order", "sort this list" | `sort -- {path}` |
| `unique_lines` | "show only distinct rows", "dedupe this list" | `sort -u -- {path}` |

Flags are modifiers on the grep intents, not separate intents:
- "ignore case" / "case insensitive" / (default for error/warning words) → `-i`
- "with line numbers" → `-n` (default on for search_in_file)
- a literal word → `-F` (default; safer than regex for a prototype)

## Slots

`PATTERN` (required for grep intents — the string to find), `PATH` (file) or
`PATH_DIR` (for recursive), optional case-insensitive flag.

## Deferred (abstain or skip)

- `tail -f` ("watch the log as it grows") — long-running/interactive. Either
  SKIP, or map it but flag that it runs until Ctrl-C. Recommend: map to
  `tail -f` but print a note "(runs until you stop it)". Your call — document it.
- `awk`/`sed`/`cut` column extraction, `comm`, `uniq -c` frequency counts —
  these are compound or mini-language; defer to Tier 2/later.
- Context flags (`-C`, before/after lines) — defer.

## Build

- `kb/commands/` for grep, sort (argv-stage, `risk_ops: [read]`).
- Capability `search_text` in `kb/taxonomy.yaml` with these 5 intents.
- Extend `nlu.py`: extract PATTERN (the quoted or named word to find), PATH,
  recursive-vs-single (does the request say "across files"/"in the folder" →
  recursive, else single file), count-vs-show ("how many" → count_matches).

## Tests (`tests/test_text_and_logs.py`)

| input | expect |
|---|---|
| "find the word convergence in report.txt" | search_in_file, pattern=convergence |
| "show errors in train.log" | search_in_file, pattern=error, -i |
| "find TODO across the src folder" | search_recursive, pattern=TODO, dir=src |
| "how many warnings in the log" | count_matches, pattern=warning |
| "sort names.txt alphabetically" | sort_lines |
| "show distinct rows in list.txt" | unique_lines |
| "find stuff" | abstain (no path, vague pattern) |

## Done when

`pytest` passes (incl. regression). Against the maze:
`lb show errors in train.log` finds the ERROR lines;
`lb how many warnings in train.log` returns a count;
`lb find TODO across src` lists the TODO hits.
Verify against the Text-and-logs maze scenarios; note pass rate and which rows
you deferred.
