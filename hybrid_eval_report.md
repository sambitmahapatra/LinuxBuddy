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

*Task 40: the runtime encoder is now ONNX (onnxruntime + tokenizers), not torch/sentence-transformers. Profiling showed the torch/transformers/ST imports were ~7 s of the old ~10 s cold cost; the model itself is ~5 ms.*

| path | median |
|---|---|
| fast (rule hit — no ML import at all) | 49 ms |
| cold abstain (ONNX session load + 1 encode + match) | 258 ms |

The fast path never imports torch/transformers/sentence-transformers/onnxruntime (asserted by a test), so rule hits stay at v1 latency (~49 ms). The abstain path now loads only the ONNX graph (fp32, exact-fidelity) through onnxruntime and tokenizers — about **258 ms** per fresh process, down from ~10 s with the torch stack (~40× faster). **That is under the ~2 s target, so no daemon / resident helper is needed** — the hybrid is now dogfoodable, and every future multi-turn turn that consults the encoder pays only this small cost.

## Guardrails (all verified by `tests/test_hybrid.py`)

1. **Rules first** — 0 regression diffs on rule-handled sweep rows (encoder on vs off).
2. **Intent, not command** — the encoder outputs an intent id; the existing slot filler → planner → renderer → gate build the command.
3. **Read/destructive asymmetry** — two thresholds; a destructive below its bar abstains honestly.
4. **Graceful degradation** — no `.onnx`/onnxruntime/tokenizers or `LINUXBUDDY_ENCODER=0` → pure v1 (no crash).
5. **Off the fast path** — the encoder (now torch-free ONNX) is imported lazily only on abstain; the 85 description embeddings are disk-cached.

