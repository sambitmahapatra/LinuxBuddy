# LinuxBuddy — Current Status

> The single source of truth for where the project is NOW. Overwrite this
> after every task. Keep it short. Next session reads this first.

**Last updated:** 2026-11-03 (initial)
**Current phase:** Phase 1 — Harden
**Branch:** v1-file-discovery

---

## Done

- Scoping, taxonomy (`kb/taxonomy.yaml`, 9 domains), 360 validated scenarios
- Test maze (`testlinuxbuddy/`) — deterministic, bindings + runtime setup
- **file_discovery domain works end to end** — 4 intents, rule-based NLU,
  planner, renderer with injection-safety proven, `lb` CLI. 33 tests pass.
- All project docs in place (ROADMAP, WBS, HANDOVER, MAZE, CLAUDE)

## In progress

- Phase 1: nothing started yet.

## Next (in order)

1. **P1.1** — fix the two known bugs (`Prompts/05_fix_slot_dropping.md`)
2. **P1.2** — run the 360 verification (`Prompts/06_verify_360.md`), raw verdicts
3. Then **Phase 2** — build the 8 remaining domains (see WBS)

## Open bugs

- **Silent slot dropping:** `lb show me the biggest files here` → `find . -type f`
  (matches everything). Fix in P1.1: abstain when an intent's defining slot
  is missing.
- **Plural extensions dropped:** `lb csvs bigger than 2 gigs` omits
  `-name '*.csv'`. Fix in P1.1: normalize plural file-type words.

## Decisions the human still needs to make

- None open. (Release audience: owner + batchmates. Model: intent-only, Phase 3.
  All settled — see ROADMAP design rules.)

## Notes / watch-outs

- Only file_discovery is built. The other 8 domains do NOT exist yet.
- `lb` lives in a uv venv; destructive-intent gate not built until P2.0.
- Owner is on bash; only the zsh widget exists.
