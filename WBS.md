# LinuxBuddy — Work Breakdown Structure

**Task IDs:** `P<phase>.<package>.<task>`. Use them in branch names
(`p2.3-text-logs`) and commit messages.

**Estimates in sittings** — one sitting ≈ 2–3 focused hours. Total ≈ 58.
At 3 sittings/week that's ~4–5 months; at 6/week, ~2 months. Side-project pace.

**Definition of done, every task:** the artifact exists and is committed; a
test asserts it *behaves* as specified (not merely that it runs); the task's
"done when" is literally satisfied.

---

## Phase 1 — Harden  (3 sittings)

| ID | Task | Depends | Done when | Sit |
|---|---|---|---|---|
| P1.1.1 | Fix abstention gate: missing defining slot → abstain. Superlatives with no number abstain with a hint. | — | `lb show me the biggest files here` exits 1 with a hint; never emits bare `find . -type f` | 1 |
| P1.1.2 | Fix plural/possessive extension normalization (`csvs→csv`, `logs→log`, `pys→py`) | — | `lb csvs bigger than 2 gigs` includes `-name '*.csv'` | — |
| P1.2.1 | Run all 360 reference commands against the maze; classify PASS/EMPTY/FAIL/SKIP/UNSAFE | P1.1 | `data/scenarios/verify_results.csv` exists for 360 rows | 1 |
| P1.2.2 | Triage verdicts: fix or drop broken reference rows; record which and why | P1.2.1 | Every FAIL/EMPTY row is either fixed, dropped with a reason, or accepted as environment-specific | 1 |

*Spec files: `Prompts/05_fix_slot_dropping.md`, `Prompts/06_verify_360.md`*

---

## Phase 2 — Breadth  (34 sittings)

### P2.0 — Cross-cutting infrastructure (build before the first destructive domain)

| ID | Task | Depends | Done when | Sit |
|---|---|---|---|---|
| P2.0.1 | `LINUXBUDDY_MODE` flag (prototype \| prod), read from env, default prototype | P1 | Mode readable from one place; documented in README | 1 |
| P2.0.2 | Maze-containment gate: in prototype mode, write/delete/chmod intents refuse unless cwd is under the maze root | P2.0.1 | A destructive request outside the maze exits 1 with a clear message; inside the maze it renders the real command | 1 |
| P2.0.3 | Mark every intent in `taxonomy.yaml` with `risk_ops` so the gate knows what to gate | P2.0.2 | Gate reads risk from the KB, not a hardcoded list | 1 |

### P2.1–P2.8 — The eight domains

Each domain is the same shape as file_discovery: KB spec → NLU rules →
unit tests → verify against that domain's 40 maze scenarios.

| ID | Domain | Depends | Done when | Sit |
|---|---|---|---|---|
| P2.1 | **wsl_interop** — explorer.exe, wslpath, clip.exe, /mnt/c navigation, df on C: | P1 | Core WSL scenarios answer; `lb open this in explorer` works | 4 |
| P2.2 | **file_inspection** — head, tail, stat, file, wc | P1 | Preview/inspect scenarios answer | 4 |
| P2.3 | **text_and_logs** — grep (+ -i, -n, -r, --include), sort, uniq, cut | P2.2 | Search-in-files scenarios answer, incl. exclude-dir | 5 |
| P2.4 | **processes** — ps, pgrep, ss (read); kill/pkill (gated) | P2.0, P2.1 | Read parts work anywhere; kill gated to maze | 4 |
| P2.5 | **python_environments** — venv create, pip list, pytest, which python | P2.0 | Env scenarios answer; venv creation gated | 4 |
| P2.6 | **archives_backup** — tar create/extract/list, gzip, sha256sum | P2.0 | Archive scenarios answer; creation gated | 4 |
| P2.7 | **workspace_and_shell** — mkdir, cd, pwd, git init/status/branch; first multi-step support | P2.0 | `lb set up a project folder called X` emits the multi-command plan | 5 |
| P2.8 | **filesystem_permissions** — stat perms, chmod, test -w, du | P2.0 | chmod gated to maze; permission inspection works anywhere | 4 |

