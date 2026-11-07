# Task 20 — asymmetric abstain policy (help on reads, confirm on destructive)

Read `CLAUDE.md`. From dogfooding: the tool abstains too readily on SAFE
requests, which for a Linux-new user is itself a failure — it sends them back to
Google, the exact thing LinuxBuddy exists to replace. Meanwhile destructive
commands are where caution actually matters. Make the policy asymmetric by risk.

## The principle (update CLAUDE.md invariant #6)

Replace the blanket "abstain over guess" with:

- **Read-only intent, a reasonable interpretation exists → emit the command.**
  A wrong `find`/`grep`/`ls` is cheap — the user sees the output and retries.
  Lean toward helping.
- **Read-only, genuinely no reasonable interpretation → abstain** (don't guess
  wildly — a wild guess the user can't judge is worse than a hint).
- **Destructive intent (write/delete/chmod/kill), anything less than a
  confident parse → abstain or require confirmation.** A wrong `rm` is a
  disaster. Caution lives here, not on reads.

Update invariant #6 in CLAUDE.md to state this asymmetry, and fix the stale
"abstain over guess (universally)" framing in the nlu docstring.

## Concrete changes

Review the abstain points in the READ-ONLY parsers. For each, ask: is there a
reasonable default that helps more than it misleads?

- "biggest files" → now `find_largest` (Task 19). No longer abstains. ✓
- Superlatives generally (biggest/largest/most/smallest) on a read → map to a
  sort intent, don't abstain.
- A read request with a missing-but-defaultable slot → use the default and emit
  (e.g. count defaults, path defaults to `.`), rather than abstaining.
- Keep abstaining when the request is genuinely unparseable or names no
  operation ("fix this", "clean up", "do the thing").

Do NOT loosen destructive abstention. chmod/kill/rm/mkdir with an unclear
target or mode still abstain — that asymmetry is the safety.

## The "open X" miss (from dogfooding, if quick)

`lb open huge_dataset.csv` gave `find . -name '*.csv'` (wrong — it searched
instead of acting on the named file). "open" is ambiguous on WSL. Either map
"open <file>" to a sensible default (in WSL, `explorer.exe <file>` opens it in
Windows — a wsl_interop intent) or abstain cleanly rather than mis-routing to
find-by-name. Your call; document it. If it's more than a small change, defer
and just stop the mis-route (abstain instead of wrong command).

## Tests

Update the relevant domain tests to reflect the new policy:
- Read superlatives emit commands, not hints.
- A genuinely vague read ("do the thing") still abstains.
- Destructive-with-unclear-target still abstains (unchanged).

## Done when

`pytest` passes (incl. regression). CLAUDE.md invariant #6 states the
asymmetry. In the maze: common safe requests that used to abstain now emit a
reasonable command; destructive requests with unclear intent still abstain.
Document in LOG.md which abstain points you converted to commands and why.
