# Tightening batch — make the built tool actually usable

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md` first.

These three tasks come from real dogfooding, not new features. The product
stays a raw CLI — no GUI, no TUI. We are making the 9 built domains solid for
the target user (new to Linux), who found that: (a) a printed command they
can't run is useless, (b) abstaining on a safe request sends them back to
Google, (c) destructive commands need a visible gate.

Execute IN ORDER:
1. `Prompts/19_find_largest.md`   — fill the obvious gap ("biggest files"), quick
2. `Prompts/20_asymmetric_abstain.md` — help on reads, confirm on destructive
3. `Prompts/18_bash_widget.md`    — buffer injection with tiered confirm (the big UX fix)

19 and 20 are quick rule changes; do them first for fast wins. 18 (the widget)
is the shell-integration piece and the highest-impact — it turns "prints a
command" into "command in your prompt, press Enter."

After each: tests, commit, update LOG.md + STATUS.md, don't push. Stop and
report on unfixable failure.

## The principle behind all three

For this user, **abstaining is itself a failure mode** on safe commands — it
sends them back to the thing the tool exists to replace. The fix is asymmetry
by risk: help confidently on read-only, be cautious only on destructive. Raw
CLI throughout; the "confirmation" for destructive is a visible warning plus the
deliberate keypress, not a dialog.
