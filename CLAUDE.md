# LinuxBuddy — working agreement

You are building LinuxBuddy: a **local, offline tool that turns plain English
into Linux commands** and puts the command in the user's shell buffer to
review and run. No LLM at runtime. Classical NLP interprets language; a
hand-written KB defines Linux semantics; a deterministic planner builds the
command.

**User:** a skilled professional (data scientist / ML engineer) on Ubuntu
under WSL2, expert in their field, new to Linux, no time to learn it as a
subject. When scoping, ask: "would this person hit it in their first month
on WSL?"

## Read first — in this order

1. `STATUS.md` — **current state: what's done, in progress, next, open bugs.**
   This is the source of truth for where the project is NOW. Trust it over
   any other doc for current state.
2. The last few entries of `LOG.md` — what recently happened and why.
3. `kb/taxonomy.yaml` — the 9 domains, intents, slots.
4. `WBS.md` — the task with its ID, dependencies, "done when".
5. The task file you were given (in `Prompts/`).

`ROADMAP.md` has the phases and design rules (stable). `HANDOVER.md` is the
**frozen founding context** from 2026-11-03 — read it once for background, but
it is NOT current state; it does not reflect work done since. For current
state, always use `STATUS.md`.

Do the task named in the current session, nothing beyond it.

## Invariants — never violate

1. **No LLM, network, or generative model at runtime.** Pure Python stdlib +
   pytest. The ONE exception is a one-time, offline, author-run paraphrase
   pass to build model training data (Phase 3) — never at runtime. If a task
   seems to need a model at runtime, stop and ask.
2. **Typed argv lists are the plan.** The shell string is RENDERED from the
   argv for display/buffer only — never the execution source.
3. **One slot value → exactly ONE argv element.** Never substitute a slot
   into a joined command string.
4. **Nothing auto-executes.** LinuxBuddy prints/injects a command; the user
   presses Enter. Confirmation is always present.
5. **Absolute paths in argv.** Resolve `$HOME`/`~` at compile time. Never emit
   `~` or `$HOME` and rely on the shell.
6. **Abstain over guess.** If an intent is missing its defining slot, refuse
   with a hint. A match-everything command (bare `find . -type f`) is worse
   than a refusal. This is the root cause of both known bugs — honour it.

## Settled design rules (do not re-litigate)

- **One rendering path — real commands only.** The planner always renders the
  genuine command (`rm`, `chmod`, `find -delete`). No "safe-rewrite" mode.
- **Safety by containment.** V1 is tested inside the maze only. The maze is
  disposable, so a real `rm` inside it is harmless.
- **Destructive intents are gated on location.** In prototype mode
  (`LINUXBUDDY_MODE=prototype`, the default), any write/delete/chmod intent
  refuses unless cwd is under the maze root. Read-only intents work anywhere.
  Prod mode lifts the gate. The gate reads `risk_ops` from the KB.
- **The model is intent-only** (Phase 3). Slot extraction stays rule-based —
  slots are structured and rules handle them reliably.

## Current state & open bugs

Not listed here — this file would go stale. **See `STATUS.md`** for what's
done, what's in progress, and the current open bugs.

## Process

- **Write the failing test FIRST**, then the implementation. A test must
  assert *behaviour*, not merely that code runs.
- **One task per session.** If a "Done when" is ambiguous, stop and ask.
- **Raw results before fixes.** When verifying (e.g. the 360 scenarios),
  report verdicts first; never silently edit data to make it pass.
- Code under `src/linuxbuddy/`, tests under `tests/`. `pip install -e .` and
  `pytest` both work.
- Commit after each task with a message naming the task ID. Do not push
  unless told.

## Logging & status — every task (REQUIRED)

Two files keep the project self-documenting. Update BOTH as part of every task,
and commit them with the task's commit:

**`LOG.md` — append-only history.** Add a dated entry; never overwrite. Record:
date/time and task ID; what you did; decisions and why (especially anything
interpreted); problems and how resolved or left; test results; anything the
human should review or that surprised you. Prose a person reads later, not a
command transcript.

**`STATUS.md` — overwrite with the current snapshot.** Rewrite it to reflect
reality AFTER the task: what's done, what's in progress, what's next, current
open bugs/issues, and any decision the human still needs to make. Keep it
short — it's the "where are we right now" that the next session reads first.
This is the file that stops future sessions acting on stale state.

## The test fixture

`testlinuxbuddy/` is a generated maze (gitignored; scripts in `tools/fixture/`
are committed). Rebuild with `./testlinuxbuddy/build_maze.sh`, source
`testlinuxbuddy/bindings.env` for paths and `testlinuxbuddy/runtime_setup.sh`
for PID/PORT/GPU_ID. See `MAZE.md` for what's in it and why. **Never let a
test or command write or delete anything outside `testlinuxbuddy/`.**

## Gotchas

- The owner is on **bash**; the current widget is **zsh** (`zle`/`bindkey`).
  The `lb` command works in any shell — enough to test the tool.
- `lb` lives in a **uv venv** (PEP-668 blocked a direct pip install). Keep it
  active or `pip install -e .` into the shell's env.
- The KB uses a **hand-rolled stdlib-only YAML subset parser** (avoids a
  PyYAML dependency). It parses a restricted subset — keep specs within it, or
  raise the PyYAML question before it chokes as domains grow.
