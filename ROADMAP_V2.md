# LinuxBuddy v2 — Roadmap (context-aware, multi-turn)

**Goal:** make LinuxBuddy understand *context* — resolve references and refine
across turns — using an attention-based encoder, while keeping v1's safety and
determinism intact. The target interaction:

```
You: find CSV files larger than 100MB
LB : find . -name '*.csv' -size +100M
You: only the ones modified yesterday
LB : find . -name '*.csv' -size +100M -daystart -mtime 1
You: show the biggest one
LB : find . -name '*.csv' -size +100M -daystart -mtime 1 -printf '%s\t%p\n' | sort -rn | head -1
```

**North star:** multi-turn refinement. Each turn edits a running query, not a
fresh parse.

---

## 1. Architecture (locked)

**Principle: augment, don't replace.** The transformer upgrades the *front half*
(understanding). v1's *back half* (planner → renderer → gate) still builds and
vets every command, so the model never emits raw shell and the safety boundary
is unchanged.

**Encoder-only, rules-first, over an explicit session frame.** No generative
model (flan-t5 et al. rejected: slower, GPU-bound, less scalable, opaque — loses
on every one of elegance/efficiency/scalability/feasibility). A fine-tuned
encoder is ~0–60 ms, CPU-capable, offline, and its attention over the
conversation is *visualizable* — the showcase figure.

### Components

| component | role | status |
|---|---|---|
| **Rules NLU** (v1) | fast deterministic first pass; handles the 134/139 | built |
| **Session frame** | mutable query state carried across turns | NEW |
| **Session store** | persists the frame between `lb` invocations (each Ctrl-G is a fresh process) | NEW |
| **Encoder** (DistilBERT/MiniLM, ~22–66M) | shared attention backbone, 3 heads | NEW |
| → intent head | embedding match vs intent *descriptions* → **zero-shot** | NEW |
| → dialogue-act head | classify turn: new / refine / operate / reset | NEW |
| → coreference head | resolve "the ones", "the biggest one", "it", "those" | NEW |
| **Frame updater** | merge (act, delta) into the running frame — deterministic | NEW |
| **Planner → Renderer → Gate** (v1) | build + `shlex`-vet + containment-check | built |
| **Continual loop** | dogfood + multi-turn sweep → relabel → re-fine-tune | harness built |

### The session frame (the heart)

```
SessionFrame {
  op:        find | show | grep | sort | count | cat | ...   # the verb
  targets:   { type:*.csv, name:…, path:… }                  # what
  filters:   { size:>100M, mtime:yesterday, … }              # constraints (ACCUMULATE)
  modifier:  max-by-size | head:N | unique | …               # "the biggest one", "top 10"
  cwd:       <resolved at turn time>                         # where (context)
  history:   [ prior turns / prior frames ]                 # for coreference
  updated_at, shell_id
}
```

Each turn produces a **(dialogue_act, delta)**; the updater applies it; the
planner renders the frame. The frame is **inspectable** — `lb --frame` can print
it, which is how drift is debugged and how the human stays in control.

### Per-turn data flow

```
turn text + loaded session frame + short history
  │
  ├─ Rules NLU ── confident, self-contained single-turn? ──► v1 path (fast) ──┐
  │                                                                           │
  └─ else → Encoder:                                                          │
        act = dialogue_act(turn, frame.history)                               │
        ├ new     → frame = parse(turn)                                       │
        ├ refine  → frame.filters += extract_delta(turn)                      │
        ├ operate → frame.op/modifier = resolve(turn, frame)  ("biggest one") │
        └ reset   → frame = empty                                             │
        coref: bind "the ones/one/them/it" → frame.targets/filters            │
        confidence τ ?                                                        │
          ├ ≥ τ → Planner(frame) → Renderer(shlex) → Gate ──────────────────►├─► buffer
          └ < τ → abstain (safe)                                              │
                                                                             save frame
```

### Session persistence (a real requirement, easy to miss)

Each Ctrl-G runs a **fresh `lb` process**, so the frame cannot live in memory —
it must persist to disk between turns. Key it to the **terminal**: the widget
runs `lb` as a child of the interactive shell, so `$PPID` = the shell's PID,
stable across turns in one window. Store at
`~/.cache/linuxbuddy/session_<PPID>.json`.

**Reset heuristics** (frame clears): explicit "start over"/"reset"/"never mind";
a TTL (e.g. 10 min since last turn); dialogue-act = `new`; optionally a `cd` that
changes context. Document the chosen set.

### Safety carries over, and multi-turn is *safe here by construction*

