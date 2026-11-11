# v2 Remaining-Work Proposal — for review before implementation (Task 41)

*Inspect + measure + propose. Nothing here is built. This proposal is grounded in
the as-built code (`asbuilt_summary.md`) and the 587-scenario live dogfood
(`dogfood500_results.csv`, `dogfood500_diversity.md`). Approve/adjust the sequence
at the end before any implementation task.*

## Headline evidence (the 587-scenario dogfood through the live hybrid)

- **Leakage-clean** vs `train.jsonl` (0 duplicates), all **85 intents** covered
  (27/27 zero-data), diversity self-audited; run through the real `lb` (encoder
  confirmed live: `ps aux` with the "interpreted" marker).
- **Behaved-as-expected: 443/587 = 75.5%** (CORRECT 382 + ABSTAIN_OK 61).
- **Safety is intact — the top priority held:** **0 GATE_LEAK**; 11/12
  outside-maze destructive probes refused (the 12th safely *degraded to a read*,
  `find`, not a destructive command); no destructive command emitted at the wrong
  exit code; destructive synonyms that aren't recognised fall to a harmless read,
  never an unflagged `rm`. The asymmetric-abstain invariant holds in the wild.

| judgment | n | % | what it means |
|---|---|---|---|
| CORRECT | 382 | 65.1% | right command, right exit |
| MISROUTE_SILENT_DROP | **99** | **16.9%** | rules emitted a confident **wrong/partial** command |
| ABSTAIN_OK | 61 | 10.4% | correctly abstained (vague/nonsense) |
| ABSTAIN_GAP | 38 | 6.5% | abstained where a command existed (phrasing gap) |
| WRONG_TARGET | 4 | 0.7% | right family, wrong slot/reference |
| ENCODER_MISFIRE | 2 | 0.3% | encoder fired the wrong intent |
| OVEREAGER | 1 | 0.2% | emitted where abstain was right |
| GATE_LEAK / CRASH | 0 | 0% | — |

- **The central architectural finding:** the encoder fired on only **31/587
  (5.3%)** of requests, and was **right 27/31 (87%)** when it did. It is
  hamstrung not because it's weak but because **the encoder is only consulted on a
  rules *abstain*** (`cli._run_single_turn`), and the dominant failure mode is the
  opposite — the rules emit a *confident wrong command* (MISROUTE, 99 rows), which
  never reaches the encoder. **The single biggest lever is not a better encoder; it
  is making the rules abstain instead of guessing, so the hybrid can catch the
  miss.**

## The MISROUTE class, decomposed (the dangerous 99)

- **88 = the "filename-hijack".** When the operation verb isn't recognised for a
  request that names a concrete file, the catch-all `file_discovery` parser (it's
  last in `_ROUTER`) grabs the filename and emits a `find`/`grep` at exit 0. Real
  examples from the run:
  - `stat notes.txt` → `find . -name notes.txt`
  - `identify model.pkl` → `find . -name model.pkl`
  - `delete error.log` → `grep -niF -- error error.log` (a destructive request
    became a text search — wrong, but safely rc 0)
  - `execute src/utils.py` → `find . -name utils.py`
  - `arrange the lines of README.md in order` (sort) → `grep -nF -- README README.md`
  These are the dangerous class the brief named: a Linux-new user sees a plausible
  command and runs it, getting a silent no-op or the wrong answer — and the encoder
  never sees it because the rules didn't abstain.
- **11 = constraint-drop.** The single-turn path *does* compose `type + one of
  {size,time}` (verified: `find . -type f -name '*.csv' -mtime -7`). It drops: the
  **second of {size,time}** (size returns first in the precedence, so a co-occurring
  time filter is lost) and the **second extension** ("csv and json" → one glob).
  Narrower than first feared, but real.

Everything below maps a workstream to this evidence.

---

## 1. Rules robustness

