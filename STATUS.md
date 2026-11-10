# STATUS — LinuxBuddy

**Last updated:** 2026-11-10 (Task 33 — **file-ops win over `find` in the
session path**)

## Where we are
**v1.0.0 (rules engine) is COMPLETE** on the `v1-file-discovery` line; v2 work is
underway on branch **`v2-multiturn`**.

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

## Final evidence (Task 33)
- **368 tests pass** (was 340; +28 in `tests/test_session_fileops_routing.py`),
  **identical with and without `LINUXBUDDY_SESSION` set** (the conftest makes it
  deterministic). 15 of the 28 new tests were RED before the fix.
- **139-row single-turn sweep: 0 routing diffs vs v7** (lb_stdout/stderr/
  exit_code/outcome byte-identical) — the fix only touches the session path.
- **Sweep coverage extended:** E140–E147 added to `sweep_scenarios.csv`;
  `data/eval/sweep_results_v8.csv` written (147 rows, COMMAND 142 / ABSTAIN 5;
  new destructive rows marked `skipped-destructive-unsafe`, maze not mutated).
  Caveat: these single-turn rows would NOT have caught this bug — the session
  test file is the real guard; they close the Task-32 single-turn coverage gap.
- **Manual (real `lb`, widget session id, in maze):** the four rows → mv/rm/cp
  at exit 3; mkdir (photos & logs) and backup_copy at exit 3; discovery (fresh
  session) still `find` exit 0; file-op outside maze refused (exit 1).

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
None known. Full suite green (368), deterministic w/ and w/o `LINUXBUDDY_SESSION`.
Single-turn sweep: 0 routing diffs (v8 routing == v7), integrity preserved.
