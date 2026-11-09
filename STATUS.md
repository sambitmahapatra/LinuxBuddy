# STATUS — LinuxBuddy

**Last updated:** 2026-11-09 (Task 30 — **v2 Phase 1 spike: multi-turn started**)

## Where we are
**v1.0.0 (rules engine) is COMPLETE** and on the `v1-file-discovery` line; v2
work is now underway on branch **`v2-multiturn`**.

**v2 Phase 1 spike (Task 30) — multi-turn mechanic, DONE (no model yet).** A
disk-backed `SessionFrame` + rules-based dialogue-act/delta detector carries a
running query across Ctrl-G calls and renders through the UNCHANGED v1 pipeline.
The target 3-turn chain works end-to-end in the maze (verified as separate
processes):
`find CSV files larger than 100MB` → refine `only the ones modified yesterday`
→ operate `show the biggest one`, accumulating into
`find . -name '*.csv' -size +100M -daystart -mtime 1 -printf '%s\t%p\n' | sort -rn | head -1`.
Multi-turn is opt-in (`LINUXBUDDY_SESSION`, exported by the widgets); single-turn
is byte-identical (sweep v5 == v4, 0 changes). `lb --frame` / `lb --reset` added.
**No transformer/torch** — the encoder is Phase 2.

v1 release artifacts (Task 29): version `1.0.0`, `README.md`, `CHANGELOG.md` on
the v1 line. **Still ready for the human to tag `v1.0.0` and push** — not tagged.

## Final evidence
- Sweep: **COMMAND 134 / ABSTAIN 5** of 139, integrity PASS, **0 regressions**.
  See `data/eval/sweep_results_v5.csv` (routing identical to v4; v1–v4 kept too).
- **302 tests** pass (281 v1 + 21 v2 session). Single-turn routing byte-identical
  across v2→v5; the only intended routing change in the whole series was Task 28's
  5 cleanup rows (v3 → v4).

## The honest-5 residual (abstain by design)
- **E056** "tail the output" / **E060** "what is this file" — generic target, no
  file named.
- **E073** "sort this list" — genuinely vague, no file.
- **E138/E139** "install the requests package" / "add pandas to my environment" —
  correct abstains: runtime network is invariant #1.
These generic/ambiguous/context-dependent cases are the motivation for v2.

## Next — v2
- **Phase 1 (multi-turn mechanic): DONE** this task (rules-only spike). Scope to
  grow next: more operate modifiers (smallest / sort / first-N), more refine
  constraints (name/path/type), coreference beyond elided "one/them/it".
- **Phase 2 (the model):** the transformer/attention intent encoder, Siamese /
  zero-shot matching for unseen phrasings, a continual-learning feedback loop.
  Intent-only — slot extraction stays rule-based; no runtime network dependency.
  The honest-5 residual above is still its motivation.

Also open (carried from v1): a **manual Ctrl-G redraw check in a real interactive
bash** — the multi-turn chain was verified via separate `lb` processes, but a
human should source the widget and press Ctrl-G to confirm the Readline redraw.
`ROADMAP_V2.md` (referenced by Prompts/30) does not exist yet — worth writing.

HANDOVER.md stays frozen as the founding context; this file is the living
snapshot.

## Open bugs
None known. Full suite green (302). Single-turn sweep: 0 regressions (v5==v4),
integrity PASS.
