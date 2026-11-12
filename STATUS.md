# STATUS — LinuxBuddy

**Last updated:** 2026-11-12 (Task 45 — **context-aware resolver WIRED into `lb`
(option 1.5, torch-free): novel multi-turn recovery 36%→79%, 0 single-turn
regression, destructive 3/3 abstain, live chains work**)

## Where we are
**v1.0.0 (rules engine) is COMPLETE** on the `v1-file-discovery` line; v2 work is
underway on branch **`v2-multiturn`**. **`v2_remaining_proposal.md` is the v2 plan
of record** (the never-committed `ROADMAP_V2.md` is stale — ignore it).

**Task 45 (wire context-aware resolution into the session path — option 1.5, part A).**
Productionized the Task-44 spike **inside `lb`**, torch-free; additive, fallback-only.
Three commits (descriptions, resolver module, session seam). **Awaits review.**
- **Seam:** `cli._session_dispatch` fallback branch — when the rules `fallback` AND a
  live `SessionFrame` exists AND the turn is elliptical, consult
  `session_resolver.resolve_fallback` (ONNX, torch-free) → an operate delta that
  merges into the frame → the UNCHANGED `to_command_plan → compile → gate → render`.
  `session.py` byte-identical; `onnx_encoder.py` unchanged.
- **Resolver:** embeds the CURRENT-TURN SPAN pooled from the contextual sequence
  `history . current` (not the turn alone — that was 1/14 — and not the whole blended
  embedding, Finding 3); maps a READ operate intent → max-by-size/count. The L4H4
  attention stays dev-time (figure + 98% coref). Reference = the frame's single target.
- **Descriptions enriched** (`kb/intent_descriptions.yaml`, find_largest/_smallest size
  synonyms), gated on BOTH evals: **587 single-turn 0 regressions** (CORRECT 403→404,
  per-scenario diff), multi-turn novel recovery **36%→79%**.
- **Acceptance (measured):** multiturn_eval end-to-end through real `lb` — in-vocab
  **24/24 byte-exact (0 regressions)**, **novel recovery 11/14 (79%)**, **destructive
  3/3 abstain** (0 command, invariant #6). Dogfood chains **48/49** (unchanged),
  147-sweep **0 diffs**, **0 GATE_LEAK**. Suites: main **437 passed/8 skipped**,
  `.venv-ml` **445 passed** (+ `tests/test_session_resolver.py`, 9). Fast-path purity
  held (rule-handled session turn imports no ML).
- **Live widget confirmed:** golden chain rules-handled; novel chain `pull up the csv
  files → only the ones over 2mb → which of those is heaviest` → correct
  `session_find_biggest` (rc 0); `get rid of those` → abstain (rc 1, no rm).
- **Residual:** 3 terse novel turns ("the fat one", "add them all up", "total them up")
  below t_read=0.55 — candidates for option 2 (light tuning) if pursued; deferred.
- **Decision for the owner:** approve → proceed to **B (continual learning)**, the
  missing graded concept; or request option 2 for the last-mile act gap first.
- **Not pushed.** Tasks 43–45 (proposal + spike + wire) are ahead of origin
  `v2-multiturn` (35–42 pushed). **Do not push unless Sambit says.**

**Task 44 (option-1.5 spike — attention as cross-turn reference resolver; DEV-TIME,
NOT WIRED).** Built the spike the Task-43 proposal recommended. **Nothing wired into
`lb`/`session.py`; no rules/encoder/gate/router change.** Full existing suite green
(**437 passed, 8 skipped**). **Awaits review before any wiring.**
- **Deliverables:** `data/eval/multiturn_eval.jsonl` (frozen held-out multi-turn eval
  — 34 chains / 87 turns / 42 coref, 25 in-vocab + 19 novel; leakage-clean +
  label-audited), the resolver + eval harness in `experiments/task44_spike/`, a
  stdlib guard `tests/test_multiturn_eval.py` (+5), `attention_spike_report.md`, and
  a novel-chain attention figure.
- **Numbers (best signal L4 H4):** coreference **100% phrase / 98% type-specific**;
  in-vocab **no-regression 25/25**; **novel recovery 5/14 (36%)** + novel refine 2/2;
  safety **3/3** (destructive elliptical turns all abstain, 0 commands emitted).
- **Signal finding:** the Task-43 probe's L3H1 binds to generic "files" (type-specific
  only 5%); a full sweep picks **L4H4** (98%). One example didn't generalize — the
  resolver defaults to the swept-best signal.
