# Changelog

All notable changes to LinuxBuddy are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [2.0.0] — 2026-11-12

The hybrid release: the rules engine gains a **small local embedding model as a
fallback**, cross-turn context, and an offline learning loop — all still offline, no
LLM, no network, nothing auto-executed. The rules keep absolute priority; the encoder
fires only when they abstain, through the same compile → gate → render pipeline.

### Added
- **Fine-tuned MiniLM-L6 bi-encoder (Siamese / zero-shot).** A contrastive
  (MultipleNegativesRankingLoss) encoder matches a request to intent *descriptions*,
  so **27 of 85 intents are routable with no training data at all**. Wired as the
  rules fallback (`hybrid.py`); never builds a command string, only picks an intent.
- **Torch-free ONNX runtime.** The runtime abstain path uses onnxruntime + tokenizers
  + numpy only (torch/transformers are export-only). `pip install -e '.[ml]'`.
- **Multi-turn / attention context.** A session frame plus an attention-based
  coreference resolver (`session_resolver.py`) carries a query across turns and
  resolves elliptical follow-ups ("which of those is heaviest") — the pronoun binds
  to the turn-1 type via head **L4H4** (98% held-out coreference). Destructive
  elliptical turns are never recovered from context.
- **Offline, human-gated continual-learning loop.** Every abstain is logged locally
  (`feedback.py`, `lb --feedback`); a retrain loop (`ml/retrain.py`) folds real misses
  into a rehearsal buffer and only adopts a candidate that passes every frozen floor.
- `LINUXBUDDY_ENCODER=0` forces pure-rules (v1) behavior; graceful degradation when
  the ML extra isn't installed.

### Results
- **What the encoder adds** (frozen evals, rules-only vs hybrid): single-turn CORRECT
  **58.9% → 67.1%** (+44 of 538, for 5 misfires); novel elliptical recovery
  **0/14 → 11/14** (and 2 rules misroutes removed); **0 gate leaks**, no in-vocab
  regression.
- Fine-tune (held-out): **gap recovery 93%** (from 19% un-tuned), nonsense FP 3%, val
  top-1 72% / top-3 89%; zero-data tail intact (+8 pts).
- **Latency: ~10 s → ~258 ms** cold abstain (~40×, torch-free ONNX); rule hit ~49 ms.
- Continual-learning arc: naive rehearsal interferes (gate rejects) → balanced
  rehearsal mitigates (587 404→407, plasticity 17→25%) but lands one turn short — an
  honest data-scale limit under the unchanged 0-regression gate.

### Known limitations
- A few terse elliptical size turns ("the fat one", "add them all up") still abstain.
- The continual-learning loop does not fully close at the current data scale (one
  multi-turn turn short); a description-only intent is un-rehearsable by design.

[2.0.0]: https://github.com/sambitmahapatra/LinuxBuddy/releases/tag/v2.0.0

## [1.0.0] — 2026-11-09

First release of the rules-based engine: a local, fully offline CLI that turns
plain-English requests into Linux commands placed in the shell buffer for
review. No LLM, no network, no API key at runtime.

### Added
- Rule-based NL→Linux translation across 10 domains (navigation, file
  discovery, file inspection, text & logs, workspace & shell, filesystem
  permissions, processes, WSL interop, archives & backup, Python environments).
- Typed-argv plan with `shlex` round-trip safety — one slot value is always
  exactly one argv element; the shell string is rendered for display only.
- Shell-buffer injection widget (bash + zsh) bound to **Ctrl-G**, with tiered
  confirmation; nothing auto-executes.
- Exit-code risk signaling: `0` read-only / `1` abstain / `3` destructive.
- Containment safety gate — destructive operations refuse unless the cwd is
  under the maze root (`LINUXBUDDY_MODE` prototype/prod, `LINUXBUDDY_MAZE_ROOT`).
- Asymmetric-by-risk abstain policy (read-only leans toward emitting an editable
  command; destructive requires a confident parse).
- Deterministic 139-scenario evaluation harness and a fixed-timestamp test maze.

### Results
- 139-scenario sweep: **134/139** correct-or-honest-abstain, 0 regressions,
  maze integrity verified intact. **281 tests** passing. Reproducible: the
  routing columns were byte-identical across reruns (v2 == v3), and the Task-28
  cleanup changed only its 5 intended rows (v3 → v4).

### Known limitations
- Generic, ambiguous, and context-dependent requests abstain by design — e.g.
  "what is this file", "sort this list", and runtime-network asks like
  "install the requests package" (excluded on purpose). The v2 attention model
  is scoped to address these; v1 is rules-only by design.

[1.0.0]: https://github.com/sambitmahapatra/LinuxBuddy/releases/tag/v1.0.0
