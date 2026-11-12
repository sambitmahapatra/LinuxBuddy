# Attention-Based Context Retention — design proposal (Task 43)

*Design/research only. Nothing here is implemented; no rules/router/encoder/gate/
session code changed. The deliverable is a recommendation to review before any
build. Grounded in the Part-1 code facts and the Part-3 probe
(`experiments/task43_attention/probe.py`, run against the real fine-tuned model).*

---

## TL;DR

- **The probe settles the central question: cross-turn attention is real and
  visualizable in our existing fine-tuned encoder.** On the canonical 3-turn chain,
  the pronoun **"one"** in turn 3 ("show the biggest **one**") attends to **"files"
  (0.626)** and **"##v" (csv, 0.20)** from turn 1 — attention literally resolving
  coreference across turns. The showcase figure exists (`attention_map.svg`,
  layer 3 head 1).
- **But the cheapest approach — "concatenate history+turn, match the whole pooled
  embedding to an intent" — has a real failure mode the probe exposed:** the
  filter-heavy history *dilutes* the current turn's operate intent. "show the
  biggest one" alone ranks `session_find_biggest` #1 (0.608); with the full history
  prepended it drops to #4 and `find_by_time` (the turn-2 filter) rises to #1
  (0.775). Whole-sequence mean-pooling blends the turns, so the *act/intent*
  decision gets outvoted by history.
- **Recommendation: a targeted hybrid (spectrum option 1.5).** Attention owns the
  one thing it demonstrably does well and the rules can't — **coreference /
  reference resolution** ("one/them/it/the ones" → which prior target) — plus it
  produces the **attention-map figure**. The rules `SessionFrame` keeps owning
  **state accumulation** and **dialogue-act/modifier detection**, where it already
  scores 48/49 and where the probe shows the encoder would *regress*. This makes
  attention do *real, visible* work without the thin-data problem and without
  betting the working path on 49 training turns.

---

## Part 1 — What we'd build on (grounded)

### State today is symbolic, and it works
`session.py` is a rules state machine, no model:
- **`SessionFrame`** (`session.py:51`) holds the running query: `op`, `targets`
  (`path`,`name`), `filters` (`size`,`mtime`), `modifier` (`max-by-size`/`count`),
  `cwd`, a 10-item `history` of `{request,act}`, TTL 10 min, disk-backed JSON keyed
  on `$LINUXBUDDY_SESSION`. **`merge()`** (`:82`) is the whole context-retention
  mechanism: a refine `.update()`s targets/filters without clobbering, so a turn-1
  `-name '*.csv'` survives a turn-2 `-mtime`. That accumulator *is* "context
  retention" today — and there is no attention in it.
- **`classify()`** (`:278`) is rules dialogue-act detection, precedence-ordered:
  `reset` → fileop-lead `fallback` → self-contained `new` → `operate` → `refine` →
  `new`-if-composable → `fallback`. `_operate_delta` (`:243`) recognises
  coreference only by hardcoded phrase: `biggest|largest|most space` →
  `max-by-size`, `count them|how many` → `count`. `_refine_delta` (`:254`) attaches
  a size/day/type constraint when there's no new op verb.
- **`to_command_plan()`** (`:95`) renders the accumulated frame to a plain v1
  `Frame` (`session_find` / `session_find_biggest` / `session_count`) that flows
  through the *unchanged* `compile → gate → render` pipeline. This is the seam any
  design must respect: **whatever decides intent/reference must still emit a Frame
  the existing planner + gate consume.**

