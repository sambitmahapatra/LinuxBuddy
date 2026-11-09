# STATUS — LinuxBuddy

**Last updated:** 2026-11-09 (Task 29 — **v1.0.0 released**)

## Where we are
**v1.0.0 — the rules-based engine is COMPLETE.** A local, fully offline CLI that
turns plain-English into Linux commands placed in the shell buffer for review.
No LLM, no network, no API key at runtime. All 10 domains built, the asymmetric
abstain policy in force, definite-reference resolution landed, shell widgets
(bash + zsh) injecting commands with tiered risk confirm on Ctrl-G.

Release artifacts written (Task 29): version `1.0.0` in `pyproject.toml` and
`linuxbuddy.__version__`, `README.md` (front door), `CHANGELOG.md` (Keep a
Changelog). **Ready for the human to tag `v1.0.0` and push** — not tagged, not
pushed here.

## Final evidence
- Sweep: **COMMAND 134 / ABSTAIN 5** of 139, integrity PASS, **0 regressions**.
  See `data/eval/sweep_results_v4.csv` (v1/v2/v3 kept for history).
- **281 tests** pass. Reproducible: routing byte-identical v2 == v3; Task-28
  cleanup changed only its 5 intended rows (v3 → v4).

## The honest-5 residual (abstain by design)
- **E056** "tail the output" / **E060** "what is this file" — generic target, no
  file named.
- **E073** "sort this list" — genuinely vague, no file.
- **E138/E139** "install the requests package" / "add pandas to my environment" —
  correct abstains: runtime network is invariant #1.
These generic/ambiguous/context-dependent cases are the motivation for v2.

## Next — v2 (not started)
A learned context layer on top of the rules: an attention/transformer intent
model, Siamese / zero-shot matching for unseen phrasings, and a continual-
learning feedback loop. It is intent-only — slot extraction stays rule-based —
and adds no runtime network dependency to what v1 ships. The honest-5 residual
above is its scope.

Also open: a **manual widget check in a real interactive bash** (verified
non-interactively; a human should source the widget and press Ctrl-G to confirm
the Readline redraw).

HANDOVER.md stays frozen as the founding context; this file is the living
snapshot.

## Open bugs
None known. Full suite green (281). Sweep: 0 regressions, integrity PASS.
