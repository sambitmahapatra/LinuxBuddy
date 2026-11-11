# STATUS — LinuxBuddy

**Last updated:** 2026-11-11 (Task 38 — **v2 Phase 1: base-model bake-off +
contrastive fine-tune; measurement/model only, no source changes**)

## Where we are
**v1.0.0 (rules engine) is COMPLETE** on the `v1-file-discovery` line; v2 work is
underway on branch **`v2-multiturn`**.

**Task 38 (Phase 1 — bake-off + contrastive fine-tune; model/measurement only).**
The Siamese step. **No rules/router/planner/KB changes; nothing wired into `lb`.**
All ML in `.venv-ml`. Suite **403 pass + 8 skipped** (main venv; ML tests run in
`.venv-ml`, 10 pass).
- **VERDICT: WIREABLE.** Fine-tuned MiniLM-L6 clears every bar on held-out data:
  **gap recovery 93%, nonsense FP 3%, val top-1 72% / top-3 89%**, zero-data tail
  intact (top-3 88%→96%). Abstain = train-fit threshold **T\*=0.55** (the logistic
  gate, option b, is equivalent).
- **Bake-off (Part A):** 5 bases, zero-shot, each with its documented input
  convention. No base separated nonsense zero-shot (best MiniLM-L6 FP 31%@gap85%;
  gte/e5 un-thresholdable). Winner = `all-MiniLM-L6-v2` (`bakeoff_report.md`).
- **Fine-tune (Part B):** MultipleNegativesRankingLoss, seed 42, 3 epochs, lr 2e-5,
  CPU (~1min; GPU had no matching torch wheel — CPU fallback, deploy is CPU anyway).
  Checkpoint `models/ft-minilm-l6/` **gitignored** (regenerates from script+seed+data).
- **Integrity:** the Task-36 split had salted train.jsonl with 21/27 gap phrasings
  (+2 val); `build_pairs()`/gate now exclude all gap/val via `heldout_texts()` (a
  test asserts it). Gap recovery stayed 93% held-out. Nonsense FP measured on a
  fresh clean probe + held-out val abstains; thresholds fit on train not eval.
- **Next (if approved):** wire the fine-tuned encoder as the rules fallback in `lb`
  (encoder runs only after the rules abstain; intent-only; slots stay rule-based).
  Report: `finetune_report.md`.

**Task 37 (Phase 1 spike — zero-shot bi-encoder; measurement only).** Measured a
*pretrained* MiniLM (all-MiniLM-L6-v2, CPU) against the 85 intent descriptions,
NO fine-tuning. **No rules/router/planner/KB changes**; all ML is isolated in
`.venv-ml` (uv Python 3.12 + CPU torch) so `lb`'s 3.14 venv is untouched. Suite
**402 pass + 4 skipped** (main venv; model tests run in `.venv-ml`).
- **VERDICT: NEEDS FINE-TUNING** at T\*=0.275. Space is roughly right but not
  wireable as-is.
- **Gap set: 23/27 (85%) recovered at top-1**; **val top-1 58% / top-3 77%**;
  **nonsense abstain 69% (31% FP)**. Nonsense is NOT separable by absolute cosine
  threshold, and the top1−top2 margin doesn't help — the main blocker. Failures
  are neighbouring-intent confusions → what contrastive fine-tuning fixes.
- **Integrity note:** removed example-anchor leakage (16 anchors were verbatim
  gap/val test utterances) before measuring; numbers above are honest post-fix.
- **Durable artifact:** `kb/intent_descriptions.yaml` (all 85, synonyms folded in)
  — reused by fine-tuning and Phase-3. Report: `zeroshot_spike_report.md`.
- **Next (if approved):** contrastive fine-tune on the Task-36 pairs, re-run the
  `eval_zeroshot` harness to measure the lift, then wire as the rules fallback.
  The 27 zero-data intents are description-served (not in the val set; judge via a
  broader eval / the targeted collection pass).

