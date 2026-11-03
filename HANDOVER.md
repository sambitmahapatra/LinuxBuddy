# LinuxBuddy — Handover (Founding Context)

> ⚠ **This is a frozen snapshot from 2026-11-03 — the project's founding
> context and the reasoning behind its design.** It does NOT track work done
> since. For current state (what's done, open bugs, what's next) read
> **`STATUS.md`**; for recent history read **`LOG.md`**. Use this doc to
> understand *why* the project is shaped the way it is, not *where it is now*.

**Repo:** https://github.com/sambitmahapatra/LinuxBuddy
**Owner:** Sambit Mahapatra
**At time of writing:** working thin slice (file_discovery). Prototype, not
research.

---

## 1. What LinuxBuddy is

A **local, offline tool that translates plain English into Linux commands**
and places the command in the user's shell buffer to review and run. No LLM
at runtime, no network, no API key. Classical/statistical NLP interprets the
language; a hand-written knowledge base defines Linux semantics; a
deterministic planner builds the command.

**It inverts the documentation index.** Every Linux manual (`man`, `tldr`)
is organized by command name — it answers "how do I use `find`?". The user
doesn't have that question; they have "where are my big files?" and no way
to get from their question to the word `find`. LinuxBuddy provides that
missing lookup direction.

### The user (this governs every decision)

A **skilled professional in another field handed Linux as a tool, not a
subject** — data scientists, ML engineers, analysts, researchers on **Ubuntu
under WSL2 on Windows**. Expert at their own work, new to Linux, no time to
learn it properly. Today they solve this by alt-tabbing to Google or an AI
chatbot ~20x/day. That tab-switch is what LinuxBuddy replaces.

NOT a sysadmin, NOT a DevOps engineer, NOT a Linux hobbyist. When in doubt
about scope, ask: "would a data scientist hit this in their first month on
WSL?"

### What it is NOT
- Not a chatbot or an LLM wrapper.
- Not a tool that auto-executes. Nothing runs until the user presses Enter.
- Not a general Linux assistant — a deliberately finite, curated scope.
- Not a research project. It's a rapid prototype, tested by using it.

---

## 2. Current status — what works

The **file_discovery** domain works end to end on real WSL:

```
$ lb csv files over 100 megs
find . -type f -name '*.csv' -size +104857600c

$ lb python files changed in the last 3 days
find . -type f -name '*.py' -mtime -3

$ lb clean up my mess
LinuxBuddy: not sure what you mean          # correct abstention
```

- 4 intents: find_by_size, find_by_time, find_by_name, find_by_type
- Rule-based NLU (no model yet — rules stand in)
- KB spec → planner → renderer with injection-safety proven
- `lb` CLI command, works in bash and zsh
- 33 tests passing
- Branch: `v1-file-discovery` (may be unmerged/unpushed — check)

This is ~1 of 9 domains. The architecture (the "spine") is proven; the
remaining work is breadth, safety, and eventually models.

---

## 3. Architecture

```
natural language
   │
   ▼
NLU (rule-based for now)      src/linuxbuddy/nlu.py
   │  produces a Frame: {intent, slots}
   ▼
Planner                       src/linuxbuddy/planner.py
   │  Frame + KB → typed argv list; resolves $HOME; rejects unresolved slots
   ▼
Renderer  ◄── SECURITY BOUNDARY   src/linuxbuddy/render.py
   │  shlex.quote per element; asserts shlex.split(out) == argv
   ▼
CLI / shell buffer            src/linuxbuddy/cli.py, shell/linuxbuddy.zsh
   the command appears in the buffer; the USER presses Enter
```

### Invariants (never violate — also in CLAUDE.md)
1. No LLM / network / generative model at runtime. Pure Python stdlib + pytest.
2. Command plans are **typed argv lists**. The shell string is rendered from
   argv for display only, never the execution source.
3. A slot value substitutes into exactly ONE argv element.
4. Nothing auto-executes.
5. Target platform is Ubuntu on WSL2 — assume **systemd is NOT running**.
6. Paths in the final argv are absolute; resolve `$HOME`/`~` at compile time.

### The security boundary (the most important part)
The renderer is where safe argv becomes text the real shell parses. A
hostile filename like `my file; rm -rf ~.txt` must stay ONE argv element and
the `;` must never become a separate token. Proven by
`tests/test_render.py` (injection stays one element + round-trips). The
renderer self-checks `shlex.split(rendered) == argv` and raises rather than
ever emitting a string that fails it.

---

## 4. Repo layout

