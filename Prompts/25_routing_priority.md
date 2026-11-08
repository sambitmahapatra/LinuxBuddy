# Task 25 — routing priority (stop `find` eating other intents) + parsing bugs

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Driven by
`data/eval/sweep_results.csv`. These are the **silent wrong-command** fixes —
highest priority, because a confident wrong command is worse than an abstain.

## A. `find` is a greedy catch-all — fix the routing priority FIRST

Root cause: when a *view / preview / count / copy / history / process /
permission-read* request happens to contain a filename or glob, the
`file_discovery` `find` parser intercepts it and wins. `find` must only win for
genuine **discovery** phrasing. Make the router prefer the specific intent when
its verb is present; `find` is the fallback, not the front-runner.

Rows that must change (each currently routes to `find` and must not):

| row | request | currently | must emit |
|---|---|---|---|
| E047 | show me config.yaml | `find . -name config.yaml` | `cat -- config.yaml` (or head preview) |
| E050 | what's in the log | `find . -name '*.log'` | preview — `cat`/`head` of `*.log` |
| E052 | peek at data.csv | `find . -name data.csv` | `head -- data.csv` |
| E054 | last lines of the log | `find . -name '*.log'` | `tail -- *.log` |
| E075 | remove duplicate lines from names.txt | `find . -name names.txt` | `sort -u -- names.txt` (or `uniq`) |
| E096 | who can read config.yaml | `find . -name config.yaml` | `ls -l -- config.yaml` (or `stat`) |
| E101 | list the python processes | `find . -name '*.py'` | `ps aux | grep -i '[p]ython'` |
| E127 | make a copy of config.yaml | `find . -name config.yaml` | `cp -- config.yaml config.yaml.bak` **(exit 3 — it writes)** |

And the **reverse** misroute:

| E035 | locate train.py | `grep -nF train.py train.py` | `find . -name train.py` — "locate" is a discovery verb, not grep |

And a count misroute:

| E069 | count the warnings in train.log | `wc -l -- train.log` (counts ALL lines!) | `grep -ciF -- warning train.log` — "count the <thing>" is grep_count, not wc |

**Keep `find` winning** for: "find/list/where are the X files", "how many X
files", "what changed recently", size/name discovery. Don't break E024–E041.

## B. Four parsing bugs (each a genuine silent-error defect)

1. **E088** "what's today's date" → emits `grep -nF 's today' 's today'` (garbage).
   A fallback grep is swallowing it. Add/repair the `date` intent so
   "what time is it" / "what's today's date" / "current date|time" → `date`,
   and make sure no grep fallback fires on these.
2. **E071** "find 'deprecated' everywhere" → `grep -RnF -- deprecated deprecated`
   — the **pattern is duplicated into the path slot**. A recursive grep with no
   explicit target must use `.` (cwd), never repeat the pattern. Emit
   `grep -RnF -- deprecated .`
3. **E042** "small files under 1kb" → `-size +1024c` — the comparator is
   **inverted**. "under / less than / smaller than" → `-size -N`;
   "over / bigger / more than" → `-size +N`. Fix the mapping (E040/E041 "over"
   must stay `+`).
4. **E019** "take me to /mnt/c/Users" → `cd /mnt/c` — the absolute-path slot is
   **truncated to the first component**. Capture the full path:
   `cd -- /mnt/c/Users`. (If navigation is rebuilt in Task 26, fix it there
   instead and note it — don't fix twice.)

## C. Housekeeping

The MANIFEST sha constant in `CLAUDE.md` (`5af914bd…`) is **stale** — the
committed `testlinuxbuddy/MANIFEST.txt` now hashes to `89ba5fc4…`. Confirm the
real value and update the constant in `CLAUDE.md` so the integrity check asserts
the right hash.

## Tests & done

Add/adjust a test per named row (A + B). Full regression run — the `find`
priority change must not steal discovery requests (E024–E046) and the parsing
fixes must not regress E040/E041/E064/E067/E068. `pytest` green. Commit, don't
push. Document in LOG.md the routing rule you changed and each bug fixed.
