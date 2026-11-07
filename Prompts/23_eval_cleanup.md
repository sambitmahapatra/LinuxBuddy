# Task 23 — eval cleanup: wrong-routes, defaults, known synonyms

Read `CLAUDE.md`. These are the smaller, specific fixes the eval exposed.
Each targets named rows. Group them; they're all small rule changes.

## A. Wrong commands (silent errors — fix FIRST, they mislead)

- **E004** "which files are huge" → emitted `command -v -- files` (!!). "huge/big
  + files" must route to `find_largest` (Task 19), never check_installed.
  Tighten check_installed so it only fires on real install-check phrasing (see C).
- **E024** "print config.yaml" → emitted a `find`. "print <file>" / "show <file>"
  must route to file_inspection (cat/preview), not file_discovery.
- **E090** "is numpy installed" → emitted `command -v -- numpy` (always fails;
  numpy is a Python package, not a CLI binary). Distinguish: a known Python
  package → the importlib check (`check_package`); a CLI tool → `command -v`.
  Keep a small known-package hint set (numpy, pandas, scipy, torch, sklearn,
  matplotlib, requests, flask, django...) → importlib; otherwise `command -v`.
- **E016** "recently modified logs" dropped the time part (just `find -name
  '*.log'`) — add the `-mtime` when "recently/lately" is present. (minor)
- **E018** "where is settings.json" → `find -name '*.json'` (all json, not the
  named file). A concrete `name.ext` in the request should be the exact `-name`,
  not globbed to its extension. (minor)

## B. Missing-argument defaults (abstain → sensible default)

- **E056** "what's on my port", **E058** "what's listening" — no port number →
  default to listing all listening sockets: `ss -ltnp`. Don't abstain.

## C. Known synonyms (the enumerable ones — patch these; the rest motivate v2)

Add these specific vocabulary cues. (The point of v1 is to patch the *common*
synonyms; the long tail is what the v2 attention model handles — do NOT try to
enumerate every phrasing.)

- kill verbs: **"stop", "terminate"** → kill intent (E060, E062). "stop the X
  process" / "terminate the X process" → kill_process, pattern=X.
- installed-check: **"check if X is installed"**, "is X there" → check_installed
  (E111). Keep it tool-name-bounded so "which files are huge" can't match.
- space synonym: **"room"** → same as "space" (E119 "how much room is left on
  ubuntu" → home_space).
- archive verbs: **"zip up"**, "bundle" → create_archive (E084).
- chmod intent-words: **"make this file private"** → chmod 600 (E077);
  **"needs to be executable"**, "should be executable" → chmod u+x (E075);
  **"only I should be able to read/edit"** → chmod 600 (E078).

## Tests

Add/adjust tests asserting each named row now behaves:
- E004 → find_largest (not command -v)
- E024 → a preview command (cat/head), not find
- E090 → the importlib check
- E056/E058 → `ss -ltnp`
- E060/E062 → kill_process
- E111 → check_installed
- E119 → home_space
- E075/E077/E078 → the right chmod
Plus a full regression run — make sure the synonym additions don't break
existing routing (e.g. "stop" must not grab non-process requests).

## Done when

`pytest` passes (incl. regression). Each named row produces the correct command
(or correct abstain). The 3 wrong-command rows no longer emit misleading
commands — that's the priority, since a wrong command is worse than an abstain.
Document in LOG.md.