- **Verdict:** **coreference/reference resolution confirmed functional + interpretable
  (the real win); act-recovery is partial → needs the light touch-up (option 2),**
  gated on this frozen eval. NOT option 3. Terse "the fat one"-style size synonyms are
  the specific, fixable gap (zero-shot act cross-check, twice mis-picking *smallest*).
- **Decision for the owner:** approve option 2 (light contrastive touch-up for the act
  piece, gated on the frozen eval) + a later `session.py` wiring task for the
  coreference resolver; or keep coref+figure as the showcase and defer the rest.
- **Not pushed.** This Task-44 commit + the Task-43 proposal commit are the only ones
  ahead of origin `v2-multiturn` (Tasks 35–42 are pushed). **Do not push unless
  Sambit says.**

**Task 43 (DESIGN PROPOSAL — attention-based context retention; NO implementation).**
Research/design task; nothing in src/rules/encoder/gate/session/KB changed.
Deliverable `attention_context_proposal.md` (+ a throwaway probe in
`experiments/task43_attention/`), **awaits review before any build**.
- **Probe findings (on the real fine-tuned model):** (1) cross-turn attention is
  real & visualizable — the pronoun "one" in "show the biggest **one**" attends to
  "csv files" from turn 1 (0.626); the showcase figure exists
  (`experiments/task43_attention/attention_map.svg`). (2) context helps resolve
  elliptical *objects* ("count them"→count_files once the history is seen). (3)
  **cautionary:** naive whole-embedding concatenation *dilutes* the current turn's
  act ("biggest one" gets outvoted by the turn-2 filter) — so don't match the whole
  pooled embedding for the decision.
- **Recommendation:** spectrum **option 1.5** — attention owns **coreference/
  reference resolution** (where it wins, zero-shot, no new data) + the figure; the
  rules `SessionFrame` keeps **state accumulation** and **dialogue-act/modifier**
  (the 48/49 path the encoder would regress). Dialogue-act head stays deferred
  (49 turns, acts imbalanced). Safety unchanged (gate + exit-3 + destructive
  asymmetry intact).
- **Decision for the owner:** approve option 1.5 + the thin-slice spike, or overrule
  toward option 3 (bespoke cross-attention head — more standout, but needs data we
  lack and risks the 48/49 baseline).
- **Tasks 35–42 are pushed to GitHub** (origin `v2-multiturn` at the Task-42
  commit). This Task-43 proposal commit is the only one ahead of origin. **Do not
  push unless Sambit says.**

