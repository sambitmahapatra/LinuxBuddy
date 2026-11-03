# LinuxBuddy — Roadmap to V1

**Status:** Phase 1 in progress. Thin slice (file_discovery) works.
**Philosophy:** rapid prototype. Build a slice, use it, learn from what breaks.
No research-grade evaluation apparatus — the owner is the evaluator.

---

## Design rules settled (do not re-litigate)

1. **One rendering path — real commands only.** The planner always renders the
   genuine Linux command (`rm`, `chmod`, `find -delete`). No "safe rewrite"
   mode. Rewriting would break command-level validation (rendered vs the 360
   reference commands), split test from ship, and poison anything downstream
   that reads command strings.

2. **Safety by containment, not by rewriting.** V1 is tested **inside the test
   maze only**, never on real folders. The maze is disposable and regenerable,
   so a real `rm` inside it is harmless.

3. **Destructive intents are gated on location.** In prototype mode the planner
   refuses to generate any write/delete/chmod command unless the current
   directory is under the maze root. Read-only intents work anywhere.
   One `cwd` check, flipped off in prod via `LINUXBUDDY_MODE`.

4. **Confirmation always.** Prototype and prod both. Nothing auto-executes;
   the command lands in the buffer and the user presses Enter.

5. **Model is intent-only.** Slot extraction stays rule-based — slots are
   structured (sizes, paths, extensions) and rules handle them reliably. The
   model earns its place on phrasing variety in intent selection.

6. **Abstain over guess.** If an intent's defining slot is missing, refuse.
   A match-everything command is worse than a refusal.

---

## Phase 1 — Harden

Fix what real use exposed, and find out how sound the dataset is.

- Fix the two known bugs (silent slot dropping, plural extensions)
- Run the 360 reference commands against the maze; get raw verdicts
- Triage: fix or drop broken reference rows

**Exit:** both bugs fixed with tests; `verify_results.csv` exists for all 360;
per-domain verdict summary reviewed.

---

## Phase 2 — Breadth (all 9 domains)

The big phase. Build the remaining 8 domains the same way file_discovery was
built: a KB spec, a handful of NLU rules, tests, verification against the maze.

Order is low-risk first, so the destructive-gate work lands only when needed:

| # | Domain | Risk | Note |
|---|---|---|---|
| 1 | wsl_interop | read | the differentiator; no prior corpus exists |
| 2 | file_inspection | read | head/tail/stat/wc/file |
| 3 | text_and_logs | read | grep/sort/uniq/cut |
| 4 | processes | read + kill | read parts first; `kill` needs the gate |
| 5 | python_environments | mixed | venv, pip, pytest |
| 6 | archives_backup | writes | tar/gzip create files |
| 7 | workspace_and_shell | writes | mkdir/cd; first multi-step work |
| 8 | filesystem_permissions | destructive | chmod; needs the gate |

Cross-cutting, built once before the first destructive domain:
- `LINUXBUDDY_MODE` flag (prototype | prod)
- the cwd-under-maze gate for write/delete/chmod intents

**Exit:** all 9 domains answer their core scenarios; destructive intents
refuse outside the maze; tests green.

---

## Phase 3 — Model

Replace the rule-based intent router with a trained classifier. This is the
point where LinuxBuddy becomes the statistical-NLP tool it set out to be.

- Training data: the 360 scenarios (NL → intent), plus a one-time LLM
  paraphrase pass (~8×) for phrasing variety. The **only** build-time LLM use;
  runtime stays pure sklearn.
- Model: TF-IDF (word 1–2gram + char 3–5gram) → LinearSVC. Intent only.
- Wire as the router: model first, low confidence → abstain. Rules stay as
  the slot extractor.
- Compare to rules **by using it** — does it handle phrasings the rules missed?

**Exit:** model pickled with a retrain script; `lb` still works; it handles
phrasings the rules abstained on.

---

## Phase 4 — Test & package

- Full maze verification across all domains
- Quick model accuracy read (20% random holdout — no calibration ceremony)
- `pip install` works cleanly; pin Python + scikit-learn (pickles are
  version-sensitive)
- Bash widget (`bind -x`) — the owner is on bash; only zsh exists today
- README with install + usage

**Exit:** a fresh clone installs and runs; both shells work.

---

## Phase 5 — Release V1

Offline CLI, tested inside the maze. Owner first, then a few batchmates.

- Tag the release
- Use it daily for a week; log what breaks
- Hand to 2–3 batchmates on WSL; collect what confuses them

**Exit:** V1 tagged and in real daily use.

---

## Phase B — Advancement (post-release)

Driven by what V1 use actually exposes, not by this list:

- **Full safety layer** — risk scoring over the rendered plan, hard blocks,
  bounded preview ("this will delete 2,847 files"), confirmation tiers
- **Prod mode** — lift the maze gate; real folders, real commands
- **Multi-step** — most of the 360 scenarios are 2–6 steps; "set up a project"
  is one thought and four commands
- **Slot model** — CRF, only if rule-based slots demonstrably strain
- **Tier-2 retrieval** — BM25 over local man/tldr for out-of-scope requests,
  returning docs rather than a synthesized command
- **More domains** — git workflows, containers, databases, ssh
- **find-then-act** (`find | xargs rm`) — needs the safety layer first

---

## Honest scale note

Phase 2 is roughly 8× the file_discovery work. This is a side project at
evenings-and-weekends pace. Phase 1 is days; Phase 2 is weeks; Phases 3–5 are
days each once Phase 2 lands. The WBS gives per-task sittings so the shape is
visible rather than guessed.