**Note on P2.7:** this is where multi-step lands. If it proves bigger than
5 sittings, split it — single-command workspace intents first, multi-step as
its own task.

---

## Phase 3 — Model  (7 sittings)

| ID | Task | Depends | Done when | Sit |
|---|---|---|---|---|
| P3.1.1 | Build the training set: 360 scenarios → (NL, intent) pairs mapped to `taxonomy.yaml` intent ids | P2 | `data/model/train.jsonl` with every row labelled | 1 |
| P3.1.2 | One-time LLM paraphrase pass, ~8× per row; vary register, add typos; drop any paraphrase that loses the intent | P3.1.1 | `data/model/augmented.jsonl` ≈ 3k rows; the ONLY build-time LLM use | 2 |
| P3.2.1 | Train TF-IDF (word 1–2g + char 3–5g) → LinearSVC intent classifier; 20% random holdout accuracy read | P3.1.2 | `models/intent.pkl` + `scripts/train_intent.py`; accuracy printed | 2 |
| P3.3.1 | Wire as the router in `cli.py`: model picks intent, rules extract slots, low confidence → abstain | P3.2.1 | `lb` works end to end on the model path; rules remain the fallback | 1 |
| P3.3.2 | Use it. Note phrasings the model handles that the rules abstained on, and any regressions | P3.3.1 | A short findings note in the repo | 1 |

---

## Phase 4 — Test & package  (8 sittings)

| ID | Task | Depends | Done when | Sit |
|---|---|---|---|---|
| P4.1.1 | Full maze verification across all 9 domains (LinuxBuddy's own output this time, not the reference CSV) | P3 | Per-domain pass rate recorded | 2 |
| P4.2.1 | Bash widget (`bind -x`) with parity to the zsh widget | P2 | Ctrl-G works in bash; `cd` still works after | 2 |
| P4.2.2 | Verify the zsh widget in a real zsh session (never yet run) | P4.2.1 | Buffer injection confirmed in zsh | 1 |
| P4.3.1 | Packaging: clean `pip install`, pin Python + scikit-learn versions | P3 | Fresh clone installs and `lb` runs | 1 |
| P4.4.1 | README: what it is, install, usage, the maze-only caveat, known limits | P4.3.1 | A newcomer can install and run it from the README alone | 2 |

---

## Phase 5 — Release V1  (4 sittings + a week of use)

| ID | Task | Depends | Done when | Sit |
|---|---|---|---|---|
| P5.1.1 | Tag `v1.0`, merge to main, push | P4 | Release tagged on GitHub | 1 |
| P5.2.1 | Daily use for one week inside the maze; log every miss and surprise | P5.1.1 | A findings list with at least 10 real entries | 1 |
| P5.3.1 | Hand to 2–3 batchmates on WSL; watch them use it without coaching | P5.2.1 | Notes on what confused them in the first five minutes | 2 |

**The watching matters more than the numbers.** Where a new user hesitates
is the real bug report.

---

## Phase B — Advancement (unscoped; driven by V1 findings)

Not estimated — the order comes from what Phase 5 exposes.

- Full safety layer: risk scoring over the rendered plan, hard blocks,
  bounded preview, confirmation tiers
- Prod mode: lift the maze gate for real folders
- Multi-step beyond P2.7's first cut
- Slot model (CRF) — only if rule-based slots demonstrably strain
- Tier-2 BM25 retrieval over local man/tldr
- New domains: git workflows, containers, databases, ssh
- find-then-act (`find | xargs rm`) — requires the safety layer first

---

## Critical path

```
P1 → P2.0 → P2.1…P2.8 → P3 → P4 → P5
```

P2.1–P2.3 (the read-only domains) can run before P2.0 if you want momentum —
they need no gate. Everything from P2.4 onward depends on P2.0 existing.

## Where this realistically slips

- **P2.3 (text_and_logs)** — grep has many flags and the NL for them is varied
  ("ignore case", "with line numbers", "skip the venv"). Budgeted 5, could be 7.
- **P2.7 (workspace_and_shell)** — multi-step is new machinery, not just
  another domain. Split it if it resists.
- **P3.1.2 (augmentation)** — paraphrase quality is the whole game for the
  model. Audit 50 by hand before generating 3,000.
