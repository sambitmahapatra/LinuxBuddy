# LinuxBuddy — Current Status

> The single source of truth for where the project is NOW. Overwrite this
> after every task. Keep it short. Next session reads this first.

**Last updated:** 2026-11-07 (v1-finish batch: Task 19 done)
**Current phase:** Phase 2 COMPLETE — next is install + dogfood
**Branch:** v1-file-discovery

---

## Done

- Scoping, taxonomy (`kb/taxonomy.yaml`, 9 domains), 360 validated scenarios.
- Test maze (`testlinuxbuddy/`) — deterministic, bindings + runtime setup.
- **file_discovery domain works end to end** — 4 intents, rule-based NLU,
  planner, injection-safe renderer, `lb` CLI. Both known bugs fixed (P1.1).
- **P1.2 (Task 06) — 360 reference commands verified vs the maze.** Raw
  verdicts only: 244 PASS · 59 FAIL · 43 SKIP · 13 EMPTY · 1 UNSAFE.
- **P1.2.2 (Task 07) — the 360 verdicts triaged.** `verify_results.csv` now
  has `verdict_final` + `verdict_final_reason` on every row.
  **True pass (PASS + PASS_WITH_STDERR) = 296/360 (82.2%).** Final tally:
  PASS 275 · PASS_WITH_STDERR 21 · PASS_IN_SEQUENCE 1 · ACCEPTED_EMPTY 13 ·
  ENV_UNSUPPORTED 3 · SKIP 43 · UNSAFE 1 · **FAIL 3**. 14 genuine dataset bugs
  fixed in the CSV and re-verified; 35 false failures reclassified; 13 EMPTY
  accepted with reasons. See `LOG.md` for the full breakdown.
- **Tier 1 batch (tasks 08–11) IN PROGRESS.** Introduced the Phase-2 **NLU
  router** (`parse()` dispatches over domain parsers; `_ABSTAIN` sentinel;
  file_discovery stays last).
  - **Task 08 — `file_inspection` DONE:** 6 intents (preview_head/tail,
    count_lines, show_size, detect_type, show_stat), `kb/commands/inspect.yaml`.
  - **Task 09 — `text_and_logs` DONE:** 5 intents (search_in_file,
    search_recursive, count_matches, sort_lines, unique_lines),
    `kb/commands/text.yaml`. grep flags carried as one combined `gflags` token.
  - **Task 10 — `processes` DONE:** 6 read-only intents (list_processes,
    top_by_cpu, top_by_mem, find_process, process_on_port, show_pid),
    `kb/commands/process.yaml`. Added **2-stage pipe support** to planner +
    render and quote-aware flow-list comma splitting in the KB loader.
    kill/pkill abstain.
  - **Task 11 — `filesystem_permissions` DONE:** 6 read-only intents
    (check_writable/readable/exists, show_permissions, show_owner, disk_usage),
    `kb/commands/fs.yaml`. Generalised composition to `&&` chains via a
    `Stages` plan container. chmod abstains; dir_empty deferred (`$(...)`).
    Verified vs the maze. **92 tests pass. Tier 1 batch COMPLETE.**
