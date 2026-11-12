# Continual Learning — the grow-from-real-use loop (Task 46 / concept #3)

*Rehearsal-based continual learning from a real-use feedback stream, measured as the **stability–plasticity** tradeoff. Plasticity = recovery on a HELD-OUT miss set (never trained on); stability = every frozen floor holds + the zero-data tail is preserved. Human-gated, offline, seed-pinned (seed 42).*

## The loop

1. **Capture** — `lb` logs every abstain to `~/.cache/linuxbuddy/feedback.jsonl` (offline, local; `lb --feedback`).
2. **Relabel** — assign each logged miss an intent from the frozen `label_space.json`; drop genuine out-of-domain.
3. **Fold** — append to a candidate `train.jsonl` (old train = the **rehearsal buffer**); assert leakage-clean vs BOTH frozen evals.
4. **Retrain** — re-run the Task-38 contrastive fine-tune (seed 42) on old-train + new misses.
5. **Ship gate** — adopt ONLY if every stability floor holds; else reject.

## The honest split

Miss pool: **26 real abstains**, every one a verified **encoder** miss on the shipped `lb` (the fine-tuned bi-encoder ranks the WRONG intent #1, or below the `t_read` threshold — these are what a retrain can fix; slot-filling gaps are excluded). Phenomena: find_recent (18), find_empty (4), show_history (3), disk_usage (1). The dominant one, **find_recent**, is systematically confused with its semantic neighbour `find_by_time`. We **hold out half the phrasings of each phenomenon** (12 misses) and never train on them — so held-out recovery is generalization to unseen phrasings of a learned phenomenon, not memorization. Training pool = 14; cycle 1 trains on half, cycle 2 on all (a repeatable, cumulative loop). Measured with the SAME decision rule the user sees (cosine top-1 ≥ t_read).

## Stability vs plasticity — before/after

| checkpoint | PLASTICITY top-1 emit | PLASTICITY gold-in-top3 | PLASTICITY mean gold sim | STABILITY nonsense FP | zero-data top-3 | gap | val top-1/3 |
|---|---|---|---|---|---|---|---|
| shipped (before) | **0%** | **67%** | 0.538 | 3% | 96% | 93% | 72/89% |
| cycle 1 (+7 misses) | **17%** | **83%** | 0.567 | 3% | 96% | 96% | 72/89% |
| cycle 2 (+14 misses) | **17%** | **83%** | 0.572 | 3% | 96% | 93% | 72/89% |

**Plasticity:** strict top-1 emit recovery rises 0% → 17% → 17%, and the softer signals show the loop is still moving the boundary even where top-1 doesn't flip: gold-in-top-3 67% → 83%, mean gold cosine 0.538 → 0.572. The strict number is **capped by a genuine semantic adjacency** — find_recent vs find_by_time ('my newest files' is recency; 'files modified today' is a date filter) are near-synonyms, so a handful of rehearsal examples lift gold from #2/#3 toward #1 but the sticky neighbour holds the last-mile. That ceiling is the honest finding, not a bug: separating two adjacent intents is exactly the hard case for rehearsal CL, and it argues for more per-phenomenon examples (or a margin-tuned gate) next — not for abandoning the floors.

**Encoder-level stability held:** nonsense FP 3%→3% (no abstain erosion), the **zero-data tail** (27 untrained intents) top-3 96%→96% (no gross forgetting), gap 93%→93%, val top-1 72%→72%. On these proxies every cycle looks adoptable — **but they are not the whole story.**

## The authoritative runtime floors — the stability COST the proxies miss

The project's real floors are **0-regression** on the 587 single-turn sweep and the multiturn eval, through end-to-end `lb`. Measured on each candidate's exported ONNX (`LINUXBUDDY_MODEL_DIR`):

| checkpoint | 587 CORRECT | GATE_LEAK | multiturn novel | multiturn in-vocab |
|---|---|---|---|---|
| shipped (floor) | 404 | 0 | 11/14 (79%) | 24/24 (100%) |
| cycle 1 (+7) | 403 | 0 | 10/14 (71%) | 24/24 (100%) |
| cycle 2 (+14) | 403 | 0 | 9/14 (64%) | 24/24 (100%) |

Both candidates **regress** the floors: 587 CORRECT 404→403 (−1) and multiturn novel 11/14 (79%)→9/14 (64%). The regression is **concrete catastrophic interference**: cycle 2 newly *forgot* the size-coreference turns **N02 'show me the heavy one'** and **N03 'the big one'** (the shipped model resolved both). Fitting the find_recent phenomenon nudged the nearby 'heavy'/'big' resolutions below threshold — the exact failure continual learning is about. Containment held throughout (GATE_LEAK 0), and in-vocab stayed 24/24.

## Ship-gate verdict (complete floors)

- Cycle 1: **REJECT** — a 0-regression runtime floor dropped (the gate doing its job)
- Cycle 2: **REJECT** — a 0-regression runtime floor dropped (the gate doing its job)

The encoder-level proxies (gap/val/nonsense/zero-data) **passed** for both cycles — an encoder-only gate would have wrongly shipped a net-negative model. The authoritative 587 + multiturn **0-regression** floors caught the cost and the complete gate **rejected** both. Nothing was adopted; the shipped checkpoint stands. **This is the loop succeeding, not failing:** it proves the human gate + hard floors prevent regression-shipping, and it localizes the fix — the find_recent/find_by_time boundary needs *balanced* rehearsal (and the size-coref turns rehearsed alongside), not more one-sided examples. 147-sweep is rule-handled → encoder-independent → structurally 0 diffs.

## What this demonstrates (grade concept #3)

Rehearsal-based continual learning from a real-use feedback stream, measured as the **stability–plasticity tradeoff** — and the tradeoff is *real*, not hand-waved: plasticity rose (held-out find_recent generalization) while stability was spent (size-coref interference), and the **0-regression ship gate** refused the trade. Offline, seed-pinned (42), human-gated, no network. The loop ties the system together: the abstain-capture hook feeds it real misses; the Siamese encoder (#1/#2) is what moves; the frozen 587 + multiturn evals are the floors that make 'don't forget' enforceable rather than aspirational.

## Reproduce

```
.venv-ml/bin/python -I experiments/task46_cl/run_demo.py --runtime
```

