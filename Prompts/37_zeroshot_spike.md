# Task 37 — v2 Phase 1 spike: zero-shot bi-encoder (NO fine-tuning, NO GPU)

Read `CLAUDE.md`, `STATUS.md`, `ROADMAP_V2.md`, `DATA_CARD.md`, recent `LOG.md`.
Branch `v2-multiturn`. **Measurement spike only — do NOT touch the rules, the
router, the planner, or the KB command specs.** No fine-tuning, no training loop,
no CUDA. The whole point is to find out how far a *pretrained* encoder gets us
before we spend a single GPU-minute.

## The question this spike answers

Our data card showed 27/85 intents have zero training data and 45 more have <3
seeds — fatal for a softmax classifier, fine for a bi-encoder that matches
utterances to intent *descriptions* by similarity. So: with an off-the-shelf
MiniLM and good descriptions, how well can we recover the intents the **rules
miss** (the 22 stress-test gaps), while still correctly abstaining on nonsense?

The answer decides whether we fine-tune at all, and whether we need the targeted
collection pass. Don't integrate anything into `lb` yet — this is offline
measurement that produces a verdict.

## Preserves the project's identity

A bi-encoder (MiniLM, ~22M params, ~90MB) is a **local embedding model**, not a
generative LLM: no API, no internet at inference (one-time model download on
WSL, then fully offline), execution still awaits human confirmation. The offline,
no-runtime-LLM promise holds.

## Setup

- `requirements-ml.txt`: `sentence-transformers` (pulls torch). **CPU torch is
  fine for this spike** — MiniLM inference on 85 descriptions + a few hundred
  utterances is sub-second on CPU. GPU only matters for fine-tuning (a later
  task). Pin versions.
- Model: `sentence-transformers/all-MiniLM-L6-v2` (downloaded once on the WSL
  box, then cached offline). If you prefer, note `all-MiniLM-L12-v2` as a
  drop-in to try if L6 underperforms — same API.
- Everything lives under `src/linuxbuddy/ml/` (the package from Task 36). Fixed
  seed for any sampling.

## Part A — author intent descriptions (this IS the work)

The bi-encoder matches utterances to intent descriptions, so **description
quality, not model choice, determines accuracy.** The KB command specs don't have
natural-language descriptions suited to matching — write them.

Produce `kb/intent_descriptions.yaml`: one entry per intent id in
`data/label_space.json` (all 85), e.g.:
```yaml
file_discovery.find_by_type:
  description: "find or list files of a particular type or extension, like all
    the python files, csv files, or log files in a directory"
  examples: ["find all the python files", "where are the csv files"]   # optional anchors
file_management.copy:
  description: "copy or duplicate a file, make a backup copy, or clone a file to
    another name or location"
file_management.delete:
  description: "delete, remove, erase, or get rid of a file or files"
```
Guidelines:
- Natural language describing *what the user wants*, in the words a user would
  use — fold in the synonyms the rules miss (erase/nuke/wipe for delete,
  clone/replicate for copy, "list all" for find). This is where we bank the
  22-gap vocabulary as *descriptions* instead of hand-patched regexes.
- 1-2 sentences. Optionally a couple of `examples:` per intent as extra anchors
  (you can embed description+examples together and average, or just description —
  try both, report which is better).
- Cover all 85, including the 27 zero-data intents — they get descriptions too,
  which is exactly how the bi-encoder can serve them with no labeled data.
- This file is a durable, reusable artifact (Phase 3 zero-shot + continual
  learning both build on it) — track it in git.

## Part B — the zero-shot matcher (`src/linuxbuddy/ml/zeroshot.py`)

- Embed all 85 intent descriptions once (cache the matrix).
- For an utterance: embed it, cosine-similarity against the 85, return ranked
  `[(intent, score), ...]`.
- **Abstain logic (critical — a bi-encoder always returns a nearest neighbor):**
  - top-1 score below an absolute threshold `T` → `_ABSTAIN`.
  - also compute the **margin** (top1 − top2); a tiny margin = ambiguous → a
    secondary abstain/defer signal. Report both; we'll pick the rule from the
    data.
- Pure function, no side effects, no `lb` integration.