Because LinuxBuddy **shows every command for review before Enter**, a mis-read
turn produces a visible wrong command the user simply rephrases — multi-turn
drift is self-correcting. This human-in-the-loop checkpoint is the project's
novel safety claim: refinement chains that are dangerous in auto-executing
agents are safe in a review-first tool. The containment gate still blocks
destructive ops outside the maze; destructive turns still signal exit 3.

---

## 2. How the three required concepts map

| concept (rubric) | where it lives | the demonstrable artifact |
|---|---|---|
| **Attention / Transformers** | the encoder backbone; self-attention over the dialogue window | **attention-weight viz**: "the biggest **one**" → "CSV files larger than 100MB" |
| **Siamese / Zero-shot** | intent head = bi-encoder matching request ↔ intent *description* | held-out intent (never trained) still routes correctly |
| **Continual learning** | dogfood + multi-turn sweep → relabel → re-fine-tune | cycle-over-cycle improvement curve on the sweep |

Problem statement for the professor: *attention applied to context-aware,
multi-turn natural-language→shell refinement, with a visualizable coreference
mechanism, in a tool with immediate real-world use and a human-in-the-loop
safety guarantee.* Real application, novel, and the attention is the brain of it.

---

## 3. Phases (each with a gate; v1's 139-sweep is the regression floor throughout)

**Phase 0 — Setup** *(mostly done)*
- Verify CUDA-on-WSL: `nvidia-smi` in WSL + `torch.cuda.is_available()` → True.
  (If not, train on CPU — the encoder is small enough.)
- Pin deps (torch, transformers, sentence-transformers) in a v2 extra.
- **Gate:** GPU visible OR CPU fallback confirmed; deps install clean.

**Phase 1 — The spike (thin slice, NO model yet)**
- Build `SessionFrame` + session store + a **rules-based** delta/act detector —
  just enough to make the exact 3-turn chain work end-to-end, rendering through
  the v1 planner.
- **Gate:** the 3-turn chain produces the three correct commands; a reset clears
  the frame; `lb --frame` prints state. *Prove the mechanic before adding ML.*

**Phase 2 — The encoder, single-turn first**
- Fine-tune the encoder: intent head (zero-shot via descriptions) + dialogue-act
  head. Wire as a **fallback behind rules** for single-turn.
- Re-run the **139 single-turn sweep**.
- **Gate:** ≥ 134/139 maintained (no regression), recovers ≥ some residual, and a
  held-out intent routes zero-shot.

**Phase 3 — Multi-turn context (the heart)**
- Add the coreference head; frame-carry across turns; the encoder now drives
  act-classification + coref (replacing Phase-1 rules for the hard cases, rules
  still the fast path).
- Build the **multi-turn sweep** (§5) and score it.
- **Gate:** multi-turn sweep ≥ target (set after first run); the 3-turn chain and
  its variants pass; 139 single-turn floor intact.

**Phase 4 — Continual learning**
- Formalize dogfood + sweep misses → relabel → re-fine-tune. Run ≥ 2 cycles.
- **Gate:** measured improvement cycle-over-cycle (the graph for the report).

**Phase 5 — Integration, ablation, report**
- Tune τ (confidence→abstain); ablation: rules-only vs +intent vs +multi-turn.
- Produce the attention-visualization figure.
- **Gate:** report-ready results; tag **v2.0.0**.

---

## 4. Visual map

```
                         ┌───────────────────────────────────────────────┐
   you type a request    │                  LinuxBuddy v2                 │
   press Ctrl-G  ───────►│                                               │
                         │   load SessionFrame  (~/.cache/.../PPID.json)  │
                         │        │                                       │
                         │        ▼                                       │
                         │   ┌──────────┐  confident single-turn          │
                         │   │ Rules NLU │────────────────┐               │
                         │   └──────────┘                 │               │
                         │        │ abstain / contextual  │               │
                         │        ▼                        │              │
                         │   ┌──────────────────────────┐  │              │
                         │   │  Encoder (attention)      │  │              │
                         │   │  • intent  (zero-shot)    │  │              │
                         │   │  • dialogue-act           │  │              │
                         │   │  • coreference            │  │              │
                         │   └──────────────────────────┘  │              │
                         │        │ (act, delta)            │             │
                         │        ▼                         │             │
                         │   update SessionFrame ◄──────────┘             │
                         │        │                                       │
                         │        ▼                                       │
                         │   Planner → Renderer(shlex) → Gate  (v1, safe) │
                         │        │                                       │
                         │   save SessionFrame                            │
                         └────────┼──────────────────────────────────────┘
                                  ▼
                       command in your shell buffer  → you review → Enter
                                  │
                   (miss?) ───────┘ → dogfood log → relabel → re-fine-tune (continual)
```