**Task 42 (workstream #1a — the rules coverage-check).** First v2 implementation
after the proposal. Froze the 587-scenario dogfood as a static, eval-only benchmark
(`data/eval/dogfood_eval.jsonl`, separate from train; `dogfood500.py` reads it), then
added the coverage-check so a bare filename stops hijacking into a confident wrong
`find`/`grep`.
- **Two surgical rule changes** (no encoder/threshold/gate/router change): gate
  `find_by_name` on `_discovery_requested` (abstain when no discovery cue → encoder
  seam), and make `_grep_pattern` filename-aware (a filename's all-caps/log word is
  not a grep pattern).
- **Measured delta (frozen eval):** MISROUTE_SILENT_DROP **99→51** (−48), CORRECT
  **382→403** (+21), encoder firings **31→50** (reach up), ABSTAIN_GAP 38→62 (freed
  hijacks now honestly abstain). **0 CORRECT regressions** (genuine discovery
  unchanged), **147-sweep 0 diffs**, **0 GATE_LEAK** (safety intact).
- **Housekeeping:** `[ml]` extra in `pyproject.toml` (`pip install -e '.[ml]'`
  reproduces the hybrid; pure-rules still the default). `*:Zone.Identifier` already
  gitignored.
- **Follow-ups logged, NOT done here:** #1b multi-constraint slot-filling
  (size+time, multi-extension) and #1c definite-reference / bare-name resolution
  (e.g. `locate notes`, `the config file`). The residual MISROUTE (51) is now mostly
  other parsers (head/cd/echo grabs) + these two classes.
- **Do NOT push yet** (push after #1 fully lands + the `v2.0.0` tag). **9 commits
  unpushed** (35–42).

**Task 41 (inspect + measure + propose — NO implementation).** Confirmed the live
`lb` reaches the ONNX encoder, read the as-built code (`asbuilt_summary.md`), ran a
**587-scenario diversified dogfood** through the real hybrid (`tests/dogfood500.py`
→ `dogfood500_diversity.md`), and wrote **`v2_remaining_proposal.md`** (awaits
review before any build).
- **Dogfood:** 587 scenarios, leakage-clean vs train (0 dups), all 85 intents
  (27/27 zero-data), diversity self-audited. **Behaved-as-expected 75.5%**
  (CORRECT 382 + ABSTAIN_OK 61). **0 GATE_LEAK** (safety intact; outside-maze
  destructive refused 11/12, 12th safely degraded to a read). Multi-turn 48/49.
- **Headline problem:** **MISROUTE_SILENT_DROP 99 (17%)** — rules emit a confident
  wrong command (88 = "filename-hijack" → catch-all `find`/`grep`; 11 =
  constraint-drop). The **encoder fired on only 5.3%** (87% correct when it did):
  it's consulted only on *abstain*, but the rules rarely abstain — they guess.
- **#1 lever (proposed):** a rules **coverage-check** (abstain instead of
  half-right) to both kill the dangerous class and unlock the encoder.
- **Proposed order:** 1 rules-robustness → 5 packaging → 3 continual-learning
  (the missing graded concept) → 4 polish/tag → 2 (defer learned dialogue-act;
  rules session layer works at 98% on ~40 turns of data).
- **Decision for the owner:** approve the sequence; optionally freeze the 587-set as
  a tracked real-eval corpus under `data/eval/`. **7 commits unpushed** (35–41).
- **Open:** `ROADMAP_V2.md` is referenced by task specs but absent from the repo
  (only a stray `:Zone.Identifier`); using `ROADMAP.md`.

**Task 40 (abstain-path latency — ONNX, torch-free runtime; PERFORMANCE only).**
Same behaviour, much faster cold start — **no intent/threshold/gate/rule/router
change**. Main suite **409 pass + 13 skipped**; `.venv-ml` **21 pass**. All five
Task-39 guardrails re-verified.
- **Profile (Part A):** imports were ~7.1s of the old ~10s cold path (ST 4.5s,
  torch 1.25s, transformers 1.14s); inference ~5ms. So the fix is dropping imports.
- **ONNX export:** fine-tuned MiniLM → `torch.onnx` (optimum's exporter is broken on
  torch 2.15, bypassed) → fp32 ONNX; pooling/normalize reimplemented in numpy to
  match ST exactly. Runtime (`ml/onnx_encoder.py`) imports only onnxruntime +
  tokenizers + numpy — torch/transformers/ST never load at runtime.
- **Fidelity:** int8 cosine 0.958 (< 0.999 gate) → shipped **fp32**, cosine
  **1.00000** vs torch; **decision parity 15/15** (same intent + emit/abstain).
- **Latency:** cold abstain **~258ms** (was ~10s, **~40× faster**), under the ~2s
  target → **no daemon needed**; fast rule-hit path ~49ms, imports no ML stack.
- **Degradation:** now also covers onnxruntime/tokenizers/.onnx absent → pure v1
  (the main 3.14 venv has neither numpy nor onnxruntime, so the full suite proves
  it) + an explicit artifact-absent test.
- **Milestone:** good checkpoint — **this branch can be pushed** (owner's call).
- **Next:** multi-turn dialogue-act head / unify `session.classify()` (old Phase 2).

**Task 39 (hybrid — encoder as rules fallback; FIRST runtime-path change).**
Single-turn, intent-only. The encoder is consulted at ONE seam
(`cli._run_single_turn`, where the rules abstain) and its intent flows through the
EXISTING slot filler → planner → renderer → gate. Main suite **408 pass + 11
skipped**; `.venv-ml` **18 pass**. All five guardrails verified by
`tests/test_hybrid.py`.
- **0 regressions:** 147-sweep rule-handled rows byte-identical encoder on vs off.
- **Safety:** destructive-on-nonsense **0/22**; read/destructive asymmetry via two
  thresholds (`t_read=0.55`, `t_destructive=0.68`+`margin_min=0.05` in
  `ml_config.yaml`); invariant-#6 guard stops match-everything finds.
- **Graceful degradation:** missing model/deps or `LINUXBUDDY_ENCODER=0` → pure v1;
  fast path never imports torch (asserted).
- **Coverage (end-to-end, `hybrid_eval_report.md`):** 10/14 rules-abstain probe
  phrasings now resolve to meaningful commands (ls -la, ps aux, find by type/time).
- **Latency:** fast path ~0.12s (unchanged); cold abstain path was ~10s/process —
  **fixed in Task 40 (ONNX): now ~0.26s, no daemon.**
- **Milestone:** good checkpoint — **this branch can be pushed** (owner's call).

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
