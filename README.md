# LinuxBuddy

**LinuxBuddy translates plain-English requests into Linux shell commands and
places them in your shell buffer — for you to read, edit, and run.** It never
runs anything on its own.

It stays **local and offline**: no network call and no API key at runtime, and
**no LLM or generative model** in the loop. v1 is pure hand-written rules; v2 adds
a small **local embedding model** (a fine-tuned MiniLM bi-encoder, run through an
ONNX runtime with no PyTorch at runtime) as a *fallback the rules can lean on* —
still offline, still deterministic once trained, still nothing leaving your machine.

## Who it's for

Someone skilled who was handed Linux as a *tool*, not a subject to study — for
example a data scientist or ML engineer working in WSL2, expert in their field but
new to the terminal and without the time to learn it as a discipline.

You say what you want — *"find the biggest files in downloads"*, *"which lines
mention warning"*, *"what's my PATH"* — and LinuxBuddy produces the command.

## Architecture (v2) — rules-first hybrid

```
request
  │
  ├─ 1. RULES  (hand-written intent/slot NLU + typed-command KB)   ← absolute priority, ~ms
  │      hit → typed argv plan
  │      miss (abstain) ↓
  ├─ 2. ENCODER FALLBACK  (fine-tuned MiniLM bi-encoder, ONNX)     ← only on a rules miss
  │      picks an INTENT by matching the request to intent *descriptions*;
  │      slots are filled by REUSING the rules' own detectors
  │      low confidence / destructive-without-confidence → abstain ↓
  ├─ 3. MULTI-TURN  (session frame + attention coreference resolver)
  │      an elliptical follow-up ("which of those is heaviest") binds back to the
  │      running query via the encoder's attention, then resolves to a command
  │
  └─ every abstain is logged offline → an optional, human-gated retrain loop
         compile → containment gate → render → your shell buffer   (ONE pipeline for all paths)
```

Key properties, all preserved from v1:
- **The plan is a typed argv list, never a string** — one slot value becomes exactly
  one argv element, checked with a `shlex` round-trip. The encoder picks an *intent*;
  it never builds a command string.
- **The rules keep absolute priority.** The encoder runs *only* when the rules
  abstain, through the *same* compile → gate → render pipeline. `LINUXBUDDY_ENCODER=0`
  forces pure-rules behavior, identical to v1.
- **Graceful degradation.** No ML dependency installed, or any failure on the encoder
  path → LinuxBuddy behaves exactly as v1 (pure rules). The fast rule-hit path never
  imports the ML stack.

## Install

```bash
# pure rules (v1 behavior) — stdlib only, Python 3.10+:
pip install -e .

# the full hybrid (adds the ONNX encoder fallback at runtime):
pip install -e '.[ml]'          # onnxruntime + tokenizers + numpy (no torch at runtime)
```

Put `lb` on your `PATH` (the editable install provides the console script), then
source the shell widget from your rc so you get the keybinding:

```bash
# ~/.bashrc
source /path/to/linuxbuddy/shell/linuxbuddy.bash
# ~/.zshrc
source /path/to/linuxbuddy/shell/linuxbuddy.zsh
```

(The model artifacts for the hybrid are built by the offline export pipeline under
`src/linuxbuddy/ml/`; torch/transformers are **export-only**, never a runtime
dependency.)

## Usage

Type a request, press **Ctrl-G**. The line is **replaced** by the suggested command
— editable, cursor ready, **not run**. Read it, change it if you like, press
**Enter**. Nothing executes without that keystroke. You can also call it directly:
`lb "find logs over 100mb"`.

**Multi-turn** (hybrid): refine a query across turns, including elliptical follow-ups.

```
$ find the csv files            → find . -name '*.csv'
$ only the ones over 2mb        → find . -name '*.csv' -size +2M
$ which of those is heaviest    → find . -name '*.csv' -size +2M -printf '%s\t%p\n' | sort -rn | head -1
```

The third turn names no type or filter — the attention resolver binds *"those"* back
to the running query. A destructive elliptical turn (*"get rid of those"*) is
**refused** (it never fills an `rm` target from context).

**Tiered confirmation, signaled by exit code:**

