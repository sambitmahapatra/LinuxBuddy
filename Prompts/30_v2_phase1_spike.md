# Task 30 — v2 Phase 1 spike: multi-turn 3-chain end-to-end (NO model yet)

Read `CLAUDE.md`, `STATUS.md`, `ROADMAP_V2.md`, recent `LOG.md`. This is the
**thin slice** for v2: prove the multi-turn *mechanic* with a session frame and
rules-based delta detection, before any ML. Build on a branch (e.g.
`v2-multiturn`), not on the v1.0.0 tag line directly — keep v1 pristine.

**Do NOT add a transformer, torch, or any model in this task.** Rules only. The
point is to make the state machine work and render through the existing v1
pipeline. The encoder arrives in Phase 2.

## The target (must work end-to-end, in a real shell, in the maze)

```
(cwd = testlinuxbuddy/project)
You: find CSV files larger than 100MB
LB : find . -name '*.csv' -size +100M
You: only the ones modified yesterday
LB : find . -name '*.csv' -size +100M -daystart -mtime 1
You: show the biggest one
LB : find . -name '*.csv' -size +100M -daystart -mtime 1 -printf '%s\t%p\n' | sort -rn | head -1
```

Plus a reset: after "never mind" (or a `cd`), the next request parses fresh.

## What to build

### 1. `SessionFrame` (new module, e.g. `src/linuxbuddy/session.py`)

A dataclass holding the running query (see ROADMAP_V2 §1 for the shape):
`op, targets{}, filters{}, modifier, cwd, history[], updated_at, shell_id`.
Methods: `merge(delta)`, `to_command_plan()` (produces the same plan object the
v1 planner consumes — reuse the existing plan/KB types; do NOT invent a parallel
renderer), `is_stale(ttl)`, `reset()`.

### 2. Session store (persist between `lb` invocations)

Each Ctrl-G is a fresh process, so the frame must persist to disk. Key by the
parent shell: `~/.cache/linuxbuddy/session_<PPID>.json` (use `os.getppid()`).
Load at start of each `lb` call, save at end. Honour a **TTL** (default 10 min)
and clear on explicit reset words ("start over", "reset", "never mind",
"forget it"). Create the cache dir if missing; tolerate a missing/corrupt file
(treat as empty frame).

### 3. Rules-based dialogue-act + delta detector (spike-grade)

Just enough to drive the target chain and the reset. Detect:
- **new** — a self-contained request (has its own op + target). → parse via the
  existing v1 NLU into a fresh frame.
- **refine** — starts with "only/just/and/also", or is a bare constraint phrase
  with no new op ("modified yesterday", "bigger than 10MB", "the python ones").
  → extract the constraint as a **delta** and merge into the current frame's
  `filters`/`targets`. Keep existing slots (don't clobber `-name`/`-size`).
- **operate** — "show the biggest one", "the biggest", "count them", "sort them",
  "the first N". → set `op`/`modifier` on the current frame, keep its filters.
  Resolve the elided target ("one"/"them"/"it") to the current frame's targets.
- **reset** — the reset words above → clear the frame, then treat the rest (if
  any) as new.

If the detector can't classify a turn AND there's no usable frame → fall back to
the normal v1 single-turn path (safe default). Never guess a destructive op from
a vague refinement.

### 4. Rendering

`SessionFrame.to_command_plan()` → **existing planner → renderer → gate**. The
command must go through the v1 safe pipeline unchanged (shlex round-trip,
containment). For "show the biggest one", render the compose form the v1 planner
already supports (`find … -printf '%s\t%p\n' | sort -rn | head -1`) via the
Stages/pipe mechanism — do not hand-concatenate a pipe string.

### 5. CLI surface

- The widget/CLI flow is unchanged (type → Ctrl-G → command in buffer). Multi-turn
  works because the session store carries state between calls.
- Add `lb --frame` to print the current session frame (debugging / the demo).
- Add `lb --reset` (and the reset words) to clear it.

## Semantics to get right (the chain hinges on these)

- "modified yesterday" → `-daystart -mtime 1` (not `-mtime 0`). Document the
  choice; "today" → `-daystart -mtime 0`.
- "the biggest one" → `op=show`, `modifier=max-by-size` → the
  `-printf '%s\t%p\n' | sort -rn | head -1` form, carrying the accumulated
  filters. ("show" here = identify the largest; a later "open it"/"cat it" turn
  would show contents — out of scope for the spike.)
- "only the ones" → refine (narrow the existing set), NOT a new query.

## Tests & done

- Unit: `SessionFrame.merge` accumulates filters without clobbering; TTL/reset
  clears; store round-trips to disk.
- Integration: the **3-turn chain** yields the three expected commands when fed
  in order through the session store; a reset mid-chain re-parses fresh; an
  unrelated turn after the chain (act=new) replaces the frame.
- Regression: the **139 single-turn sweep is unchanged** — single-turn behavior
  must not shift (run it, diff routing vs v4; expect 0 changes).
- Manual: run the target chain in a real bash session in the maze and confirm
  each command lands in the buffer (don't auto-run destructive).

`pytest` green. Commit on the v2 branch, don't push. Document in LOG.md: the
frame shape, the store key/TTL/reset choices, and the `-daystart` decision.
Update STATUS.md to mark v2 Phase 1 started.

## Explicitly out of scope (Phase 2+)

No transformer, no torch, no embeddings, no coreference beyond the simple elided
"one/them/it" → current-target binding, no CUDA. Keep the slice thin.