## Part C — evaluation harness (`src/linuxbuddy/ml/eval_zeroshot.py`)

Run three evaluations and a threshold sweep. **No training.**

1. **Val accuracy (ceiling check).** On `data/val.jsonl` (55 single-turn):
   top-1 and top-3 accuracy, overall and per covered intent. Top-3 high but
   top-1 mediocre ⇒ the space is right, margin/fine-tuning would sharpen it.
2. **The gap set (the real target).** The 22 stress-test rules-ceiling
   phrasings (pull them from `stress_test_results.csv`, or from Task 36's
   `source: "stress_gap"` rows which are already labeled). For each: does the
   matcher recover the correct intent at top-1? This is the number that matters —
   these are exactly the cases the rules abstain on today.
3. **Abstain negatives (false-positive check).** The `_ABSTAIN` rows (vague +
   nonsense). The matcher must score these *below* `T`. Report the
   false-positive rate (nonsense forced to a real intent) at each threshold.
4. **Threshold sweep.** Vary `T` across the cosine range; plot/table three
   curves: gap-recovery %, val top-1 %, and nonsense-correctly-abstained %.
   Recommend an operating point `T*` that maximizes gap recovery while keeping
   nonsense-abstain high (aim: nonsense false-positive < ~15%).

Write `data/eval_cache.jsonl` (per-utterance: top-3 intents+scores+correct) so
we can re-analyze without re-embedding.

## Part D — report + verdict (`zeroshot_spike_report.md`)

```markdown
# Zero-Shot Bi-Encoder Spike — Report
## Setup: model, description strategy (desc-only vs desc+examples), T*
## Results
- Val: top-1 __%, top-3 __% (per-intent table; worst performers)
- Gap set (22): recovered __/22 at T*  ← the headline number
- Nonsense abstain: __% correct at T*  (false-positive __%)
- Threshold sweep table/figure
## Verdict (pick one, with the numbers behind it)
- GOOD ENOUGH: zero-shot floor is strong → wire it as the rules fallback next,
  skip fine-tuning for now.
- NEEDS FINE-TUNING: space is right (top-3 high) but top-1 soft → contrastive
  fine-tune on the 204 pairs (next task, uses the 3050).
- NEEDS BETTER DESCRIPTIONS: specific intents fail because their description is
  weak → iterate Part A first (cheap), re-run before any training.
## Which intents fail and why (the confusion-matrix watchlist from the data card)
## Recommendation on the 27 zero-data intents: served acceptably by description
  alone, or flagged for the targeted collection pass?
```

Iterate once if cheap: if a handful of gaps miss because a description is weak,
improve those descriptions and re-run — that's the whole advantage of this
approach over regex whack-a-mole.

## Tests (`tests/test_zeroshot.py`)

- `intent_descriptions.yaml` covers all 85 label-space intents (0 missing,
  0 extra). Fail loudly on mismatch.
- The matcher returns a valid in-vocabulary intent or `_ABSTAIN`.
- Determinism: same utterance → same ranking across runs.
- A couple of golden cases: "erase scratch.tmp" ranks `file_management.delete`
  in top-3; "banana telephone sunshine" scores below a sane `T`.
- (Keep the existing 401 suite green — this task adds only, changes nothing.)

## Done when

- `kb/intent_descriptions.yaml` (all 85), `zeroshot.py`, `eval_zeroshot.py`,
  `tests/test_zeroshot.py`, and `zeroshot_spike_report.md` exist.
- The report gives the headline gap-recovery number, the nonsense false-positive
  rate at `T*`, the val top-1/top-3, and a one-line verdict.
- Full suite green. Commit on `v2-multiturn` (track the descriptions file + the
  report; the eval cache can be gitignored like the stress outputs). **Do NOT
  push.** Document the verdict + `T*` in LOG.md + STATUS.md.

## Explicitly out of scope (later tasks)

No fine-tuning / contrastive training (that's the next task, *if* the verdict
calls for it). No `lb`/router integration (that's the hybrid-wire task, after we
see the numbers). No multi-turn / dialogue acts (old Phase 2). No attention
visualization yet (we'll make the showcase figure once the model is settled). If
you're writing a training loop or editing the router, stop — wrong task.