| Request | Behavior | Exit code |
|---------|----------|-----------|
| Read-only (`find`, `grep`, `ls`, …) | command appears silently | `0` |
| Vague / no operation named | abstains with a short hint, no command | `1` |
| Destructive (write / delete / chmod / kill) | command appears with a warning | `3` |
| Encoder-interpreted | a "review before running" note on stderr; stdout is still exactly the command | `0`/`3` |

## What the encoder adds (the honest number)

By design the rules handle the bulk and the encoder fires only on a minority (the
rules-abstains). Measured on the **frozen** evals, rules-only vs full hybrid:

**538 single-turn scenarios:**

| bucket | rules only | hybrid | delta |
|---|---|---|---|
| CORRECT | 317 (58.9%) | **361 (67.1%)** | **+44** |
| MISROUTE | 54 | 59 | +5 |
| ABSTAIN | 167 | 118 | −49 |
| GATE_LEAK | 0 | 0 | 0 |

**Frozen multi-turn eval:**

| metric | rules only | hybrid |
|---|---|---|
| in-vocab no-regression | 24/24 | 24/24 |
| novel elliptical recovered | **0/14** | **11/14** |
| novel → misroute (wrong command) | 2/14 | **0/14** |
| destructive elliptical abstain | 3/3 | 3/3 |

So the encoder converts ~50 rules-abstains into **+44 correct** single-turn commands
(for 5 honest misfires), recovers **11/14** novel elliptical follow-ups, and even
*removes* 2 rules misroutes — at **0 gate leaks** and no in-vocab regression.

Two things that number *doesn't* capture but are real: **27 of the 85 intents carry
no training data** and are routable by their description alone (zero-shot), and the
whole thing has an **offline, human-gated learning loop** that rules can't have. The
headline: *rules alone 58.9% → hybrid 67.1%, plus zero-shot extensibility and a
learning loop.* See [`CONCEPTS.md`](CONCEPTS.md) for the full writeup.

## Safety model — containment

The safety guarantee is **containment**. In the default **prototype** mode, any
destructive operation (write / delete / permission change) is **refused unless the
current directory is under the maze root**; read-only intents work anywhere.
Encoder-chosen destructives are gated identically, and a destructive turn is never
recovered from context.

- `LINUXBUDDY_MODE` — `prototype` (default) or `prod` (lifts the gate).
- `LINUXBUDDY_MAZE_ROOT` — the directory under which destructive commands are allowed
  in prototype mode.

There is **one rendering path**: LinuxBuddy always renders the genuine command (`rm`,
`chmod`, `find -delete`) — no "safe-rewrite" mode. Safety comes from the gate and from
the fact that you press Enter.

## Coverage — 10 domains

Navigation · File discovery · File inspection · Text & logs · Workspace & shell ·
Filesystem permissions · Processes · WSL interop · Archives & backup · Python
environments.

## Performance

The abstain → encoder path is **torch-free at runtime** (ONNX + tokenizers + numpy).
Cold abstain latency is **~258 ms** (down from ~10 s before the ONNX runtime, ~40×),
and a rules hit stays ~49 ms and imports no ML stack — no daemon needed.

## Known limits (honest)

- **Residual terse size turns.** A few very terse elliptical follow-ups still abstain
  — e.g. *"the fat one"*, *"add them all up"* — below the read threshold. LinuxBuddy
  abstains rather than guess.
- **Continual-learning data scale.** The offline retrain loop demonstrably learns new
  phrasings (held-out plasticity rises) under a strict 0-regression gate, but at the
  current data scale (a 49-turn multi-turn floor) a balanced-rehearsal cycle lands
  *one* turn short of adoption — an honest data limit, documented in
  [`continual_learning_report.md`](continual_learning_report.md), not a weakened gate.
- A description-only (zero-shot) intent is **un-rehearsable** by the CL loop — a real
  tension between the zero-shot and continual-learning designs (see `CONCEPTS.md`).

## Evidence & reproducibility

- Frozen evals under `data/eval/` (587 single-turn dogfood + the multi-turn eval);
  the rules-vs-hybrid measurement scripts are in `experiments/task48_release/`.
- Reports: `finetune_report.md` (Siamese/zero-shot), `attention_spike_report.md` +
  the L4H4 figures in `experiments/task44_spike/` (attention), and
  `continual_learning_report.md` (the continual-learning arc).
- Full test suite passes (pure-`.venv` rules path and `.venv-ml` hybrid path).
