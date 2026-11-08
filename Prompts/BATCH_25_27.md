# Batch — close the sweep gaps (Tasks 25 → 27 → re-sweep)

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md` first. This batch acts on the
139-row sweep (`data/eval/sweep_results.csv`). Every fix targets named rows.

Execute IN ORDER:

1. `Prompts/25_routing_priority.md` — stop `find` eating view/count/copy/
   history/process intents, fix 4 parsing bugs, refresh the MANIFEST sha.
   *(The silent wrong-command fixes — do these first.)*
2. `Prompts/26_navigation_build.md` — build the navigation domain properly
   (parent/home/ancestor/child/absolute), kill the glob leak and stray `cd -`.
3. `Prompts/27_intent_synonym_fill.md` — add the missing intents and synonyms
   (env vars, date, disk space, pip list, extract/unzip, wslpath, find-perms,
   package-vs-CLI, empty/count, recursive grep).
4. **Re-run the sweep** — re-execute `Prompts/24_full_sweep.md` on the same 139
   scenarios, write `data/eval/sweep_results_v2.csv`, print the new per-domain
   COMMAND/ABSTAIN tally and the read-row executability tally. Same guards
   (timeout, temp files, group kill, skip GUI, skip kill-family exec, throwaway
   maze for destructive, MANIFEST re-check).

After EACH task: run `pytest`, commit, update `LOG.md` + `STATUS.md`. **Do not
push.** Stop and report on any unfixable failure rather than guessing.

## The bar (from CLAUDE.md)

Turn abstains into reasonable, user-editable commands — not perfect ones. A
command the user can tweak beats an abstain. Keep abstaining only on genuinely
vague ("fix this", "tail the output") or deferred rows. Destructive intents
(chmod, kill, extract, archive-create, copy, pip install) must still signal
**exit 3**.

## Expected after re-sweep

Fully-right should climb from ~72/139 toward ~115–125/139. The remaining
residual will be genuinely-vague generic references and deferred installs —
that residual is the documented motivation for the v2 attention model. Record
the final numbers in LOG.md, and flag any NEW regressions the re-sweep exposes
(a fix that broke a neighbor) as the top follow-up.
