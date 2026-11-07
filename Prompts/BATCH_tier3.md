# Tier 3 batch — the final domains

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md` first.

This batch completes all 9 domains. Execute IN ORDER:
1. `Prompts/15_chmod_kill.md`   — cheap follow-on: completes filesystem + processes
2. `Prompts/16_workspace.md`    — multi-step (scoped), the big new capability
3. `Prompts/17_wsl_interop.md`  — GUI/interop, hand-tested, LAST

After each: tests + maze verification where possible, update LOG.md and
STATUS.md, commit, don't push. Stop and report on unfixable failure.

## Rules (in addition to CLAUDE.md)

- **Destructive intents (chmod, kill, mkdir, touch) are gated** via the P2.0
  gate — they carry `risk_ops: [write]` (chmod/kill: consider `[privilege]`
  for chmod-of-others, but `[write]` is fine for V1). Reads work anywhere.
- **`cd`/`export` are fine** — they go into the user's shell buffer and the
  user's own shell runs them. That's the whole point of buffer injection.
  The CLI just emits the command string; it does not execute it.
- **Multi-step is SCOPED** (Task 16): build named fixed recipes
  (setup_project = mkdir dirs && cd), NOT arbitrary compound decomposition.
  Generalized compound support is explicitly V1.1 — do not attempt it here.
- **Nested command substitution `$(...)` is deferred** (Task 17): the
  flat-argv + round-trip model can't represent `cd $(wslpath $(cmd.exe …))`
  safely. Build the clean single-level intents; abstain on the nested ones.
- Keep all prior domains green (regression) after each task.

## After this batch

All 9 domains built. Phase 2 complete. Next is **install + dogfood**, then
decide Phase 3 (the LinearSVC intent model) and generalized multi-step from
real use — not speculatively.
