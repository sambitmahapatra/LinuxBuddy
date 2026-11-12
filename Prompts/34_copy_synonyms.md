# Task 34 — copy synonyms + no-destination copy (the last hand-patch before Phase 2)

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Branch `v2-multiturn`. Small
synonym fix. This is deliberately the LAST manual synonym patch — the remaining
phrasing tail is Phase-2 (encoder) territory, not more rules.

## Evidence (real `lb`, session path)

| request | got | must emit |
|---|---|---|
| create a copy of sales.csv | `find . -name sales.csv` | `cp -- sales.csv sales.csv.bak` (exit 3) |
| create a copy of sales.csv in this folder | `find . -name sales.csv` | `cp -- sales.csv sales.csv.bak` (exit 3) |
| create a copy of MANIFEST.txt in this folder | `grep -nF -- MANIFEST MANIFEST.txt` | `cp -- MANIFEST.txt MANIFEST.txt.bak` (exit 3) |

Root cause: the copy intent matches "copy X to Y" and "make a copy of X", but not
"**create** a copy of X" / "duplicate X". Unmatched → falls through to the greedy
`find`/`grep` fallback (and in the session path the `_FILEOP_LEAD_RE` guard
doesn't fire because the head verb is "create", unrecognized for copy).

## Fix

1. **Copy cues** — add as copy-intent triggers (single-turn router AND the session
   `_FILEOP_LEAD_RE` guard, so both paths agree):
   - "create a copy of X", "make a copy of X" (confirm this still works),
     "duplicate X", "make a duplicate of X", "back up X" (→ copy, not archive,
     when it's a single file).
2. **No-destination copy** — when copy has a source but no "to Y":
   - default to `cp -- X X.bak` (append `.bak`).
   - "in this folder" / "in this folder itself" / "here" → same (cwd is implied).
3. Keep "copy X **to** Y" → `cp -- X Y` unchanged. All copy variants are
   write ops → **exit 3, maze-gated**.

## Tests

- "create a copy of sales.csv" → `cp -- sales.csv sales.csv.bak`, exit 3
- "create a copy of X in this folder" → same
- "duplicate report.csv" → `cp -- report.csv report.csv.bak`, exit 3
- "make a copy of config.yaml" → still works (don't regress Task 25/32)
- "copy a.txt to b.txt" → `cp -- a.txt b.txt` (unchanged)
- Outside maze → refused.
- Regression: `find`/`grep` still win for their real cases (discovery, search);
  139 sweep 0 routing diffs; multi-turn chain intact.

## Done when

The three evidence rows emit `cp` at exit 3, no `find`/`grep` leakage, discovery
unregressed, `pytest` green. Commit on `v2-multiturn`. Document in LOG.md +
STATUS.md — and add a one-line note that further synonym gaps are deferred to the
Phase-2 encoder rather than patched individually.
