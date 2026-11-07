# Batch — finish v1 (rules accuracy + widget)

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md` first.

Goal: take the eval score from 62% to ~85% with rules fixes, then make the tool
usable daily with the widget. Driven by the 130-request eval
(`data/eval/eval_results.csv`) — every fix targets specific failing rows.

Execute IN ORDER:
1. `Prompts/19_find_largest.md`        — superlatives ("biggest files")  [already written]
2. `Prompts/20_asymmetric_abstain.md`  — help on reads, confirm on destructive  [already written]
3. `Prompts/22_definite_reference.md`  — "the log" → *.log  (THE big lever: 28 failures)
4. `Prompts/23_eval_cleanup.md`        — wrong-routes, defaults, known synonyms
5. **Re-run the sweep** — re-execute `Prompts/21_eval_sweep.md` on the same 130
   requests, write `data/eval/eval_results_v2.csv`, print the new per-domain
   COMMAND/ABSTAIN tally. This measures the batch.
6. `Prompts/18_bash_widget.md`         — buffer injection, tiered confirm (usability)

After each: tests, commit, update LOG.md + STATUS.md, don't push. Stop and
report on unfixable failure.

## The bar for the rules fixes

Turn abstains into **reasonable, user-adjustable commands** — not perfect ones.
A `grep error *.log` the user can tweak beats an abstain every time. Keep
abstaining only on genuinely vague ("fix this") or deferred (nested $()) rows.

## Expected after the re-sweep

Wrong-abstains should drop from 45 toward ~15; the residual will be mostly the
~9 synonym cases we can't fully enumerate — that residual is the documented
motivation for the v2 attention model. Record the final number in LOG.md.
