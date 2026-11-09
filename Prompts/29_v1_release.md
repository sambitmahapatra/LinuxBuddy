# Task 29 — declare v1 (release artifacts)

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Run this AFTER Task 28's
re-sweep is clean. This writes the release artifacts that make v1 a real,
documented release. No code changes — docs, version, changelog. Commit, don't
push (the human does the tag + push).

## 1. Version

Set the project version to **1.0.0** in `pyproject.toml`.

## 2. README.md (rewrite — this is the front door)

Concise and honest. Cover, in this order:
- **What it is:** a local, fully offline CLI that translates plain-English
  requests into Linux shell commands and places them in your shell buffer for
  review before you run them. **No LLM, no network, no API key at runtime** —
  classical rule-based NLU. (The only AI involvement was authoring the rules.)
- **Who it's for:** a skilled professional handed Linux as a tool, not a subject
  — e.g. a data scientist working in WSL, new to the terminal. It inverts the
  docs index: you say what you want, it finds the command.
- **How it works (one paragraph):** request → intent/slot parse → typed plan →
  rendered command (with `shlex` round-trip safety) → your shell buffer.
- **Install:** the editable install (`pip install -e .`) OR the venv symlink to
  `~/.local/bin/lb`; then source the widget (`shell/linuxbuddy.bash` /
  `.zsh`) from your shell rc. Note `~/.local/bin` must be on PATH.
- **Usage:** type a request, press **Ctrl-G** → the command replaces your line,
  editable, not run; press Enter to run. **Tiered confirm:** read-only commands
  land silently; destructive ones show a warning and signal risk by exit code
  (0 read / 1 abstain / 3 destructive); vague requests abstain with a hint.
- **Safety model:** the containment gate — destructive operations
  (write/delete/privilege) are refused unless cwd is under the test maze root
  (`LINUXBUDDY_MAZE_ROOT`); `LINUXBUDDY_MODE` prototype/prod. v1 is maze-tested.
- **Coverage:** the 10 domains (navigation, file discovery, file inspection,
  text & logs, workspace & shell, permissions, processes, WSL interop, archives
  & backup, Python environments).
- **Evidence:** the 139-scenario deterministic sweep — ~134/139 emitting the
  right command or honestly abstaining, 266 tests, fully reproducible against
  the fixed-timestamp maze. Link `data/eval/sweep_results_v4.csv`.
- **Known limits / what's next:** the honest residual (generic references with
  no resolvable target, ambiguous intent, context-dependent cases) is the
  motivation for v2 — a transformer/attention layer for context understanding.
  State plainly that v1 is rules-only by design.

Keep it readable — prose and short lists, not a wall. No marketing.

## 3. CHANGELOG.md (new)

Start a Keep-a-Changelog style file. One entry:

```
## [1.0.0] — 2026-11-09
### Added
- Rule-based NL→Linux translation across 10 domains.
- Shell-buffer injection widget (bash + zsh) with Ctrl-G and tiered confirm.
- Exit-code risk signaling (0 read / 1 abstain / 3 destructive).
- Containment safety gate (maze-scoped destructive ops).
- Deterministic 139-scenario evaluation harness + fixed test maze.
### Results
- 139-scenario sweep: ~134/139 correct-or-honest-abstain; 266 tests passing;
  reproducible (v2==v3 routing).
### Known limitations
- Generic/ambiguous/context-dependent requests abstain by design — the v2
  attention model is scoped to address these.
```

## 4. STATUS.md (mark the milestone)

Update STATUS.md to state: **v1.0.0 — rules-based engine COMPLETE.** Record the
final sweep number, the honest-5 residual abstains (E056, E060, E073, E138,
E139), and point forward to the v2 plan (attention / Siamese-zero-shot /
continual-learning feedback loop). Keep HANDOVER.md's frozen founding context as
is; STATUS is the living snapshot.

## 5. (optional) VERSION or __version__

If the package exposes `__version__`, set it to `1.0.0` to match pyproject.

## Done when

Version is 1.0.0, README/CHANGELOG/STATUS written, `pytest` still green (docs
shouldn't touch tests, but confirm). Commit as `release: v1.0.0`. Do NOT push
and do NOT tag — report that it's ready for the human to tag and push.
