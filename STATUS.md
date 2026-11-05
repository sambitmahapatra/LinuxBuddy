# LinuxBuddy — Current Status

> The single source of truth for where the project is NOW. Overwrite this
> after every task. Keep it short. Next session reads this first.

**Last updated:** 2026-11-05 (after Task 14 / Tier 2 batch COMPLETE)
**Current phase:** Phase 2 — Tier 2 done; 2 domains remain
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

## In progress

- Nothing. Tier 2 batch (12–14) complete.

## Next (in order)

1. Quick follow-on (optional, now cheap — gate exists): `chmod`
   (filesystem_permissions) and `kill`/`pkill` (processes) complete those two
   Tier-1 domains.
2. Last/hardest two domains: `workspace_and_shell` (multi-step) and
   `wsl_interop` (GUI).
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
- Built domains (7): `file_discovery`, `file_inspection`, `text_and_logs`,
  `processes`, `filesystem_permissions` (read-only), `archives_backup`,
  `python_environments` (read + GATED writes). Planner/render support safe
  2-stage `|` and `&&` composition (`Stages` container). 2 domains to go.
- Single-command-only scope by design; compound, `/proc`-based, redirect,
  network, shell-state and (for Tier 1) destructive maze scenarios are
  deferred — hence modest per-domain maze coverage (inspection 5/40, text 8/40,
  processes 7/40, filesystem 1/40, archives 7/40, python ~6/40). Every built
  intent is verified correct end-to-end against the maze.
- `lb` lives in a uv venv. **Destructive-containment gate (P2.0) is now built**
  (`gate.py`/`config.py`); prototype mode is the default, maze root defaults to
  `~/linuxbuddy/testlinuxbuddy`.
- Owner is on bash; only the zsh widget exists.
- Verification host gaps (not dataset bugs): no `pandas`, no `python3-venv`,
  WSL kernel has no `/proc/<pid>/io` → 3 ENV_UNSUPPORTED rows.
