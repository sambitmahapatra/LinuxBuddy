# Changelog

All notable changes to LinuxBuddy are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

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