```
linuxbuddy/
├── CLAUDE.md                 # invariants + process for Claude Code
├── HANDOVER.md               # this file
├── pyproject.toml            # lb = linuxbuddy.cli:main entry point
├── kb/
│   ├── taxonomy.yaml         # 9 domains, intents, slots (taxonomy-v2)
│   └── commands/find.yaml    # only find so far
├── src/linuxbuddy/
│   ├── kb.py                 # KB loader (stdlib-only YAML subset parser)
│   ├── nlu.py                # rule-based intent + slot extraction
│   ├── planner.py            # frame → argv
│   ├── render.py             # argv → safe shell string (SECURITY BOUNDARY)
│   └── cli.py                # the `lb` command
├── shell/linuxbuddy.zsh      # zsh ZLE widget (Ctrl-G) — UNTESTED (see gotchas)
├── tests/                    # 33 tests
├── data/scenarios/
│   └── LinuxBuddy_360_WSL2_Terminal_Scenarios.csv   # ground-truth dataset
├── tools/fixture/            # copies of the maze scripts
├── testlinuxbuddy/           # GENERATED test maze (gitignored)
│   ├── build_maze.sh         # deterministic wipe-and-rebuild
│   ├── bindings.env          # 134 placeholder → path bindings
│   └── runtime_setup.sh      # exports PID/PORT/GPU_ID for runtime tests
└── Prompts/                  # task files for Claude Code (01–06)
```

---

## 5. How to run it

```bash
cd ~/linuxbuddy
source .venv/bin/activate          # the uv venv where lb is installed
lb csv files over 100 megs         # prints a find command

# against the test maze:
./testlinuxbuddy/build_maze.sh
source testlinuxbuddy/bindings.env
cd testlinuxbuddy/project
$(lb csv files over 100 megs)      # runs it → ./data/raw/huge_dataset.csv
```

The zsh widget (Ctrl-G buffer injection) needs zsh — see gotchas.

---

## 6. Known bugs

### Bug 1 — silent slot dropping → match-everything  (HIGH)
`lb show me the biggest files here` → `find . -type f`
"biggest" is dropped; the command matches every file. Looks like it worked,
floods the user. Root cause: the abstention gate is too weak — when an
intent's defining slot is missing, it falls through to bare `find` instead
of refusing. **Fix spec: Prompts/05_fix_slot_dropping.md.**

### Bug 2 — plural extensions dropped  (MEDIUM)
`lb find csvs bigger than 2 gigs` → `find . -type f -size +2147483648c`
"csvs" (plural) not recognized as the csv extension; `-name` missing. Size
parsed fine. Fix: normalize plural file-type words before slot extraction.
Also in Prompts/05.

### Rule: the fix for both is the same principle
**If the chosen intent is missing its defining slot, ABSTAIN — never emit a
degenerate command.** A match-all command is worse than a refusal.

---

## 7. Data & test assets

### The 360 scenarios (`data/scenarios/`)
360 validated NL→command scenarios across 9 domains, weighted to the WSL
data-scientist user (50% beginner, 78% read-only, 55% single-step). This is
the ground-truth inventory and eventual training-label source. Every
reference command passes `bash -n`; no banned tools (systemd etc.); no
duplicates; no template phrasing.

**Caveat:** the natural-language column is cleaner/more formal than real
speech in places. Good for frame definitions and intent labels; real
phrasing variety still needs augmentation or real user input.

**Not yet done:** running all 360 against the maze to get PASS/FAIL verdicts.
Spec: Prompts/06_verify_360.md. Do this before training on these labels so
the model isn't trained on broken rows.

### The test maze (`testlinuxbuddy/`, gitignored)
A deterministic filesystem fixture: a realistic DS project (src, tests,
notebooks, data of varied sizes incl. a 120MB sparse CSV, logs with
tracebacks, .git with branches, venv skeleton), plus an `awkward/` dir
(spaces, quotes, unicode, newlines, broken symlinks, 2000-file dir) and
WSL-specific material (CRLF script, /mnt/c bindings). Rebuild with
`build_maze.sh`; byte-identical across rebuilds (sha256 5af914bd…). Fixture
scripts are sourced in `tools/fixture/` and committed; the generated tree is
gitignored.

---

## 8. Roadmap — what remains for full V1

### Immediate
1. Fix the two known bugs (Prompts/05).
2. Run the 360 verification (Prompts/06) — the single most informative next
   step; turns "I think it works" into real per-domain numbers.

### Breadth — the other 8 domains (KB spec + NLU rules each)
Recommended order, read-only first (no safety layer needed yet):
1. **wsl_interop** — the differentiator, no prior corpus exists, mostly read-only
2. **file_inspection** — head/tail/stat/wc, high frequency
3. **text_and_logs** — grep/sort, high frequency
4. filesystem_permissions, processes — introduce some risk
5. workspace_and_shell — multi-step (mkdir+cd+git init)
6. archives_backup, python_environments

### The safety layer — NOT BUILT YET
The thin slice is all read-only, so it never needed this. Required before
any write/delete/kill domain ships:
- Risk scoring over the rendered plan (not by command name)
- Hard blocks (root/home/protected deletion, etc.)
- Confirmation UX for risky commands (second keypress for high risk)
- Bounded read-only preview selector ("this will delete 2,847 files")