- **Tier 2 batch (tasks 12–14) IN PROGRESS.**
  - **Task 12 — P2.0 containment gate DONE.** `config.py` (LINUXBUDDY_MODE /
    LINUXBUDDY_MAZE_ROOT) + `gate.py` (`check(risk_ops, cwd)`), wired into the
    CLI after compile, before render. Destructive plans (risk_ops ∋
    write/delete/privilege) abstain unless cwd is under the maze root
    (prototype mode); reads work anywhere; prod lifts the gate. realpath +
    commonpath defeat `..`/symlink traversal. **99 tests pass.**
  - **Task 13 — `archives_backup` DONE (first write domain).** 7 intents:
    read `list_archive`(tar -tf)/`list_zip`(zipfile -l)/`archive_integrity`
    (gzip -t)/`archive_size`(du -h); write (gated) `create_archive`(tar -czf),
    `extract_archive`(mkdir && tar -xf), `compress_file`(gzip -k).
    `kb/commands/archive.yaml`, capability `manage_archives`. Verified vs the
    maze — create/extract/compress run inside, abstain outside. **108 pass.**
  - **Task 14 — `python_environments` DONE.** 5 intents: read `python_version`
    (python3 --version && command -v), `where_python` (command -v),
    `check_package` (importlib find_spec probe); write (gated) `run_script`
    (python3 -- path), `check_syntax` (py_compile). `kb/commands/python.yaml`,
    capability `python_env`. Router: python before text (so "...syntax errors"
    isn't grabbed as a grep). pip/venv/activate/server deferred (abstain).
    Verified vs the maze. **119 pass. Tier 2 batch COMPLETE.**
  - **Tier 3 batch (tasks 15–17) IN PROGRESS.**
  - **Task 15 — chmod + kill DONE.** filesystem gains make_executable/
    remove_executable/set_permission (chmod, gated); processes gains
    kill_process (pkill -f)/kill_pid (kill), gated. Old kill/chmod abstains
    replaced by real intents. Both domains now COMPLETE (only dir_empty
    deferred). Verified vs the maze. **129 pass.**
  - **Task 16 — `workspace_and_shell` DONE.** 10 reads (where_am_i, go_home,
    go_back, goto, list_all, who_am_i, which_shell, show_history, clear_screen,
    check_installed), make_dir (gated), and setup_project — the ONE scoped
    multi-step recipe (mkdir dirs && cd). `kb/commands/workspace.yaml`. Planner
    now resolves ~/$SHELL whole-element literals at compile. Fixed a latent
    substring bug ("account"→count). Verified vs the maze. **139 pass.**
  - **Task 17 — `wsl_interop` DONE.** 8 read-only intents: open_explorer,
    goto_cdrive, goto_home, path_to_linux (wslpath -u), path_to_windows
    (wslpath -w), copy_to_clipboard (pwd | clip.exe), cdrive_space,
    home_space. `kb/commands/wsl.yaml`. Nested $(...) navigation deferred
    (abstain). Script-verified wslpath/df; hand-verified explorer/clip.
    **148 pass. ALL 9 DOMAINS COMPLETE — Phase 2 done.**

## In progress

- Nothing. **Phase 2 complete (all 9 domains built, 148 tests pass).**

## Next (in order)

1. **Install + dogfood** — use `lb` for real daily WSL work and learn from what
   breaks (the ROADMAP philosophy). Set up the shell widget / `lb` on PATH.
2. From real use, decide **Phase 3** (the LinearSVC intent-only model) and
   **generalized multi-step** (V1.1) — driven by friction, not speculation.
3. Deferred, when motivated by use: dir_empty (filesystem), zip create/extract
   & gzip -l (archives), list_packages/venv helpers (python), nested-$() WSL
   path resolver (wsl_interop), general "do A then B" compound.
2. (Later / optional) Resolve the **3 genuine remaining FAILs** (dangling
   `$TARGET_FILE`) and decide whether to make the 13 ACCEPTED_EMPTY scenarios
   literal via small `build_maze.sh` additions — see below.

## Open bugs / dataset issues

- **3 genuine dataset defects remain** (same root cause): INS-007, FS-022,
  FS-040 all read `$TARGET_FILE` (`output/target.txt`), which **no scenario row
  creates** and the maze omits. Fix = rebind `TARGET_FILE` to an existing file,
  or create it (+ a producer) in `build_maze.sh`. Not fixed in Task 07 (it's a
  binding/fixture decision, not a command edit).
- No open bugs in `file_discovery` code.

## Decisions the human still needs to make

1. **`2>/dev/null` on generated find/grep/du/tar?** Should LinuxBuddy's
   *generated* recursive commands suppress permission-denied stderr (the cause
   of all 21 PASS_WITH_STDERR rows)? Trade-off and context in `LOG.md`
   (Task 07, Step 4). **Left open.**
2. **The 3 dangling-`TARGET_FILE` rows** — rebind or add fixture? (above)
3. **13 ACCEPTED_EMPTY scenarios** — leave accepted, or add small maze content
   (`.pt` checkpoints, a "deprecated"/METRICS block in train.log, `train_*`
   files, archives in `backups/`) to make them return real output? Each is a
   one-line `build_maze.sh` change; none is a command bug.

## Notes / watch-outs

- **ARCH-024 changed risk read-only → writes** in Task 07 (now does a `cp`
  before verifying) — it falls under the Phase-2 destructive-location gate.
- **Task 07 fixes are CSV-only; the maze (`build_maze.sh`) was NOT changed**,
  to keep the fixture stable. PY-003/018/024/036/037 + WORK-039 were repointed
  from `good_script.sh` to `scripts/train_stub.py` (`$TRAIN_SCRIPT`).
- **All 9 domains built:** `file_discovery`, `file_inspection`, `text_and_logs`,
  `processes` (+kill), `filesystem_permissions` (+chmod), `archives_backup`,
  `python_environments`, `workspace_and_shell` (+ scoped multi-step),
  `wsl_interop`. Reads work anywhere; all writes/destructive intents gated to
  the maze (P2.0). Planner/render support safe 2-stage `|` and `&&` composition
  (`Stages`) + compile-time ~/$HOME/$SHELL/$USER resolution.
- Router order: file_inspection → python → text_and_logs → processes →
  archives → wsl → filesystem → workspace → file_discovery.
- Single-command-only scope by design (setup_project is the one scoped recipe);
  compound/redirect/network/shell-state/nested-$() scenarios are deferred —
  hence modest per-domain maze coverage. Every built intent is verified
  end-to-end against the maze (or, for GUI/clipboard, by hand).
- `lb` lives in a uv venv. **Destructive-containment gate (P2.0) is now built**
  (`gate.py`/`config.py`); prototype mode is the default, maze root defaults to
  `~/linuxbuddy/testlinuxbuddy`.
- Owner is on bash; only the zsh widget exists.
- Verification host gaps (not dataset bugs): no `pandas`, no `python3-venv`,
  WSL kernel has no `/proc/<pid>/io` → 3 ENV_UNSUPPORTED rows.
