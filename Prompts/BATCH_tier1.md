# Tier 1 batch — build 4 read-only domains

Read `CLAUDE.md`, `STATUS.md`, and recent `LOG.md` first.

Execute these task files IN ORDER, each as its own unit:
1. `Prompts/08_file_inspection.md`
2. `Prompts/09_text_and_logs.md`
3. `Prompts/10_processes_read.md`
4. `Prompts/11_filesystem_read.md`

After each: run its tests, verify against that domain's maze scenarios, update
LOG.md and STATUS.md, commit (naming the task), do NOT push. Do not start the
next domain until the current one's "Done when" is met. If a domain's tests
fail and you can't fix them in a few attempts, STOP and report.

## Rules that apply to ALL four domains

- **Single-command intents only.** Many scenarios in these domains are
  *compound* (e.g. "preview the file, count its lines, and show its size" =
  three commands). For Tier 1, build the intents that map to ONE command. If a
  request is compound (asks for several distinct things), **abstain** — a
  "multi-step" capability is later work. Document which scenarios you deferred.
- **All read-only.** No destructive commands, no gate needed. If a domain has
  destructive scenarios (chmod, kill), SKIP them — they're a later tier.
- **Reuse the file_discovery pattern exactly:** KB spec in `kb/commands/`,
  capability in `kb/taxonomy.yaml`, NLU rules in `src/linuxbuddy/nlu.py`
  (extend, don't rewrite), tests from real examples, verify against the maze.
- **Pipes:** some intents need a 2-stage pipeline (e.g. `ps ... | head`,
  `sort | uniq -c | sort`). Before building those, check whether the planner
  supports multi-stage `argv` + a PIPE operator. If it does NOT yet, add
  minimal 2-stage pipe support to `planner.py` and `render.py` FIRST (render
  must still quote each stage's elements and keep the `|` compiler-inserted,
  never from slot text). Write a pipe round-trip test. If a single intent can
  avoid a pipe, prefer that.
- **Abstain over guess** stays the rule: missing defining slot → abstain.
- Extend the NLU router so it first picks the domain/intent, then the right
  slot extractor. Keep file_discovery working — run its tests after each
  domain to confirm no regression.

## Order rationale

file_inspection is simplest (clean single-command intents). text_and_logs has
grep's flag variety. processes and filesystem have the most pipe/compound
scenarios, so they come last once pipe support exists.
