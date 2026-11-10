# STATUS — LinuxBuddy

**Last updated:** 2026-11-10 (Task 32 — **file-management intents + nested nav**)

## Where we are
**v1.0.0 (rules engine) is COMPLETE** on the `v1-file-discovery` line; v2 work is
underway on branch **`v2-multiturn`**.

**New capabilities (Task 32), all deterministic rules.** A `file_management`
domain: **move/rename** (`mv -- X Y`), **copy-to-dest** (`cp -- X Y`, generalized
from the old X.bak duplicate), **delete** (`rm -- X`), **mkdir** (noun-then-name
phrasings → the existing `make_dir`). All destructive → exit 3, maze-gated, real
command rendered through the unchanged v1 pipeline; delete is plain `rm --` (no
`-f`/`-i`) with the review-before-Enter + gate as the safety net. Definite refs
grew: "the old logs" → `*.log`, "the image" → `*.{jpg,png}`. **Nested navigation**
("go to X inside Y") resolves Y to an ancestor (absolute) or a child dir
(relative), else abstains; repeated path segments disambiguate by which ancestor
actually contains X.

**v2 multi-turn — now actually works in the real widget (Task 31 bugfix).** The
Task-30 spike's store was keyed on `os.getppid()`, but the Ctrl-G widget runs `lb`
inside a `$(lb …)` command substitution — a fresh subshell with a new PID each
press — so every turn got its own session file and nothing accumulated (turn 2
dropped turn 1's `-name/-size`). Fixed by keying on a stable, exported
per-terminal id: the widgets now `export LINUXBUDDY_SESSION="lb-$$-$(date +%s%N)"`
and `session.store_key()` derives the file name from that (sanitized), falling
back to `getppid()` only when the env id is absent. `save()` also reaps stale
session files past the TTL. TTL / reset-word / cwd-change reset unchanged.

The target 3-turn chain now accumulates end-to-end through real `$(lb …)`
subshells in the maze:
`find CSV files larger than 100MB` → `find . -name '*.csv' -size +100M`; refine
`only the ones modified yesterday` → `… -daystart -mtime 1` (filters KEPT);
operate `show the biggest one` → `… -printf '%s\t%p\n' | sort -rn | head -1`.
Multi-turn is still opt-in (the env id); single-turn is byte-identical.
**No transformer/torch** — the encoder is Phase 2.

v1 release artifacts (Task 29): version `1.0.0`, `README.md`, `CHANGELOG.md` on
the v1 line. **Still ready for the human to tag `v1.0.0` and push** — not tagged.

## Final evidence
- Sweep: **COMMAND 134 / ABSTAIN 5** of 139, integrity PASS, **0 regressions**.
  See `data/eval/sweep_results_v7.csv` (routing byte-identical v4→v7; v1–v6 kept
  too). The Task-32 intents aren't in the 139 yet (see "open items").
- **340 tests** pass (281 v1 + 27 v2 session + 32 file-ops/nested-nav). The
  cross-process test `test_env_keyed_persistence_across_subshells` reproduces the
  Task-31 subshell bug (FAILS under getppid keying, PASSES with env-id keying).

## The honest-5 residual (abstain by design)
- **E056** "tail the output" / **E060** "what is this file" — generic target, no
  file named.
- **E073** "sort this list" — genuinely vague, no file.
- **E138/E139** "install the requests package" / "add pandas to my environment" —
  correct abstains: runtime network is invariant #1.
These generic/ambiguous/context-dependent cases are the motivation for v2.

## Next — v2
- **Phase 1 (multi-turn mechanic): DONE** (spike in Task 30; keying fixed in Task
  31 so it works in the real widget). Scope to grow next: more operate modifiers
  (smallest / sort / first-N), more refine constraints (name/path/type),
  coreference beyond elided "one/them/it".
- **Phase 2 (the model):** the transformer/attention intent encoder, Siamese /
  zero-shot matching for unseen phrasings, a continual-learning feedback loop.
  Intent-only — slot extraction stays rule-based; no runtime network dependency.
  The honest-5 residual above is still its motivation.

## Open items / for the human
- **`ROADMAP_V2.md` does not exist yet** (referenced by the Prompts/30–32 "read
  first" lists). Tasks were built to the inline spec. Worth writing as a task.
- **Sweep coverage for the Task-32 intents**: the move/copy/delete/mkdir +
  nested-nav cases aren't in the 139-row `sweep_scenarios.csv` (prompt marked
  this optional). Adding ~10 rows would regress them in future sweeps.
- **Manual Ctrl-G redraw check** in a fully interactive bash: the Task-31
  persistence bug is covered by an automated cross-process test and verified via
  real `$(lb …)` subshells, but a human pressing Ctrl-G confirms the Readline
  redraw (and the new destructive warning on the file-management ops).
- Tag `v1.0.0` + push the v1 line (carried from Task 29).

HANDOVER.md stays frozen as founding context; this file is the living snapshot.

## Open bugs
None known. Full suite green (340). Single-turn sweep: 0 regressions (v7==v6),
integrity PASS.
