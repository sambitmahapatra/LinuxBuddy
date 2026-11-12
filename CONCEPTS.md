# The three graded concepts — where they live, and the evidence

LinuxBuddy stays a **local, offline, rules-first** tool: nothing auto-executes, no
network, no LLM or generative model at runtime. The three graded ML concepts are
woven in as a **fallback and a learning loop around the rules**, never as a
replacement for them. This document maps each concept to its code and its honest
evidence — including the findings that make the design read as understood rather
than assembled.

---

## 1. Attention — contextual coreference resolution across turns

**What it is.** A fine-tuned MiniLM-L6 bi-encoder (6 transformer layers, 12 heads).
Its self-attention is what lets an elliptical follow-up turn — *"which of **those**
is heaviest"* — bind its pronoun back to the type named in turn 1 (*"the **csv**
files"*), so the multi-turn resolver can carry the running query forward.

**Where it lives.**
- The encoder: `src/linuxbuddy/ml/` (trained in `finetune.py`; torch-free ONNX
  runtime in `onnx_encoder.py`).
- The cross-turn resolver, wired at the **session fallback seam**:
  `src/linuxbuddy/session_resolver.py`, consulted from `cli._session_dispatch`
  only when the rules abstain on an elliptical turn and a live `SessionFrame`
  exists. It embeds the **current-turn span pooled from the `history . current`
  contextual sequence** (not the turn alone — that lost context — and not the whole
  blended embedding) and maps a READ operate intent to a max-by-size / count delta.

**Evidence.**
- The head that does the job is **L4H4**: a signal sweep over all 72 (layer, head)
  pairs puts it first — **phrase-accuracy 1.00, type-specific coreference 98%
  (41/42)** across the held-out multi-turn set. The probe's original L3H1 binds to
  the generic token "files" (type-specific only 5%) — a documented finding, and the
  reason the resolver uses the swept-best head, not the first interpretable one.
- Figures: `experiments/task44_spike/attention_{golden,novel}_L4H4.svg` show the
  elliptical pronoun attending to the turn-1 type tokens, on both the golden chain
  and a novel-phrasing chain; head-averaged variants (`…_layer4_avg.svg`) are kept
  for comparison (the single-head L4H4 reads most cleanly).
- End-to-end through real `lb`: novel multi-turn recovery **36% → 79% (11/14)** once
  wired; in-vocab chains **24/24** byte-exact (0 regression); destructive elliptical
  turns **3/3 abstain** (invariant #6 — context never fills an `rm`/`mv` target).
- Reports: `attention_context_proposal.md`, `attention_spike_report.md`.

---

## 2. Zero-shot / Siamese — matching utterances to intent *descriptions*

**What it is.** The SAME encoder embeds both an utterance and an intent
*description*; a contrastive objective (**MultipleNegativesRankingLoss**, in-batch
negatives) pulls a true (utterance, description) pair together and pushes the rest
apart. That IS a Siamese network: one shared encoder, two inputs, a distance
objective. Because intents are reached by their description, an intent needs **no
training utterances at all** to be routable — the zero-shot property.

**Where it lives.**
- Training: `src/linuxbuddy/ml/finetune.py` (MNRL on utterance↔description pairs).
- The intent descriptions: `kb/intent_descriptions.yaml` (all 85 intents).
- Runtime matching + abstain gate: `onnx_encoder.py` + the `t_read` threshold in
  `hybrid.py`; a calibrated logistic gate on `[max_sim, margin]` is the documented
  alternative decision rule (`finetune.py`).

**Evidence.**
- Of **85 intents, 27 carry zero training utterances** and are served by their
  description alone (58 have training rows). A 12-intent / 24-utterance **zero-data
  guardrail** confirms fine-tuning doesn't silently degrade them: top-3 **intact
  (+8 points)**.
- Held-out quality after fine-tuning: **gap recovery 93%** (from 19% on the
  un-tuned base — zero-shot alone could not be thresholded), **nonsense FP 3%**
  (target < 15%), val top-1 **72%** / top-3 **89%**.
- Report: `finetune_report.md` (and the base bake-off in `bakeoff_report.md`).

---

## 3. Continual learning — the offline, human-gated, grow-from-real-use loop

**What it is.** A rehearsal-based loop that learns from a stream of **real logged
misses** (plasticity) while **proving** it does not forget (stability), gated by a
human. No network, no runtime LLM; seed-pinned and reproducible.

**Where it lives.**
- Capture: `src/linuxbuddy/feedback.py` + the `cli` seam — every abstain is appended
  to an offline `~/.cache/linuxbuddy/feedback.jsonl` (`lb --feedback`).
- The loop: `src/linuxbuddy/ml/retrain.py` — relabel (frozen label space) → fold
  into a candidate train (old train = the **rehearsal buffer**) with a leakage assert
  vs both frozen evals → retrain (reuse the fine-tune) → evaluate every floor → ship
  gate. Nothing adopts without a human.
- Demonstration: `experiments/task46_cl/run_demo.py` → `continual_learning_report.md`.

**Evidence — the complete stability–plasticity arc.**
- **Naive cumulative rehearsal** raised held-out plasticity (top-1 0→17%) but caused
  **catastrophic interference** — it forgot the size-coref turns *"show me the heavy
  one"* / *"the big one"*. The **0-regression ship gate rejected it.**
- **Balanced / targeted rehearsal** (upweight the interfered region) reversed the
  single-turn interference (587 **404→407**), lifted plasticity (**17→25%**), and
  recovered one of the two forgotten turns — but stayed **one** turn short on the
  multiturn floor, an honest **data-scale limit** (not papered over).
- The gate is the **same frozen floors, same held-out split, never weakened**, so the
  verdict means something.

**Two insights that make the design legible.**
1. **Proxy metrics passed but the runtime floor caught the regression.** The
   encoder-level floors (gap / val / nonsense / zero-data) all held on the naive
   candidate — an encoder-only gate would have *shipped a net-negative model*. Only
   the **end-to-end** 587 + multiturn floors exposed the forgetting. The authoritative
   gate must be end-to-end.
2. **A description-only intent is un-rehearsable.** The last un-recovered turn
   resolves to `session_find_biggest`, which has **zero trainable rows** (it exists by
   description alone — concept #2). Rehearsal can only pin an intent it has rows for,
   so the very property that makes an intent zero-shot makes it impossible to protect
   by rehearsal — a real, inherent tension between the zero-shot and continual-learning
   designs.

---

## How they fit together

```
rules (fast, deterministic, absolute priority)
  └─ abstain → encoder fallback  ……………………… concept #1 (attention) / #2 (zero-shot)
                 picks an intent by description; slots re-use the rules' detectors;
                 runs through the SAME compile → gate → render pipeline
  └─ multi-turn: elliptical turn → session_resolver ……… concept #1 (cross-turn coref)
  └─ every abstain logged → offline retrain loop ……………… concept #3 (continual learning)
```

The rules keep absolute priority; the encoder only runs when they abstain; the human
presses Enter; and nothing is adopted into the shipped model without passing every
frozen floor. The ML earns its place as reach and adaptivity **on top of** a tool
that is correct and safe without it.
