# Task 36 — v2 Phase 0: training data generation (NO model yet)

Read `CLAUDE.md`, `STATUS.md`, `ROADMAP_V2.md`, recent `LOG.md`. Branch
`v2-multiturn`. **Data only — do NOT touch any LinuxBuddy source, the rules, or
the KB contents.** This builds the labeled corpus the Phase-1 encoder will train
on. No torch, no transformers in this task.

## Why this task is first (and why label discipline matters)

The Phase-1 encoder is a *fallback behind the rules*. Its predicted labels must
be the **exact intent ids the router/planner already use**, or its output can't
plug into the hybrid router in Phase 1. So the KB is the single source of truth
for the label space. We do NOT invent labels, and we do NOT trust the stress
test's ad-hoc `category` column (those were the test agent's own names).

## Part A — extract the authoritative label space (do this FIRST)

1. Enumerate every intent id the system actually has, from the KB
   (`kb/commands/*.yaml`) and the router/planner. Produce `data/label_space.json`:
   ```json
   {
     "intents": ["file_discovery.find_by_type", "file_discovery.find_by_size",
                 "file_management.copy", "file_management.delete", ...],
     "dialogue_acts": ["new", "refine", "operate", "reset", "fallback"],
     "special": ["_ABSTAIN"]
   }
   ```
   Use whatever granularity the KB uses for intents — match it exactly (same
   strings, same casing). If the KB groups by domain with sub-intents, keep that
   structure. `_ABSTAIN` is a real label: it's what the encoder must emit for
   out-of-domain / vague input instead of forcing a wrong intent.
2. Print the full intent list and the count. This list is frozen for Phase 1 —
   every training example's label must be one of these strings.

## Part B — single-turn labeled dataset

Pull real utterances from the data we already have. Each example:
```json
{"text": "find all the python files", "intent": "file_discovery.find_by_type",
 "domain": "file_discovery", "source": "sweep", "seed_id": "E012"}
```

Sources, in priority order:

1. **`sweep_scenarios.csv` (147 rows) — already labeled.** It has `intent` and
   `domain` columns. Map each row's `intent` to the frozen label space. If any
   sweep intent string doesn't match the label space exactly, STOP and report
   the mismatch (don't silently remap) — it means the KB and sweep have drifted
   and we need to reconcile before training.

2. **Stress-test failures — the valuable gap examples.** From
   `stress_test_results.csv`, take the rows judged `WRONG_COMMAND` or
   `UNEXPECTED` where a reasonable intent exists (the 22 rules-ceiling
   phrasings, e.g. "list all python files", "where are the spreadsheets", "what
   changed in the last day", "clone config.yaml", "set up a folder called
   reports"). **Label each one by hand against the frozen label space** — these
   are exactly the cases the rules miss, so they're the highest-value training
   signal. Record `source: "stress_gap"`.
   - For the destructive synonyms that degraded to a read (clone/replicate →
     find, "set up a folder" → cd, erase/nuke/wipe → find): label them with the
     correct destructive intent they SHOULD have hit (clone → file_management.copy,
     etc.). That's the whole point — teach the encoder the synonym.

3. **Abstain / out-of-domain negatives.** From the stress test, take the rows
   judged `ABSTAIN_OK` (the vague + nonsense: "clean up the temp files", "what
   is the meaning of life", "asdfghjkl", "banana telephone sunshine"). Label
   them `_ABSTAIN`. Add a handful more nonsense/off-topic lines so the encoder
   has enough negatives to learn the abstain boundary (aim ~10-15% of the final
   set is `_ABSTAIN`). Without these the encoder will confidently misclassify
   garbage — abstain must be a learned class, not an afterthought.

Write the raw (un-augmented) single-turn set to `data/single_turn.raw.jsonl`.
Report: total count, count per intent, count of `_ABSTAIN`, count per source.

## Part C — multi-turn dataset (dialogue acts + frame deltas)

Each turn in a chain is one example:
```json
{"chain_id": "C001", "turn": 2,
 "text": "only the ones modified yesterday",
 "prev_frame": {"name": "*.csv", "size": "+100M"},
 "dialogue_act": "refine",
 "frame_delta": {"mtime": "-daystart -mtime 1"},
 "source": "roadmap_seed"}
```

Sources:
1. The ROADMAP_V2 seed chains (incl. C001, the golden find→refine→operate chain).
2. The 9 session chains the stress test exercised (they're in
   `stress_test_results.csv` as `Session` rows — the `c*_*` rows carry the
   utterance and the resulting command; the `chain:*` assertion rows carry the
   frame state). Reconstruct each chain's turns with their dialogue act.
3. Author ~10-15 more short chains by hand to cover acts that are thin:
   especially `reset` (reset words), `operate` (count/biggest/sort them), and
   cross-domain `new`-replaces-`new`. Keep them realistic and inside-maze.

Write to `data/multi_turn.raw.jsonl`. Report count per dialogue_act (they will
be imbalanced — note it; Phase-2 will weight the loss).

## Part D — augmentation (TRAIN SPLIT ONLY — leakage is the trap)

The corpus is small (~200 real single-turn). Augment to ~500-800, but **only
after the split, and only the train side**, grouped by `seed_id`/`chain_id` so
no variant of a val example leaks into train.

Deterministic, offline, rule-based augmentation (NO LLM, NO paraphrase model):
- **Synonym substitution** from a small curated bank you define in
  `data/synonyms.json` (e.g. find↔locate↔show me↔list, delete↔remove↔get rid
  of, folder↔directory, file↔files). Document the bank.
- **Filler/politeness injection**: prepend/append "please", "can you", "could
  you", "for me" occasionally.
- **Word dropout**: drop a low-information token ("all", "the", "me") with low
  probability.
- **Filename/extension swap**: swap the concrete filename or extension for
  another from a fixed pool (config.yaml→settings.json, *.csv→*.log) — keeps the
  intent, varies the surface. Do NOT do this for `_ABSTAIN` rows.

Each augmented row keeps its parent's `intent`/`dialogue_act` and records
`source: "aug:<transform>"` and `parent_seed_id`. Set a fixed random seed so the
run is reproducible. Cap augmentation per seed (e.g. ≤4 variants) so no single
seed dominates.

## Part E — split + final files

1. **Split at the seed/chain-group level, 80/20, stratified by intent**
   (so rare intents appear in both). A seed and all its augmentations stay on
   the same side. Multi-turn: split whole chains, never split a chain across
   train/val.
2. Write: `data/train.jsonl`, `data/val.jsonl` (single-turn),
   `data/train_mt.jsonl`, `data/val_mt.jsonl` (multi-turn).
3. Write `data/DATA_CARD.md`: total counts, per-intent counts (train/val),
   `_ABSTAIN` share, augmentation multiplier, per-dialogue-act counts, the
   synonym bank summary, the random seed, and an explicit note that augmentation
   is train-only and the split is group-level (no leakage).

## Tests & sanity checks (`tests/test_data.py`)

- **Label validity:** every `intent` in train/val is in `data/label_space.json`;
  every `dialogue_act` is valid. Fail loudly on any unknown label.
- **No leakage:** no `seed_id`/`chain_id` appears in both train and val; assert
  the intersection is empty.
- **Abstain present:** `_ABSTAIN` is in both splits and is 8-20% of single-turn.
- **Schema:** every row parses, has the required keys, non-empty `text`.
- **Stratification:** every intent with ≥2 examples appears in train; report any
  intent that's val-only or has <3 train examples (these will train poorly —
  flag them, don't fail).
- **Reproducibility:** running the generator twice with the same seed yields
  identical files (byte-for-byte).

## Done when

- `data/label_space.json` matches the KB intents exactly (0 drift, or the drift
  is reported and reconciled).
- `data/train.jsonl` + `data/val.jsonl` (~500-800 single-turn total) and the
  `_mt` pair exist, all labels valid, 0 leakage, abstain class present.
- `data/DATA_CARD.md` written; `tests/test_data.py` green.
- Generator script `src/linuxbuddy/ml/make_dataset.py` is reproducible
  (fixed seed), runnable as `python -I -m linuxbuddy.ml.make_dataset`.
- Commit the generator, the data files, the synonym bank, the data card, and the
  test on `v2-multiturn`. **Track the data/ files** (unlike the ephemeral stress
  outputs — this corpus is the training input, it belongs in git). Do NOT push.
- Document in LOG.md + STATUS.md: the label count, the final dataset size, the
  abstain share, and any intents flagged as under-represented (Phase-1 will
  watch those in the confusion matrix).

## Explicitly out of scope (Phase 1+)

No torch, no transformers, no tokenizer, no training, no CUDA. If you find
yourself importing a model, stop — that's Task 38. This task ends with clean,
labeled, leak-free `.jsonl` files and a data card.

## Note on the stress-test observation

The stress agents clustered around find/grep phrasings and under-explored the
destructive + multi-turn edges — so the single-turn gap corpus is richer than
the multi-turn one. That's why Part C asks you to hand-author extra chains: the
multi-turn training data needs topping up that the stress run didn't provide.