**Findings / evidence.** MISROUTE_SILENT_DROP = 99/587 (17%): 88 filename-hijack +
11 constraint-drop. WRONG_TARGET = 4 (definite-reference → literal token, e.g. "the
config file"→ a literal `config`). ABSTAIN_GAP = 38 (6.5%) are phrasings that
abstained where a command exists (e.g. "gzip the big log file", "point me at the
fattest files", and bare commands like `ls`/`df`/`ps`). Code roots:
`nlu._ROUTER` ordering (file_discovery is the catch-all); the size-before-time
precedence in `_parse_file_discovery` (`nlu.py:394`); `_detect_ext` returning a
single extension; `_DEFINITE_GLOBS` only covering type-implying references.

**Recommended approach (in priority order).**
1. **A coverage-check / confidence floor before emit (highest leverage).** Before
   `file_discovery` emits a bare `find -name <token>`/`grep`, require positive
   evidence that discovery was actually *asked for* (a discovery verb / "where"/
   "which"/"how many"), not merely that a filename is present. When an operation
   verb is present but unrecognised (stat/delete/sort/run/…), **abstain** instead
   of degrading to find — which hands the row to the encoder (87% correct when it
   fires). This directly converts much of the 88-row filename-hijack class from
   "confident wrong" into "encoder gets a shot / honest abstain". *This is the one
   change that most increases the hybrid's value.*
2. **Multi-constraint slot-filling in single-turn:** keep both of {size,time} (and
   multiple extensions) instead of the precedence early-return — reuse the
   `SessionFrame` compositional model that already composes correctly multi-turn.
   Addresses the 11 constraint-drops.
3. **Definite-reference for generic nouns** ("the config file", "the main script")
   via the cwd listing — addresses WRONG_TARGET (4) and some ABSTAIN_GAP.
4. **Synonym + apostrophe-UX cleanup** is explicitly *lower* priority: per
   STATUS/CLAUDE.md, Task 34 was the last manual synonym rule — the encoder is the
   intended home for synonym breadth. Fix the apostrophe/shell-line mangle (a UX
   correctness bug), but push synonym coverage to workstream 3, not more rules.

**Scope.** Medium. (1) is a contained guard in the router + a new abstain path;
(2) is a refactor reusing existing `session` composition; (3) extends an existing
table. Each is a few focused PRs with the 147-sweep as the regression floor and
this 587-set as the new acceptance eval.

**Risks.** (1) could over-abstain and *lower* single-turn coverage if the "was
discovery asked for" test is too strict — must be measured against the 147-sweep
(0 regressions) AND this 587-set (CORRECT must rise, not fall). (2) risks changing
rule-handled rows — gate it on the sweep byte-identity test.

**Graded-concept mapping.** None directly (this is classical NLP robustness), but
it is the **prerequisite** that lets the Attention encoder (#2/#3) actually help —
without it the encoder stays at 5% reach.

---

## 2. Multi-turn encoder integration (dialogue-act head)

**Findings / evidence.** The **rules-based** `session.classify()` performed very
well on the 22 varied chains: **48/49 turns correct** (the one "miss" was "find
files" with no constraint correctly abstaining, then refined). So the current
rules dialogue-act detector (reset→new→operate→refine→fallback) is **not a bottleneck
today**. Data reality (DATA_CARD): only **40 labeled multi-turn train turns** across
20 chains, dialogue acts imbalanced (new 23 ≫ refine 7 / operate 9 ≫ reset 6 /
fallback 4). The encoder already reaches multi-turn *indirectly*: a session
`fallback`/uncomposable turn routes to `_run_single_turn`, which consults the encoder.

**Recommended approach.** **Do NOT learn the dialogue-act head yet.** With ~40
turns it would be data-starved and would regress a working 98% rules path. Instead:
keep dialogue-act detection in rules, and let the encoder own **intent + reference
resolution** on the turns that fall back to single-turn (where #1's coverage-check
will now route more turns productively). Revisit a learned dialogue-act head only
after continual learning (#3) grows the multi-turn corpus to a few hundred
real turns. If a unification is wanted sooner, the lower-risk target is unifying
the *intent* decision (one encoder for single- and multi-turn intent) while leaving
act detection rules-based.

**Scope.** Small now (a documented decision + wiring the encoder into the
multi-turn fallback intent path, already mostly present). Large later (learned act
head) — deferred behind data.

**Risks.** Learning the act head now = near-certain regression of a 98% path on
40 examples. Deferring is the low-risk call.

**Graded-concept mapping.** Attention/Siamese (#1,#2) — the encoder handling
multi-turn *intent* exercises the graded encoder on a second NLU path without a new
model.

---

## 3. Continual learning (graded concept #3 — not yet started)

**Findings / evidence.** This is the missing graded concept and the natural home
for everything workstreams 1–2 defer (synonym breadth, zero-data-intent coverage,
the 38 ABSTAIN_GAP phrasings, the 88 filename-hijack phrasings once #1 makes them
abstain). We now have the two assets a credible loop needs: a **regression floor**
(the 147-sweep, byte-identity) and the **seed of a real held-out eval** (this
leakage-clean 587-set across all 85 intents).

**Recommended approach — a grow-from-use pipeline (targeted, grounded, measured):**
1. **Feedback log of mispredictions at runtime** — when the hybrid abstains, or
   when the user edits/rejects the emitted command, append the (request, context,
   outcome) to a local, offline log. No network, no auto-training.
2. **Periodic, human-gated re-fine-tune** — batch the logged misses, label them
   (the KB label space is fixed), fold into `train.jsonl`, re-run the Task-38
   fine-tune (seed-pinned, ~1 min CPU).
3. **Promote the 587-set to a tracked real-eval corpus** (see "tracking" below) and
   report every re-tune against it + the 147-sweep regression floor + the
   nonsense-FP safety metric. A re-tune ships only if: sweep 0-diff, nonsense FP
   stays ≤ target, and the 587-set CORRECT rises.
4. **Explicitly NOT a synthetic dump** — grow from *real* logged misses and the
   587 held-out set, never a large generated corpus (the Task-36 augmentation cap
   discipline carries over).

**Scope.** Medium–large (the biggest single workstream), but stageable: the
feedback log is small and independent; the re-tune harness already exists
(`ml/finetune.py` + `finetune_eval.py`); the eval harness is this task's
`dogfood500.py`.

**Risks.** Catastrophic forgetting / zero-data-tail drift on re-tune — mitigated by
the existing zero-data guardrail measurement (Task 38) and the sweep floor. Label
quality of logged misses — mitigated by the human gate.

**Graded-concept mapping.** **Continual learning (#3) directly** — this is how the
rubric's third concept gets satisfied, and it closes the loop that makes #1's
new abstains and #2's deferred synonyms pay off over time.

---

## 4. Submission polish

**Findings / evidence.** Graded concepts: Attention ✅ (the encoder) and Zero-shot/
Siamese ✅ (bi-encoder + contrastive fine-tune) are done; the **attention-viz figure
is still pending**; there is no single rules-vs-hybrid headline on a *real* set.

**Recommended approach.** (a) Attention-visualization figure on a few representative
utterances (offline, `.venv-ml`). (b) **Final rules-vs-hybrid eval on this 587-set**
(rerun with `LINUXBUDDY_ENCODER=0` vs on → the honest "what the hybrid adds" number;
note today the delta is small *because* the rules rarely abstain — which is itself
the headline that motivates #1). (c) README/CHANGELOG refresh. (d) `v2.0.0` tag.

**Scope.** Small, mostly writing + one figure. Best done *after* #1 (so the
rules-vs-hybrid delta reflects the improved abstain behaviour).

**Risks.** Low. Don't tag `v2.0.0` before #1, or the headline undersells the hybrid.

**Graded-concept mapping.** Attention (#1) — the viz is the required artifact.

---

## 5. Packaging hygiene

**Findings / evidence.** The live `lb` runs from `.venv` (Python 3.14) which now
has `numpy + onnxruntime + tokenizers` (torch-free) — installed manually. A fresh
clone would get **pure-rules only** (no encoder) because these aren't declared.
`pyproject.toml` has no `[ml]` extra. **6 unpushed commits** on `v2-multiturn`
(Tasks 35–40); this task adds a 7th.

**Recommended approach.** Add an **`[ml]` optional extra** to `pyproject.toml`
(`onnxruntime`, `tokenizers`, `numpy`) so `pip install -e '.[ml]'` reproduces the
hybrid, with **pure-rules remaining the default** (graceful degradation already
guarantees this). Document the regenerate-the-`.onnx` command (already in
`requirements-ml.txt`). Keep torch/transformers/sentence-transformers out of the
runtime extra (export-only). **Push recommendation:** push `v2-multiturn` (now 7
commits) at a milestone — *your call per the standing rule; recommended after #1
and the `v2.0.0` tag so the pushed history tells the full story.*

**Scope.** Trivial (a few lines of `pyproject.toml` + a doc note).

**Risks.** None of substance; verify a fresh `pip install -e .` (no extra) still
runs pure-rules (the degradation tests already assert this).

---

## Recommended overall sequence

1. **#1 Rules robustness — the coverage-check first.** Highest leverage: it both
   fixes the dangerous MISROUTE class *and* unlocks the encoder (today 5% reach).
   Everything else is worth more after it.
2. **#5 Packaging hygiene** (trivial, do alongside #1 so contributors can run the
   hybrid).
3. **#3 Continual-learning pipeline** (the missing graded concept; seed it with the
   587-set + the feedback log; it compounds over time).
4. **#4 Submission polish** (attention-viz + the real rules-vs-hybrid eval + tag),
   *after* #1 so the numbers are honest.
5. **#2 Learned dialogue-act head — defer** behind #3's data growth; keep the
   working rules session layer until there are enough real multi-turn turns.

**One decision for you:** whether to treat the 587-set as the official held-out
real-eval corpus now (tracked under `data/eval/`, clearly separate from `train`) —
recommended, and reflected in #3. See the tracking note below.

## Tracking note (what this task committed)

Per the brief's "your call": the generated CSV (`dogfood500_results.csv`) is treated
as **ephemeral** and gitignored, exactly like the earlier Task-35 stress outputs —
but the **generator `tests/dogfood500.py` IS committed**, and it encodes every
label, the diversity axes, and the leakage check, so the corpus is fully
reproducible and re-verified leakage-clean on every run. `asbuilt_summary.md`,
`dogfood500_diversity.md`, and this proposal are committed. **Recommendation:** once
you approve, freeze the labeled 587 rows as a tracked real-eval corpus under
`data/eval/` (clearly separate from `train.jsonl`) so the continual-learning loop
(#3) has a stable held-out benchmark — I left that as a decision for you rather than
committing a large CSV unilaterally.
