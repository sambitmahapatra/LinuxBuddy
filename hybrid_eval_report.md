# Hybrid End-to-End Eval — Report (Task 39)

*Measured through the real `lb` (rules → encoder-on-abstain → gate), not the encoder in isolation. Single-turn.*

## Coverage — rules-abstain cases the hybrid now resolves

- Probe: 32 phrasings (the stress gap set + the honest-5 residual).
- The rules abstain on **14** of them.
- The encoder resolves **10/14** of those through the gate, correctly leaving **4** abstained.

### What the encoder now handles that v1 couldn't

| phrasing | command | kind |
|---|---|---|
| where are the spreadsheets | `find . -name '*.csv'` | read |
| spreadsheet files please | `find . -name '*.csv'` | read |
| what changed in the last day | `find . -type f -mtime -1` | read |
| what changed in the last day in this directory | `find . -type f -mtime -1` | read |
| find the files modified in the last day | `find . -type f -mtime -1` | read |
| list everything here | `ls -la` | read |
| show me what's in this folder | `ls -la` | read |
| list everything here in this directory | `ls -la` | read |
| what processes are running | `ps aux` | read |
| what processes are running in this directory | `ps aux` | read |

### Correctly still abstained (no reasonable interpretation)

`got any spreadsheets?`, `find all the files here`, `what is this file`, `add pandas to my environment`

## Safety — destructive-on-nonsense (THE metric)

- Nonsense probe: 22 clearly out-of-scope/gibberish inputs.
- Commands emitted on nonsense: **0/22**.
- **Destructive commands on nonsense: 0 — PASS (zero leaks)**.

The two-threshold asymmetry (read `t_read`=0.55, destructive `t_destructive`=0.68 + `margin_min`=0.05) means a destructive intent needs a high, clear-margin match AND a concrete target the slot filler can extract — nonsense has neither, so it can never produce an rm/mv/chmod.

## Latency (cold, per fresh `lb` process — each Ctrl-G is one)

| path | median |
|---|---|
| fast (rule hit — no ML import) | 120 ms |
| cold abstain (model load + 1 encode + match) | 9911 ms |

The fast path never imports torch/sentence-transformers (asserted by a test), so rule hits stay at v1 latency (~120 ms) — the common case is unaffected. The abstain path, however, pays a cold per-process torch-import + model-load each Ctrl-G (~0.0 s). **That is too slow for a snappy widget on an abstain** (the disk-cached description embeddings remove the 85-encode, but the torch import + model load dominate and cannot be cached away per-process). **Recommended next step: a resident helper** — a small long-lived process that loads the model once and answers abstain queries over a socket, bringing the abstain path to tens of ms. NOT built here (the task explicitly scopes out a daemon); flagged as the follow-up.

## Guardrails (all verified by `tests/test_hybrid.py`)

1. **Rules first** — 0 regression diffs on rule-handled sweep rows (encoder on vs off).
2. **Intent, not command** — the encoder outputs an intent id; the existing slot filler → planner → renderer → gate build the command.
3. **Read/destructive asymmetry** — two thresholds; a destructive below its bar abstains honestly.
4. **Graceful degradation** — no model/deps or `LINUXBUDDY_ENCODER=0` → pure v1 (no crash).
5. **Off the fast path** — ML imported lazily only on abstain; the 85 description embeddings are disk-cached.

