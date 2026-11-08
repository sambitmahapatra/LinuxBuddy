# Task 27 — intent & synonym fill (turn the wrong-abstains into commands)

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Driven by the wrong-abstain rows
of `data/eval/sweep_results.csv`. These are missing intents and missing synonym
cues — mostly deterministic, common, and overdue. Group by domain. The bar
(from `CLAUDE.md`): emit a reasonable, user-editable command; keep abstaining
only on genuinely vague requests.

## workspace_and_shell

- **env_var** (new): "what's my PATH", "show the PORT variable", "print the HOME
  variable", "echo X" → `echo $X` (uppercase the named var; recognize common
  ones: PATH HOME PORT USER SHELL PWD). Rows E076, E077, E078.
- **date_time**: "what time is it", "what's today's date", "current date/time"
  → `date`. Row E087. (If Task 25 already added `date`, just confirm these hit it.)
- **disk_space**: canonical "how much space is left", "am i running out of
  disk", "disk free/usage" → `df -h`. "space" must work as well as "room" does.
  Rows E079, E081.
- **which**: "which pip", "which X am i using" → `command -v X`. Row E085.

## python_environments

- **pip_list** (new): "what packages are installed", "list my pip packages",
  "show installed packages" → `pip list`. Rows E134, E135.
- **package-vs-CLI disambiguation** — extend the Task-23 known-package set so the
  synonym verbs route correctly:
  - "do i have pandas", "check if torch is there" → importlib check (known
    Python packages). Rows E129, E130. **E129 must NOT be `command -v pandas`.**
  - "check if docker is there", "do i have node" → `command -v` (CLI tools).
    Row E132.
  Route "do i have X" / "check if X is there" through the SAME package-vs-CLI
  decision `is numpy installed` already uses (E128 is correct — match its path).

## archives_backup

- **extract** (new intent): "extract the tarball", "unzip the archive", "unpack
  X", "open the backup" → definite-ref resolves the target
  (`*.tar.gz` → `tar xzf`, `*.zip` → `unzip`). **Writes files → exit 3.**
  Rows E123, E124.
- **create_archive** synonyms: "make a backup of X", "compress X", "bundle X"
  (already partly works) → `tar czf …`. Add "make a backup of the project" /
  "compress the results". Rows E120, E122.

## wsl_interop

- **win_path** (new): "what's the windows path for this", "convert this path to
  a windows path" → `wslpath -w .` (or `wslpath -w <path>`). Rows E113, E114.
- **open_vscode**: "open this in vs code", "edit this in vscode" → `code .`.
  (Read-tier; the sweep/exec layer skips GUI launches — that's fine.) Row E116.
- **win_folders**: "take me to my windows downloads/documents" →
  `cd -- /mnt/c/Users/$USER/Downloads` (and Documents). Rows E117, E118.

## filesystem_permissions

- **chmod_private** synonym: "lock down the X file" → `chmod 600 -- X`
  (**exit 3**). Row E094.
- **find_perms** (new): "world-writable files" → `find . -perm -002`;
  "readable by everyone" → `find . -perm -004`. Rows E097, E098.

## processes

- **list_proc** synonym: "show my processes" → `ps -u "$USER"` (or `ps aux`).
  Row E100.

## text_and_logs

- **grep_recursive**: "search for X in the code", "search all files for X",
  "find X everywhere" → `grep -rn -- X .`. Rows E065, E070. (E071's doubled-path
  bug is fixed in Task 25 — just confirm it stays fixed.)

## file_discovery

- **find_empty** (new): "find empty files" → `find . -empty -type f`;
  "empty folders" → `find . -empty -type d`. Rows E043, E044.
- **find_recent** edge: "what did i touch in the last hour" → `find . -mmin -60`.
  Row E039.
- **count_files**: "count the X files" → `find … | wc -l`. Row E046. And add
  `| wc -l` to "how many X files are there" (E045 currently emits `find` with no
  count).

## Tests & done

Add a test per named row asserting it now emits the intended command (or the
right exit tier for the exit-3 ones: extract, lock-down). Full regression — new
cues must not steal existing routes (e.g. "space"/"disk" must not grab
unrelated rows; "open" collisions already handled in Task 26). `pytest` green.
Commit, don't push. Document in LOG.md the intents added and the synonym cues.
