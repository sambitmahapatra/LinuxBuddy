# Tier 2 batch — gate + 2 write-capable domains

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md` first.

Tier 2 domains WRITE files (tar creates archives, gzip compresses), so they
need the destructive-containment gate that Tier 1 didn't. Build the gate first.

Execute IN ORDER:
1. `Prompts/12_gate_infrastructure.md`   (P2.0 — required before any write intent)
2. `Prompts/13_archives.md`
3. `Prompts/14_python_env.md`

After each: tests + maze verification, update LOG.md and STATUS.md, commit,
don't push. Don't start the next until the current "Done when" is met. Stop and
report on unfixable test failure.

## Rules (in addition to CLAUDE.md)

- **Read intents work anywhere; write intents are gated** (prototype mode:
  cwd must be under the maze root). The gate reads `risk_ops` from the KB.
- **Single-command intents** still — compound requests abstain, as in Tier 1.
- **Reuse the 2-stage composition** the router already has (pipe + &&) for
  intents like `mkdir -p … && tar -xf …`.
- Keep all prior domains' tests green (regression) after each task.
- Defer anything that needs **network** (pip install), **shell state**
  (venv activate/deactivate — can't be a subprocess), or is **long-running**
  (http.server). Document what you deferred.

## After this batch — a cheap win worth noting

Once the gate (P2.0) exists, the destructive intents deferred in Tier 1 become
small additions: `chmod` (filesystem_permissions) and `kill`/`pkill`
(processes). They complete those two domains. Do them as a quick follow-on task
if time allows, or flag for next session. Not required to close this batch.

## Remaining after Tier 2

workspace_and_shell (multi-step) and wsl_interop (GUI) — the two hardest,
saved for last.
