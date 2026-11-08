# Task 26 — build the navigation domain properly

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Driven by the navigation rows
(E001–E023) of `data/eval/sweep_results.csv`. Navigation was never really
built — it was winning on accidents, leaking globs, and emitting `cd -` for
"go up". Build it as a first-class domain parser with clear intents and a clear
resolution order.

## The intents (resolution order matters — first match wins)

Resolve in THIS order, because directional words are unambiguous and must beat
name-matching:

1. **cd_parent** — cues: "up", "go up", "back", "take me back", "parent",
   "parent folder/directory", "up a level", "up one level", "go back up".
   → `cd ..`  ·  "up two levels" / "up N levels" → `cd ../..` (N segments).
   Rows: E006, E007, E008, E009, E011. **E009 "take me to the parent folder"
   must be `cd ..`, NOT `cd -- parent`.**
2. **cd_home** — cues: "home", "take me home", "go home", "home directory",
   "my home". → `cd ~`. Must match the single word "home" (E014).
   Rows: E012, E013, E014.
3. **cd_previous** — cues: "where i was", "previous directory", "last
   directory", "back to where i was". → `cd -`. Rows: E020.
   **Guard:** "go up" / "back up" / "project root" must NOT reach this — they are
   cd_parent / cd_ancestor. (Fixes E010, E016 which wrongly emit `cd -`.)
4. **cd_ancestor** — cues: "take me to X" / "go back to X" / "X root" / "the X
   folder" **where X matches a path component of `$PWD`**. lb already reads the
   cwd (the gate uses it). Walk `$PWD`; if X is an ancestor segment, emit `cd`
   to that absolute ancestor path (e.g. from `…/project/logs`, "take me to
   project" → `cd /…/project`; "go back to the project root" → same).
   Rows: E015, E016, E017. **E015/E017 must resolve the ancestor, not emit
   `cd -- project` / `cd -- testlinuxbuddy`.**
5. **cd_child** — cues: "go into X", "enter X", "move into X", "take me to X",
   "open the X folder/directory", "cd to X", where X is a bareword dir name that
   is NOT an ancestor. Strip trailing "folder"/"directory". → `cd -- X`.
   Rows: E001–E005. **"open the X folder" → cd** (E004).
6. **cd_absolute** — an absolute path (`/…`) is present → `cd -- <full path>`.
   **Capture the WHOLE path**, not the first component (E019:
   "/mnt/c/Users" → `cd -- /mnt/c/Users`, not `cd /mnt/c`).
7. **pwd** — "where am i", "what folder am i in", "current directory".
   → `pwd`. Already works (E021–E023); keep.

## Two bugs to kill explicitly

- **Glob leak (E001):** "take me to the logs folder" emits `cd -- *.log`. The
  Task-22 definite-reference glob resolver is firing on navigation targets. A
  navigation target is a **directory name** — it must NEVER be globbed to a file
  extension. Exclude navigation intents from definite-reference glob resolution.
- **Stray `cd -` (E010, E016):** "go back up one directory" and "go back to the
  project root" wrongly emit `cd -`. See the cd_previous guard above.

## Disambiguation (don't break neighbors)

- "open the **folder**" → cd (navigation). "open **config.yaml**" / "open the
  **file**" → file_inspection. Split on whether the target is a directory-ish
  word vs a filename. Verify file_inspection "open" handling (if any) still works.
- Directional cues ("up", "back") must not steal non-navigation requests — e.g.
  "back up the data" is archives (backup), not cd_parent. Test this collision.

## Tests & done

Add a test per row E001–E020 asserting the correct `cd` form (use `$PWD`-aware
cases for cd_parent/cd_ancestor — set a known cwd in the test). Regression run,
with explicit collision tests: "back up the project" → archive (not cd),
"open config.yaml" → inspection (not cd). `pytest` green. Commit, don't push.
Document in LOG.md the intent set, the resolution order, and the ancestor
resolution approach.