---

## 5. Multi-turn data-generation plan

Same philosophy as the 139 single-turn sweep: a hand-curated, ordered,
ground-truthed set that doubles as the regression eval and the training corpus.

### Schema — `data/eval/multiturn_scenarios.csv`

```
chain_id, turn_no, request, expected_act, expected_frame, expected_cmd_shape, cwd, risk, notes
```

- A **chain** = several rows sharing `chain_id`, in `turn_no` order.
- `expected_act` ∈ {new, refine, operate, reset, abstain}.
- `expected_frame` = the accumulated frame *after* this turn (compact JSON/shorthand).
- `expected_cmd_shape` = the command that should render (hint, not asserted byte-wise).

### Turn-type coverage (what makes a chain a good test)

- **refine-add-filter:** "only the ones modified yesterday", "just the big ones", "the python ones too"
- **operate-on-result:** "show the biggest one", "count them", "sort by size", "just the first 5"
- **coreference:** "open it", "show that log", "delete those" (destructive → exit 3)
- **reset / topic-switch:** an unrelated new query mid-session → must reset, not refine
- **ambiguous:** "do that again", "the other one" with no antecedent → abstain

### Method

1. **Seed from single-turn.** Take v1 intents as turn-1 bases; append 1–3
   refinement/operate turns each.
2. **Vary:** domains, chain length (2–4 turns), phrasing, and end some chains in
   a destructive turn (safe in the maze, throwaway-copy execution as in Task 24).
3. **Volume:** ~8–10 **gold chains hand-written for Phase 1** (incl. the target
   chain below); grow to ~40–60 for Phase 3; then dogfooding feeds it (continual).
4. **Label** each turn with `expected_act` + delta — this is the training signal
   for the act + coref heads.

### Example chains (seed set)

```
C001,1,find CSV files larger than 100MB,new,{op:find,type:*.csv,filters:{size:>100M}},find . -name '*.csv' -size +100M,project,read,target chain
C001,2,only the ones modified yesterday,refine,{...,filters:{size:>100M,mtime:yesterday}},find . -name '*.csv' -size +100M -daystart -mtime 1,project,read,
C001,3,show the biggest one,operate,{op:show,modifier:max-by-size,...},find ... -printf '%s\t%p\n' | sort -rn | head -1,project,read,
C002,1,show me the logs,new,{op:find,type:*.log},find . -name '*.log',project,read,
C002,2,just the errors in them,operate,{op:grep,pattern:error,targets:*.log},grep -niF -- error *.log,project/logs,read,coref: "them"
C002,3,how many,operate,{op:count,...},grep -ciF -- error *.log,project/logs,read,coref: elided target
C003,1,find big datasets,new,{op:find,filters:{size:large}},find . -type f -size +50M,project,read,
C003,2,never mind, what's running,reset,{op:ps},ps aux,project,read,topic switch → reset
```

### The multi-turn sweep harness (Phase 3)

Extend Task 24: for each chain, run the turns **in order through `lb` with the
persistent session store**, capture the frame + command at each turn, score
`expected_act` and `expected_cmd_shape`. **Reset the session between chains.**
Same guards (timeout, GUI-skip, throwaway maze for destructive, MANIFEST check).
Output `multiturn_results.csv`; the single-turn 139 stays the floor.

---

## 6. Risks & mitigations

- **Error compounding across turns** → the review-before-Enter checkpoint makes
  it self-correcting; also `lb --frame` surfaces state.
- **Non-determinism from the model** → rules-first (model only on fallback); the
  139 single-turn sweep is a hard regression floor; model proposes structure,
  never raw shell.
- **Small data** → pretrained encoder + zero-shot descriptions (adapt, don't
  train from scratch); continual loop grows the corpus.
- **Session-state staleness** → TTL + reset heuristics; frame is cheap to clear.
- **Latency creep** → keep the encoder small; rules short-circuit the common case.

## 7. Success criteria

- Phase 1: target 3-turn chain works end-to-end (mechanic proven).
- Phase 2: 139 floor held; zero-shot intent demonstrated.
- Phase 3: multi-turn sweep passing at target; the target chain + variants green.
- Phase 4: cycle-over-cycle improvement curve.
- Phase 5: ablation table + attention-viz figure; **v2.0.0 tagged**.