**Task 36 (Phase 0 — training data; data only).** Built the labeled corpus for
the Phase-1 intent encoder. **No source/rules/KB changed** — added
`src/linuxbuddy/ml/` (reproducible generator + KB label builder) and tracked
`data/` artifacts. Reproducible: `python -I -m linuxbuddy.ml.make_dataset` (seed
20261111). **Full suite 401 pass** (389 + 12 new `tests/test_data.py`).
- **Label space (frozen):** 85 KB intent ids (plain `frame.intent` keys, not
  domain-dotted) + 5 dialogue acts + `_ABSTAIN` → `data/label_space.json`.
- **Drift handled:** sweep's intent column is a different coarser vocabulary
  (57/59 don't match the KB). Reported it (drift guard), owner approved
  reconciling by *runtime behavior* (label = what `lb` actually fires). Auditable
  `data/sweep_intent_map.json` committed.
- **Corpus:** single-turn train **688** / val **55** (`_ABSTAIN` ~12%); multi-turn
  **40/9** turns across 20 chains. Augmentation is train-only + group-level (no
  leakage, asserted by tests). `data/DATA_CARD.md` has the full balance.
- **Phase-1 watchlist:** **27 of 85 intents have ZERO single-turn data** (sweep+
  stress never exercised them); 45 more have <3 raw train seeds. Listed in the
  data card for the confusion matrix. Owner has seen the class balance (their gate
  before committing to the encoder).
- **Next (Phase 1):** the hybrid router + intent encoder trains on these files.
  The encoder can only fall back for the 58 covered intents until the corpus grows.

**Task 35 (stress test — testing only).** Added `tests/stress_test.py`: a 5-agent
adaptive harness (Environment Builder / Explorer / Adversary / Session Tester /
Judge) that generates and adapts its own test cases. One run = **170 tests,
84.1% behaved as a reasonable user expects, 0 gate leaks, session 32/32**. **No
LinuxBuddy source was modified.** Outputs (`stress_test_results.csv`,
`stress_test_report.md`) are gitignored as ephemeral — regenerate with
`python3 tests/stress_test.py`. It cleans up `testlinuxbuddy/stress/` after each
run. The harness separates **bugs to fix** from **Phase-2 encoder territory** —
see "Findings from the stress test" below.

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

## Findings from the stress test (Task 35) — for triage, not yet actioned
**Routing/rendering (5, all read-only → low-risk, but wrong command emitted):**
- `where are the python scripts` → `command -v python3` (python-installed check
  steals the find).
- `list all python files` → `ls -la` (list_all beats find_by_type; cf. `find all
  the python files` works).
- `show the permissions of notes.txt` → `head -n 10` and `show me the stats for
  notes.txt` → `head` (inspection verbs misroute to preview).
- `check the syntax of src/main.py` → `find . -name main.py` (py_syntax phrasing
  unrecognised).

**Rules ceiling → Phase-2 encoder corpus (22, NOT to patch by hand):** abstained
reads (`what processes are running`, `list everything here`, `where are the
spreadsheets`, `what changed in the last day`) + destructive synonyms that
degrade *safely* to a find (`erase/nuke/wipe/discard/del/throw away`,
`clone/replicate`, `set up a folder`). The full list is the training signal.

**Containment observation (for the human — would change a settled rule):** the
gate is cwd-based by design, so `delete ../../../etc/hosts` run *inside* the maze
emits `rm -- ../../../etc/hosts` at rc=3 — a `..` target escapes the maze. Not a
breach of the current contract (and `lb` never executes), but a prod-mode
hardening item. No change made.

## Open bugs
None in shipped behaviour. Full suite green (389), deterministic w/ and w/o
`LINUXBUDDY_SESSION`. Sweep: 0 routing diffs (147 rows == v8), integrity
preserved. The 5 routing observations above are stress-test findings for triage
(read-only, non-blocking), not regressions.