So coreference "works" today only because (a) the frame keeps the prior slots and
(b) the exact surface phrase is in a regex. Novel phrasings ("which of those is
heaviest", "drop the small ones", "just the recent stuff") fall through to
`fallback` → single-turn → likely abstain.

### The encoder, and why viz needs torch
- Fine-tuned **`all-MiniLM-L6-v2`** (6 layers, 12 heads, 384-dim), contrastive
  **MNRL / Siamese** (`ml/finetune.py`): the same encoder embeds an utterance and
  an intent *description*; cosine + a 2-feature logistic **abstain gate**
  (`[max_sim, margin]`) makes the in-domain/abstain call.
- It is consulted **only on a single-turn rules abstain** (the `hybrid.py` seam),
  which is why its live reach is small (5.3% → ~8.5% after Task 42).
- **Runtime is torch-free ONNX fp32** (`ml/onnx_encoder.py`) for latency. Confirmed
  in the probe: **the ONNX export does not expose attention weights** — SDPA can't
  return them and the export only emits `last_hidden_state`. **Attention
  extraction/visualization therefore needs the torch model in `.venv-ml`, dev-time
  only.** That's fine: the figure is an author-time artifact, never a runtime
  dependency (mirrors the existing "torch is export-only" rule).

### Multi-turn data (the constraint)
`data/multi_turn.raw.jsonl`: **49 turns across 20 chains**, acts **imbalanced** —
`new 23 / operate 9 / refine 7 / reset 6 / fallback 4`. **14/49 turns carry
coreference** ("only the ones over 1mb", "which one is biggest", "delete them",
"count them"). Sources: hand 28 / stress_session 18 / golden_seed 3. This is far
too little to train a dialogue-act head (the `refine`/`fallback` classes have 7/4
examples) — which is exactly why act-detection stays rules.

---

## Part 2 / Part 3 — The design space, decided by probe evidence

The probe (`experiments/task43_attention/probe.py`) tested the three riskiest
assumptions on the **real** fine-tuned model. Results drive every choice below.

### Finding 1 — Cross-turn attention is real (so the figure is real)
On `"find the csv files. only the ones modified yesterday. show the biggest one"`,
turn-3 tokens put **0.71 of their attention mass onto turn-1/2 tokens** at the
strongest head (layer 3, head 1); six heads exceed 0.59. Token-level, at L3H1:

| turn-3 token | attends most to (prior turns) |
|---|---|
| **one** | **files 0.626**, **##v (csv) 0.20**, modified 0.03 |
| biggest | one 0.31, files 0.19, modified 0.17 |
| show | the 0.29, biggest 0.26, modified 0.09 |

**"one" resolving to "csv files" across two turns is the exact showcase** the grade
asks for. The figure is in `experiments/task43_attention/attention_map.svg`
(+ a head-averaged last-layer variant).

### Finding 2 — Context helps *reference/object* resolution (zero-shot)
Prepending history disambiguates elliptical turns:
- `"count them"` alone: `count_files 0.563`, `count_matches .551`, `count_lines
  .542`, `session_count .542` — a near-tie (count *what*?). With `"find the python
  files. count them"`: `count_files 0.794` clear. Context resolves the *object*.
- `"only the ones modified yesterday"` → `find_by_time` either way, but context
  sharpens 0.691 → 0.872.
- `"delete them"` → `delete_file` stays #1 with or without context (0.620 / 0.633).
  Safety-relevant: the destructive intent is recognised; context doesn't erase it.

### Finding 3 — Naive whole-embedding concatenation REGRESSES the act/intent decision
The cautionary result. `"show the biggest one"` alone ranks `session_find_biggest`
**#1 (0.608)**. With the full 3-turn history prepended, it falls to **#4 (0.681)**
and **`find_by_time` (0.775)** — the turn-2 *filter's* intent — rises to #1. Mean-
pooling over the whole concatenation **blends** the turns; the operate verb in the
short final turn gets outvoted by the longer filter-heavy history. **So "concatenate
and match the whole pooled embedding" is the wrong way to pick the act/intent.** The
rules get this right (operate = "biggest") at 48/49.

**Conclusion the evidence forces:** attention is excellent at *what the elliptical
turn points back to* (Findings 1–2) and *bad* at *which act the turn is* when read
as a blended whole (Finding 3). Give each sub-problem to the layer that wins it.

### The architecture spectrum, weighed

| option | novelty | data need | offline/3050 | regression risk | viz | verdict |
|---|---|---|---|---|---|---|
| **1. Reuse + concat, match whole embedding** | low | none (0-shot) | trivial (reuse) | **high** — Finding 3 dilutes the act | yes | ❌ as the *decision* path |
| **1.5 Reuse + attention as a reference resolver** (recommend) | **medium-high** (attention does a *named* job + figure) | none for spike | trivial | **low** — rules keep the act/state | **yes, central** | ✅ |
| **2. Light contrastive touch-up** on ~49 turns + a few synth chains | medium | some (overfit trap) | minutes CPU | medium | yes | later, only if #1.5 shows a gap |
| **3. Bespoke cross-attention head** (current=query, history=keys/values) | **highest** | needs data we lack | trainable but data-starved | **high** | yes (purpose-built) | tempting for "standout", deferred |

Option 3 is the most academically impressive ("a *custom* attention mechanism, not
just used a transformer"), and worth naming as the stretch goal — but it needs
training data the project doesn't have (49 turns, 7 refine / 4 fallback) and it
risks the 48/49 baseline. Option 1.5 gets **most of the standout** (attention doing
a real, named, visualized job in multi-turn) at near-zero data and regression cost.

---

## Part 4 — The proposal

### Recommended approach: **1.5 — attention as the cross-turn reference resolver**

Keep the division the evidence draws:
- **Rules `SessionFrame` keeps state** (accumulate targets/filters via `merge`) and
  **rules `classify()` keeps dialogue-act + modifier** (new/refine/operate/reset).
  These are the 48/49 path and the parts the probe shows the encoder would regress.
- **Attention owns reference/coreference resolution:** when a turn is elliptical
  ("the biggest **one**", "delete **them**", "only the **ones**…"), feed
  `history [SEP] current-turn` through the fine-tuned **torch** encoder and use the
  **cross-turn attention** (the "one"→"csv files" signal, Finding 1) to confirm/pick
  **which accumulated target** the pronoun binds to — then the rules frame operates
  on that resolved target. In the single-target chains we have today the rules
  already bind correctly; attention's visible job is to make that binding
  *model-driven and inspectable*, and to **generalize** to phrasings the regex
  misses (where today the turn falls to `fallback`→abstain).
- **The attention map is a first-class deliverable**, not a side effect: the same
  forward pass that resolves the reference renders the figure.

Why this and not the cheaper option 1: Finding 3. Why not option 3 now: data. This
is the honest maximum that the 49-turn reality supports.

### Thin-slice spike plan (rapid-prototype, gated, measurable)

A dev-time spike in `experiments/` / `.venv-ml`, **not wired into `lb`**, proving
the mechanism end-to-end on the 3-turn chain:

1. **Reference-resolution probe → module (dev-time).** Given `(history, current
   elliptical turn)`, run the torch encoder once, extract L3H1 cross-turn attention,
   and emit: (a) the resolved prior target the pronoun attends to, (b) the
   contextualized embedding of the *current turn span only* (pool over current-turn
   tokens, **not** the whole sequence — this sidesteps Finding 3), matched to intent
   descriptions for the act/modifier *as a cross-check* against the rules.
2. **Measure against the rules on a real held-out chain eval** (below). Gate:
   attention-resolution must **match the rules on the chains the rules already get
   (no regression)** and **recover ≥ some of the novel-phrasing chains the rules
   miss** (the actual value-add). If it can't beat `fallback`→abstain on novel
   phrasings, we learned the cheap path isn't enough and escalate to option 2/3 —
   that's a valid outcome.
3. **Produce the figure** on the canonical chain (done already in the probe) and a
   second novel-phrasing chain, for the write-up.
4. **Only then** propose the production seam (step below), as a *follow-up task*.

### Where it would seam in later (not now)
In `session.py`, at the `operate`/`refine`/`fallback` decision in `classify()`:
when the rules would `fallback` on an elliptical turn (no regex hit) **and** a frame
exists, consult the attention resolver to recover the reference and the
act/modifier; feed the result into the existing `merge()` + `to_command_plan()`.
Everything still renders to a `Frame` → `compile → gate → render`, unchanged.
**Graceful degradation:** if the torch/ONNX model is absent (or
`LINUXBUDDY_ENCODER=0`), `classify()` behaves exactly as today — the resolver is a
bonus path, never a dependency, mirroring the single-turn hybrid.

### Data & eval plan — the honest baseline and what attention buys
- **Baseline to beat: the rules `SessionFrame` at 48/49 on the dogfood chains.**
  State it plainly.
- **Build a real held-out multi-turn eval** — the analogue of the frozen 587
  single-turn set (`data/eval/dogfood_eval.jsonl`). Author ~25–40 **labeled chains**
  (final-frame + per-turn act), **half paraphrased into phrasings the current regex
  does NOT cover** ("which of those is heaviest", "drop the tiny ones", "just
  what changed today"), frozen under `data/eval/` and **never trained on**. Without
  this, no claim is measurable.
- **What attention buys over the rules (be precise, don't oversell):**
  1. **Robustness to unseen phrasing** — the regex handles `biggest|largest|count
     them`; attention/embedding generalizes to synonyms the rules will always miss,
     turning `fallback`→abstain into a correct resolution. *This is the measurable
     win; the held-out novel-phrasing chains quantify it.*
  2. **Coreference as a learned signal** — "one/them/those" bound to a prior target
     by attention, not by the frame happening to hold one target.
  3. **Interpretability** — the attention map is a genuine, inspectable explanation
     of the cross-turn decision (the grade centerpiece).
  If the spike shows attention merely *matches* the rules on in-vocabulary chains
  with better generalization + a figure, **that is the honest claim** — "attention
  does real, visible, generalizing context work," not "attention beats rules."
- **Augmentation without the overfit trap:** reuse the Task-36 discipline — cap
  synthesized chains, keep them OUT of the frozen eval, grow mainly from *real
  logged* multi-turn misses (ties to continual learning, #3). Do **not** mass-
  generate chains and train a head on them.

### Risks and mitigations
- **Regressing the 48/49 rules path** → attention is *additive* (only on
  `fallback`, only with a frame); rules decision kept; byte-level chain regression
  check before any wiring. **Primary risk, primary mitigation.**
- **Thin data (49 turns)** → spike is zero-shot (no training); any touch-up (option
  2) is gated on the frozen held-out eval, not train accuracy.
- **Finding-3 dilution** → resolved by pooling the *current-turn span* and letting
  rules own the act; never match the whole concatenated embedding for the decision.
- **Latency on the multi-turn path** → the resolver is torch (slow) and multi-turn
  is interactive; for production, either export a *second* ONNX (no attention, just
  the contextual embedding) and keep attention torch-for-figures-only, or restrict
  the resolver to the rare `fallback` turns. Decide at wiring time, not now.
- **ONNX-vs-torch for viz** → settled: viz is torch/`.venv-ml`, dev-time; runtime
  stays ONNX. No runtime torch dependency ever.
- **Over-engineering** → option 3 (bespoke head) explicitly deferred behind data;
  the spike is the minimum that proves the mechanism + figure.

### Grade-concept mapping
- **Attention (#1) becomes a showcase, not a black box.** Today attention is
  "MiniLM uses self-attention internally, on a fallback path, never shown." After
  this: attention performs a *named* job — cross-turn coreference resolution — with
  a figure that shows "one" → "csv files". That is the difference between "we used a
  transformer" and "attention visibly retains context across turns."
- **Zero-shot / Siamese (#2, done)** is *reused*: the same MNRL-fine-tuned
  bi-encoder provides both the contextual embedding and the attention; no second
  model.
- **Continual learning (#3)** is the long-term feeder: real logged multi-turn misses
  grow the chain corpus and (optionally) the light touch-up, under the frozen
  held-out eval — the same loop proposed in `v2_remaining_proposal.md`.

### What stays rules (explicit)
- **Dialogue-act classification** (new/refine/operate/reset) — data-starved
  (7 refine / 4 fallback), works at 48/49; stays `classify()`.
- **`SessionFrame` state accumulation** (`merge`) and the render bridge
  (`to_command_plan` → Frame) — the symbolic accumulator is correct and cheap.
- **Safety is entirely unchanged.** Multi-turn destructive ("delete them") still
  routes through the **same gate + exit-3 + human-review**, with the destructive-
  confidence asymmetry intact: the probe confirms the encoder still identifies
  `delete_file` from context, but the *decision to emit* a destructive command stays
  behind the location gate and confirmation — attention resolves the reference, it
  never lowers the bar to run `rm`. An elliptical destructive turn with an unclear
  referent must still **abstain**, exactly as the single-turn destructive policy
  (CLAUDE.md invariant #6) requires.

---

## Appendix — probe artifacts (throwaway, not wired in)
- `experiments/task43_attention/probe.py` — the three probes (A context-helps,
  B cross-turn mass, C figure). Run: `.venv-ml/bin/python -I
  experiments/task43_attention/probe.py`.
- `experiments/task43_attention/attention_map.svg` — the showcase figure (L3H1):
  turn-3 "one" attending to turn-1 "csv files".
- `attention_map_lastlayer_avg.svg` — head-averaged last layer (cleaner, less sharp).
- Nothing in `src/`, `tests/`, the KB, or the model was changed by this task.
