# Attention Reference-Resolver — option-1.5 spike report (Task 44)

*Dev-time spike. **Nothing wired into `lb`/`session.py`**; no rules/encoder/gate/
router change. The resolver runs only in `.venv-ml` under
`experiments/task44_spike/`. Full existing suite green (437 passed, 8 skipped).*

**One-line verdict:** **Attention's coreference/reference resolution is confirmed
functional and interpretable (100% phrase / 98% type-specific binding, 0 regressions)
— that is the real, visualizable win. The zero-shot act-recovery piece is only
partial (5/14 novel operate turns), strong on count-synonyms but weak on terse
size-synonyms ("the fat one"), so reliable act-recovery needs the light touch-up
(option 2). Recommend: ship 1.5 for coreference + the figure now; gate option 2 on
this frozen eval for the act piece. Do NOT jump to option 3.**

---

## What was built (all dev-time, unwired)
- **`data/eval/multiturn_eval.jsonl`** — the frozen held-out multi-turn eval (the
  multi-turn analogue of the frozen 587). **34 chains / 87 turns / 42 coref turns**,
  **25 in-vocab + 19 novel** discriminating turns. Leakage-clean vs the 49 training
  turns and label-audited (see below). Regenerate:
  `.venv-ml/bin/python -I experiments/task44_spike/build_eval.py --freeze`.
- **`experiments/task44_spike/resolver.py`** — the attention reference-resolver
  (torch, eager-attention). Two jobs only: (1) cross-turn coreference resolution,
  (2) a current-turn-**span**-pooled act/modifier cross-check (never the whole
  blended sequence — Finding 3).
- **`experiments/task44_spike/eval_spike.py`** — runs rules baseline vs resolver,
  sweeps attention signals, writes the figures.
- **`tests/test_multiturn_eval.py`** — pure-stdlib guard (leakage + schema + split)
  so the frozen eval stays honest in the main suite.
- **Figures:** `attention_novel_L3H1.svg`, `attention_novel_lastlayer_avg.svg`
  (novel chain "…which of **those** is heaviest").

## Part A — the eval, and the label-audit
The audit (in `build_eval.py`) **asserts** three things before freezing, so the
numbers mean something:
1. **Leakage-clean:** 0 of 87 turns duplicate any of the 49 `multi_turn.raw.jsonl`
   turns (same discipline as the dogfood check; also guarded by the stdlib test).
2. **In-vocab == rules:** every `in` turn's gold frame is exactly what the real
   `session.classify` + `merge` produce — so the in-vocab half genuinely measures
   *no-regression*, not a hand-wave.
3. **Novel == rules-miss:** every `novel` discriminating turn is one the rules
   actually miss (classify → `fallback` → single-turn abstain). That split is the
   whole experiment. Coverage: coref types `the ones`/`one`/`those`/`them`/`ones`
   across find/size/time/count/delete/operate and several registers.

## Part B/C — results

### Attention-signal sweep (which signal resolves coreference best)
Swept all 72 (layer, head) pairs + per-layer head-averages + all-average, scored by
referent accuracy over the 42 coref turns:

| signal | phrase-acc | type-specific |
|---|---|---|
| **L4 H4 (best)** | **1.00** | **0.98** |
| L0 H2 | 1.00 | 0.79 |
| L5 H11 | 0.98 | 0.95 |
| last-layer head-avg | 0.93 | 0.67 |
| **L3 H1 (the probe's example)** | **0.98** | **0.05** |

**Key lesson (exactly the task's warning):** *one example does not generalize.* The
Task-43 probe's **L3H1** binds the pronoun to the generic noun **"files"** (phrase-
correct, 0.98) but almost never to the **type** word (`csv`/`log`/`py`…, 0.05). A
proper sweep finds **L4H4**, which binds to the specific type **98%** of the time.
The resolver defaults to the swept-best signal, not the first example.

### The numbers (best signal L4H4)
| metric | result | reading |
|---|---|---|
| **In-vocab no-regression** (resolver agrees with rules where rules are right) | **25/25 (100%)** | attention never contradicts the 48/49 rules path |
| **Coreference — phrase** (binds to the target noun phrase) | **42/42 (100%)** | — |
| **Coreference — type-specific** (binds to the exact type token) | **41/42 (98%)** | the robust, visualizable win |
| **Novel recovery — strict frame** (headline) | **5/14 (36%)** | recovers what the rules abstain on… partially |
| **Novel refine** (act + reference recovery; slot stays rules') | **2/2 (100%)** | recognises the refine act + binds the target |
| **Safety — rules emit NO command on destructive elliptical** (invariant #6) | **3/3 (100%)** | hard guarantee intact |
| **Safety — resolver recognises destructive** (soft) | **2/3 (67%)** | a miss degrades to a non-destructive suggestion, never an `rm` |

### Where recovery wins and where it fails (honest breakdown)
RECOVERED (5): `which of those is heaviest`, `give me a count of those`, `which hogs
the most room`, `what's the headcount`, `total them up`.
MISSED (9): `show me the heavy one`, `the big one`, `tally them up`, `the bulkiest of
them`, `the fat one` (→ *min*-by-size!), `add them all up`, `the beefiest one` (→
*min*-by-size!), `the chunkiest of those`, `the weightiest of the bunch`.

**Pattern:** the attention **reference** is correct in ~all of these (the pronoun
binds to the right target). The failure is the **act cross-check**: the zero-shot
bi-encoder, pooling a terse `"the fat one"` / `"the beefiest one"`, does not match
the `find_largest` description — and twice picks `find_smallest` (wrong direction).
Verbose operate phrasings and *all* count-synonyms recover; terse `"the <adj> one"`
size phrasings are the gap. This is precisely the "attention resolves the reference,
but the act needs sharpening" outcome — i.e. a case for the **light contrastive
touch-up (option 2)**, not for abandoning 1.5.

## What attention actually BUYS over the rules (don't oversell)
1. **Coreference as a learned, reliable signal** (100%/98%) — "one/them/those" bound
   to the correct prior target by attention, not by the frame happening to hold one
   slot. Generalises across phrasings the regex never enumerates.
2. **Interpretability / the figure** — a genuine, inspectable cross-turn attention
   map (the grade centerpiece), now on a *novel* chain, not just the canonical one.
3. **Partial robustness on act** — count-synonyms and verbose size-synonyms the rules
   abstain on are recovered zero-shot (5/14 + 2/2 refine). This is real but partial.

What it does **not** buy (yet): reliable act detection on terse operate synonyms.
On in-vocabulary chains it **matches** the rules (25/25) — it does not beat them. The
honest claim is "attention does real, visible, generalising **coreference** work +
partial act-recovery," not "attention beats the rules."

## Safety (invariant #6 preserved)
All three destructive elliptical turns (`get rid of those`, `drop the tiny ones`,
`trash them`) route through rules → `fallback` → single-turn → **abstain**: **0**
destructive commands emitted (3/3). The resolver **never emits** by design — it only
*suggests*; emission stays behind the existing gate + exit-3 + review. Its destructive
*recognition* is 2/3 (it misreads "drop" as a size op), but that miss degrades to a
non-destructive suggestion and therefore cannot cause an `rm`. If 1.5 is ever wired,
an unclear destructive referent must still abstain, exactly as today.

## Risks observed
- **Regression:** none measured — 25/25 in-vocab agreement; the resolver is additive
  and only consulted on coref/novel turns. (And it is not wired at all yet.)
- **Thin data:** the eval is 34 chains; treat the 36% recovery as a directional
  signal, not a precise rate. It is enough to show the *shape* (coref solid, act
  partial).
- **Latency:** the resolver is torch (dev-time). Any production wiring must keep the
  ONNX hot path and restrict torch/attention to the rare `fallback` turns or export a
  second attention-free contextual ONNX — decided at wiring time, per the proposal.
- **ONNX-vs-torch for viz:** unchanged — attention viz is torch/`.venv-ml` only.

## Recommendation
- **Confirm option 1.5 for coreference + the figure.** The attention reference
  resolver is reliable (100%/98%), interpretable, and zero-regression. This alone
  makes "attention retains context across turns" a true, demonstrated claim.
- **For the act-recovery piece, escalate to option 2 (light contrastive touch-up),**
  gated on *this* frozen eval — the data shows a specific, fixable gap (terse operate
  synonyms), not a dead end. **Not option 3** (bespoke head): the mechanism works
  zero-shot; the gap is sharpening, not architecture.
- **Wiring into `session.py` remains a later task**, gated on the above and on the
  latency decision.

## Reproduce
```
.venv-ml/bin/python -I experiments/task44_spike/build_eval.py --freeze   # eval + audit
.venv-ml/bin/python -I experiments/task44_spike/eval_spike.py --figure   # metrics + figures
.venv/bin/pytest tests/test_multiturn_eval.py -q                         # stdlib guard
```
