# Task 32 — file-management intents (move/copy/delete/mkdir) + nested navigation

Read `CLAUDE.md`, `STATUS.md`, `ROADMAP_V2.md`, recent `LOG.md`. Branch:
`v2-multiturn`. **Run AFTER Task 31 is confirmed** (multi-turn must work first).
All deterministic rules — no model. These fill real gaps found by dogfooding.

## Part A — file-management intents (NEW, all destructive-tier)

A new domain (e.g. `file_management`). Every one of these is a write/delete op →
**exit 3, maze-gated, renders through the v1 planner/renderer/gate** (shlex
round-trip, `--` guard). The widget already shows the destructive warning on
exit 3.

| intent | phrasings | renders |
|---|---|---|
| **move / rename** | "move X to Y", "move the image to photos", "rename X to Y", "put X in Y" | `mv -- X Y` |
| **copy** | "copy X to Y", "make a copy of X" (exists — generalize to a dest) | `cp -- X Y` (or `cp -- X X.bak` when no dest) |
| **delete** | "delete X", "remove X", "remove the old logs", "get rid of X" | `rm -- X` |
| **make dir** | "make a folder X", "create a directory X", "new folder X" | `mkdir -- X` |

Details:
- **Two-slot extraction** for move/copy: parse source and destination from
  "X to Y" / "X into Y" / "X in Y". Destination that's a directory → `mv -- X Y/`
  is fine; keep it simple and let the shell resolve.
- **Definite-reference** resolution (reuse the Task-22 table): "the image" →
  `*.jpg`/`*.png` (an image glob), "the old logs" → `*.log`, "the csv" → `*.csv`.
  A glob as source is fine (shell expands); document it.
- **delete gets the strongest treatment:** it's irreversible. Still exit 3 +
  maze-gate + the widget warning (the review-before-Enter checkpoint is the
  safety net). Do NOT auto-add `-f`. Consider `rm -i --` is overkill for a
  review-first tool — plain `rm -- X` with the warning is consistent; note the
  choice in LOG.md.
- Risk classification: all four are write/delete → the gate must refuse them
  outside `LINUXBUDDY_MAZE_ROOT`, exactly like chmod/kill today.

## Part B — nested navigation ("X inside Y")

Extend the navigation domain (Task 26). Handle "go to X inside Y" / "take me to
X in Y" / "X under Y":

- If **Y is an ancestor** of `$PWD` (reuse the cd_ancestor resolution): resolve
  Y's absolute path, append X → `cd -- <Ypath>/X`.
  Example from `~/linuxbuddy/anything`: "go to test_02 inside linuxbuddy" →
  `cd -- /home/sambi/linuxbuddy/test_02`.
- If **Y is a child** of cwd and X a child of Y: `cd -- Y/X`.
- If Y is **not resolvable** from `$PWD` or children (a folder elsewhere on
  disk): abstain (that fuzzy case is v2 / a future find-based resolver). Don't
  guess.

## Tests & done

- Part A: a test per intent asserting the right command AND **exit 3**; a gate
  test that each is refused outside the maze and allowed inside; definite-ref
  cases ("move the image to photos", "delete the old logs").
- Part B: "go to test_02 inside linuxbuddy" from a dir under `~/linuxbuddy`
  resolves to the absolute path; a non-resolvable Y abstains; existing navigation
  (Task 26) unregressed.
- Regression: 139 single-turn sweep unchanged; the multi-turn chain still
  accumulates (Task 31 intact).
- Manual: in `~/linuxbuddy/testlinuxbuddy`, try a move/copy/delete inside the
  maze (works, warns) and the same from outside (refused). Try the nested-nav
  phrase.

`pytest` green. Commit on `v2-multiturn`. Document the new domain, the
definite-ref choices, and the delete-safety decision in LOG.md + STATUS.md.

## Optional — regenerate the sweep coverage

These new intents aren't in the 139. Consider adding ~10 rows to
`sweep_scenarios.csv` (move/copy/delete/mkdir + nested-nav, read and destructive)
so they're covered by future regression sweeps. Not required for this task.
