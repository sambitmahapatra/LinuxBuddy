# LinuxBuddy — Current Status

> The single source of truth for where the project is NOW. Overwrite this
> after every task. Keep it short. Next session reads this first.

**Last updated:** 2026-11-03 (after Task 05 / P1.1)
**Current phase:** Phase 1 — Harden
**Branch:** v1-file-discovery

---

## Done

- Scoping, taxonomy (`kb/taxonomy.yaml`, 9 domains), 360 validated scenarios
- Test maze (`testlinuxbuddy/`) — deterministic, bindings + runtime setup
- **file_discovery domain works end to end** — 4 intents, rule-based NLU,
  planner, renderer with injection-safety proven, `lb` CLI.
- **P1.1 (Task 05) — both known bugs fixed.** Abstention gate: a defining
  slot missing → abstain, never a match-everything command. Plural/possessive
  file-type words normalize to the extension. 39 tests pass.
- All project docs in place (ROADMAP, WBS, HANDOVER, MAZE, CLAUDE)

## In progress

- **P1.2 (Task 06)** — verifying the 360 reference commands against the maze.

## Next (in order)

1. **P1.2** — run the 360 verification (`Prompts/06_verify_360.md`), raw verdicts
2. Then **Phase 2** — build the 8 remaining domains (see WBS)

## Open bugs

- None open in `file_discovery`. (Both P1.1 bugs fixed — see `LOG.md`
  2026-11-03.)

## Decisions the human still needs to make

- None open. (Release audience: owner + batchmates. Model: intent-only, Phase 3.
  All settled — see ROADMAP design rules.)

## Notes / watch-outs

- Only file_discovery is built. The other 8 domains do NOT exist yet.
- `lb` lives in a uv venv; destructive-intent gate not built until P2.0.
- Owner is on bash; only the zsh widget exists.