### Multi-step
The planner compiles one command. Most of the 360 scenarios are 2–6 steps
("set up a project folder" = mkdir + cd + git init). Core for this user.
Preview-then-act (dry-run, then the real command as a separate approval) is
the pattern to use for anything destructive.

### Delivery plumbing
- Bash widget (`bind -x`) — currently only zsh is written
- Tier-2 fallback: BM25 over local man/tldr for out-of-scope requests,
  returning docs (not a synthesized command)
- Optional: a resident daemon so `lb` doesn't cold-start each call

### Modelling (the eventual point — comes AFTER breadth)
See §9. Rules are scaffolding; the model generalizes across the territory
once there IS territory (3-4+ domains).

### Explicitly deferred
- find-then-act (`find | xargs rm`) → needs preview + safety suite first
- git workflows beyond navigate/init → large domain of its own
- awk/sed text transforms → they're mini-languages; tier-2 covers them
- containers / k8s / ssh / databases → beyond the WSL-migrant first-month surface

---

## 9. The modelling plan (lean / prototype version)

**Do NOT model until there's breadth (3-4 domains) and a reason.** A model
produces an intent, but an intent is useless without a KB+planner behind it
to compile — so modelling one domain to replace working rules is pure
overhead.

When ready, the lean path (NOT research-grade):
1. Train data = the 360 scenarios (+ optional one-time LLM paraphrase to
   ~8x, the ONLY build-time LLM use; runtime stays pure sklearn).
2. Model = TF-IDF (word 1-2gram + char 3-5gram) → LinearSVC. The model
   picks the **intent only**; slot extraction stays rule-based.
3. 20% random holdout for a quick accuracy read. No calibration ceremony,
   no human test set, no Wilson intervals — it's a prototype.
4. Wire as the router: model first; low confidence → abstain. Pickle to
   models/intent.pkl with a retrain script.
5. Test live by using it. The question is only "does it handle phrasings the
   rules missed?"

Pin Python + scikit-learn versions once a model exists — pickles are
version-sensitive.

---

## 10. Key decisions & rationale (so these aren't re-litigated)

- **Buffer injection, not a sub-REPL / execution engine.** A subprocess
  can't do `cd`/`export`/`source` and strands the user outside their shell.
  The widget replaces the shell's own buffer; the user's shell runs it.
- **Rules before models.** Rapid prototype; rules prove the architecture and
  map the scope cheaply. Models are the expensive thing, built last, once
  rules demonstrably hit a wall.
- **Build-time LLM only.** An LLM may generate/paraphrase training data once,
  on the author's machine. The shipped tool has no model dependency.
- **argv stages, not format-string templates.** Prevents slot text from
  becoming shell syntax (injection). This drove the whole KB schema.
- **Risk computed over the rendered plan, not command name.** `find -delete`
  is dangerous; `rm ./one.log` is trivial. (Layer not built yet, but the
  principle is fixed.)
- **Scope = WSL data-scientist, evidence-based.** The taxonomy was rebuilt
  twice: first from NL2Bash (wrong — that corpus is expert-skewed scraping),
  then from the 360 WSL scenarios (right — matches the actual user).
- **Abstention is a feature.** Refusing to guess beats emitting a plausible
  wrong (or dangerous) command. The known bugs are both failures of this
  principle.

---

## 11. Gotchas

- **You're on bash; the widget is zsh.** `zle`/`bindkey` are zsh builtins.
  To use Ctrl-G: `sudo apt install zsh && exec zsh`, then source the widget.
  Or build the bash `bind -x` version. The `lb` command itself works in any
  shell — that's enough to use and test the tool.
- **`lb` lives in a uv venv.** Your environment had no python3-venv and
  PEP-668 blocked a direct pip install, so Claude Code made a uv venv. For
  the widget to find `lb`, either keep that venv active or `pip install -e .`
  into whatever env your interactive shell uses. Settle this once.
- **The KB uses a hand-rolled stdlib-only YAML parser** (to avoid a PyYAML
  dependency). It parses a restricted subset. When the KB grows across 9
  domains with richer specs it may choke — either keep specs within the
  subset deliberately, or accept PyYAML as the one dependency. Decide
  before domain 3-4.
- **`find` vs `bfs`.** In some sandboxes `find` is actually `bfs`
  (find-compatible); error prefixes differ. On real Ubuntu/WSL it's `find`.
- **`-mtime` tests use real clock time.** The maze gives a few tracked files
  now-relative mtimes so recency searches stay meaningful; the MANIFEST
  prints those as `RELATIVE` to keep rebuilds byte-identical.

---

## 12. Immediate next actions

1. Run `Prompts/05_fix_slot_dropping.md` in Claude Code (fix both bugs).
2. Run `Prompts/06_verify_360.md` (raw verdicts, no fixes).
3. Review the per-domain verdict summary; drop/fix broken reference rows.
4. Then: widen to wsl_interop, OR start the lean intent model — owner's call.
5. Push `v1-file-discovery`, open a PR, or merge to main when satisfied.
