# STATUS — LinuxBuddy

**Last updated:** 2026-11-10 (Task 34 — **copy synonyms; last manual synonym
patch**)

## Where we are
**v1.0.0 (rules engine) is COMPLETE** on the `v1-file-discovery` line; v2 work is
underway on branch **`v2-multiturn`**.

**Task 34 (synonym fix — the LAST manual one).** "create a copy of X" /
"duplicate X" / "make a duplicate of X" / "back up X.ext" are now copy intents
(`cp -- X X.bak`, or `cp -- X Y` with a destination), rendered at exit 3 and
maze-gated. Three coordinated edits so single-turn and session agree: `_ARC_COPY_RE`
gained the create/duplicate-of/back-up cues (back-up only for a single file with
an extension; a folder still → `create_archive`); `_parse_text_and_logs` now
bails to the copy parser when a grep pattern came only from an ALL-CAPS filename
stem (the "MANIFEST.txt" theft), placed after the distinct/sort checks so dedup
is unaffected; and the session `_FILEOP_LEAD_RE` gained `duplicate` / `back up` /
`make|create a copy|duplicate` leads. **Deliberately the last hand-written
synonym rule** — the remaining phrasing tail is Phase-2 encoder territory, not
more rules.

**Task 33 (bugfix).** The Task-32 file-management verbs (move/copy/delete/rename)
were emitting `find …` (exit 0) instead of the real destructive command (exit 3)
— but ONLY in the multi-turn widget path. Single-turn (`nlu.parse` →
`cli._run_single_turn`) was always correct. Root cause (contrary to the prompt's
guess about router order, which Task 32 had already fixed): `session.classify()`
treated ANY request carrying a filename extension as a composable `find`-by-type
query, so "delete old.log" became `find . -name '*.log'`. `mkdir "photos"`
survived only because it has no extension; `"make a folder logs"` was hijacked
too. **Fix:** a `_FILEOP_LEAD_RE` guard in `classify()` — a file-management verb
at the HEAD of the request (move/copy/rename/delete/remove/trash/put/get rid of,
bare mv/cp/rm, "make a copy", make/create/new/add a folder|dir|directory) now
returns `fallback` before the composable-find and operate/refine checks, so the
v1 single-turn path routes it. Discovery verbs are disjoint → discovery
unregressed.

**Test hygiene:** new `tests/conftest.py` autouse-unsets `LINUXBUDDY_SESSION` so
the single-turn tests are deterministic even when run from the owner's
widget-active bash (that env is what hid this bug and was failing 6 single-turn
tests spuriously).

### Earlier v2 state (unchanged, carried forward)
Task 32 added the `file_management` domain: move/rename (`mv -- X Y`),
copy-to-dest (`cp -- X Y`), delete (`rm -- X`), mkdir, plus nested navigation
("go to X inside Y"). All destructive → exit 3, maze-gated. Task 31 fixed the
multi-turn store key (per-terminal `$LINUXBUDDY_SESSION`, not `getppid()`) so the
3-turn chain accumulates end-to-end through the real `$(lb …)` subshells.
**No transformer/torch** — the encoder is Phase 2.

## Final evidence
- **389 tests pass** (Task 34 added `tests/test_copy_synonyms.py`, +21; Task 33
  added `tests/test_session_fileops_routing.py`, +28), **identical with and
  without `LINUXBUDDY_SESSION` set** (the conftest makes it deterministic).
- **147-row sweep: 0 routing diffs vs v8** (the 139 originals + Task-33's
  E140–E147). Task 34 shifted no existing routing, so no new results file.
- **Sweep baseline:** `data/eval/sweep_results_v8.csv` (147 rows, COMMAND 142 /
  ABSTAIN 5; Task-33's new destructive rows `skipped-destructive-unsafe`).
- **Manual (real `lb`, widget session id, in maze):** Task 34 — all copy
  synonyms → `cp … .bak` (or `cp -- X Y`) at exit 3; `remove duplicate lines` →
  `sort -u` (0, not copy); `back up the project` → tar (3). Task 33 — move/
  delete/rename/mkdir at exit 3; discovery still `find` (0); refused outside maze.

## The honest-5 residual (abstain by design, unchanged)
- **E056** "tail the output" / **E060** "what is this file" — generic target.
- **E073** "sort this list" — vague, no file.
- **E138/E139** "install the requests package" / "add pandas …" — correct
  abstains (runtime network is invariant #1).
Motivation for the v2 model.

## Next — v2
- **Phase 1 (multi-turn mechanic): DONE** (Task 30 spike; keying fixed Task 31;
  file-ops no longer hijacked by the session find-composer, Task 33). Scope to
  grow: more operate modifiers (smallest / sort / first-N), more refine
  constraints (name/path/type), coreference beyond elided "one/them/it".
- **Phase 2 (the model):** transformer/attention intent encoder, Siamese/
  zero-shot matching, continual-learning feedback loop. Intent-only; slot
  extraction stays rule-based. The honest-5 residual is its motivation.

## Open items / for the human
- **`ROADMAP_V2.md` still does not exist** (referenced by Prompts/30–33 "read
  first"). All v2 tasks built to the inline spec. Worth writing as a task.
- **Manual Ctrl-G redraw check** in a fully interactive bash — the one remaining
  human confirmation (Readline redraw + the destructive warning on file-ops).
  The persistence + routing are covered by automated cross-process/session tests.
- Tag `v1.0.0` + push the v1 line (carried from Task 29; still not tagged).

HANDOVER.md stays frozen as founding context; this file is the living snapshot.

## Open bugs
None known. Full suite green (389), deterministic w/ and w/o `LINUXBUDDY_SESSION`.
Sweep: 0 routing diffs (147 rows == v8), integrity preserved.
