# LinuxBuddy — Test Maze (`testlinuxbuddy/`)

**Purpose:** a deterministic, disposable filesystem to run generated commands
against. Every scenario in the 360-scenario dataset needs real files to act
on; the maze provides them. It is rebuilt identically every time so test
results are reproducible.

**Location:** `~/linuxbuddy/testlinuxbuddy/` (gitignored — it's a build
artifact; the scripts that produce it live in `tools/fixture/` and are
committed).

**Rebuild:** `./testlinuxbuddy/build_maze.sh`
**Use:** `source testlinuxbuddy/bindings.env` (paths) and
`source testlinuxbuddy/runtime_setup.sh` (PID/PORT/GPU_ID).

---

## Hard rules the builder enforces

1. Refuses to run unless `MAZE_ROOT` is strictly under `$HOME` and is not
   `$HOME` itself. It never touches anything outside the maze.
2. Deterministic — fixed seed, fixed `touch -d` timestamps, fixed contents.
   Two builds produce a byte-identical `MANIFEST.txt`
   (sha256 `89ba5fc4…` — the current committed build; the older `5af914bd…`
   constant was stale, corrected in Task 25).
3. Idempotent — `rm -rf` then rebuild, every time. The 000-permission dir is
   restored to writable before each wipe so rebuilds never jam.
4. Pure bash + coreutils + git. No network, no pip.

---

## The tree

```
testlinuxbuddy/
├── build_maze.sh        # wipe-and-rebuild (preserves itself during wipe)
├── bindings.env         # 134 placeholder → absolute path bindings
├── runtime_setup.sh     # starts helpers, exports PID/PORT/GPU_ID
├── MANIFEST.txt         # ~2140 entries (type, perms, size, mtime) for diffing
├── project/             # a realistic data-science project
└── awkward/             # deliberately hostile filenames
```

### `project/` — the realistic workload

| Path | Contents | What it tests |
|---|---|---|
| `src/` | ~15 `.py` files, cross-imports; some contain `TODO`, `FIXME`, `API_URL`, "convergence" | find by type, grep for symbols/strings |
| `tests/` | ~5 `test_*.py` | find by name pattern |
| `notebooks/` | 3 `.ipynb` (valid minimal JSON) | find by extension |
| `data/raw/` | CSVs at 2K, 90K, 5M, **120M** (sparse); a `.tsv`, a `.jsonl` | **find by size** (the core thin-slice test) |
| `data/processed/` | a few outputs | copy/move targets |
| `logs/train.log` | ~2000 lines, timestamped INFO/WARNING/ERROR, a **traceback near the end**, the word **timeout** | tail, grep errors, log inspection |
| `logs/app.log` | smaller, different format | grep, preview |
| `logs/old/` | 3 rotated logs with **older mtimes** | find by time (-mtime +30) |
| `configs/` | `config.yaml`, `settings.json`, `.env.example` | inspect, diff, file-type detection |
| `.venv/` | `bin/activate`, `lib/`, `pyvenv.cfg` skeleton | venv detection (not a working venv) |
| `.git/` | **real repo**: 3 commits, a `feature/experiment` branch | git status/branch/log scenarios |
| `scripts/` | `crlf_script.sh` (CRLF → "bad interpreter"), `good_script.sh` (LF, +x), `not_executable.sh` (644) | **WSL line-ending bug**, permission/exec checks |
| `archives/` | `backup_*.tar.gz`, `release.zip`, `data.gz`, a **truncated/corrupt** tar.gz | list/extract archives, handle corruption |
| `perms/` | `readable.txt` (644), `private.txt` (600), `executable.sh` (755), `noaccess_dir/` (000) | permission inspection, the "Permission denied" path |
| `build/__pycache__/` | cache dirs | preview-delete-cache scenarios |
| `compare/` | paired files that genuinely differ (FILE_A/B, OLD/NEW_CONFIG, JSON_A/B, VENV_A/B with different `pip freeze`, …) | diff scenarios (non-vacuous) |

### `awkward/` — the hostile-input surface

This is what proves the renderer's quoting actually holds:

- a file **with spaces** in the name
- a file with **'single quotes'** in the name
- a file whose name **starts with a dash**
- a **unicode** filename
- a file with a **newline** in the name (skipped if the FS refuses)
- a **broken symlink** (target doesn't exist)
- a **valid symlink** pointing into `project/`
- an **8-level deep** nested chain
- a directory with **2000 small files** (stress + maxdepth tests)
- an **empty** directory

### WSL-specific material

- `scripts/crlf_script.sh` — CRLF endings + shebang, so running it produces
  the real "bad interpreter" error a WSL newcomer hits.
- `/mnt/c` bindings in `bindings.env` marked READ-ONLY — the Windows side is
  real, outside the maze, and never a write target.
- Windows profile path detected at build (`/mnt/c/Users/<you>`).

---

## Timestamps — the one deliberate compromise

`find -mtime`/`-mmin` test against the **real clock**, which fights fixed
timestamps. Resolution: a small tracked set (`train.log`, `app.log`, rotated
logs, one data file) gets **now-relative** mtimes so recency searches stay
meaningful on every rebuild; everything else uses hard-fixed `touch -d`
dates. The MANIFEST prints the relative ones as the literal token
`RELATIVE`, which is what keeps two builds byte-identical. `.git` internals
are normalized to a baseline mtime and excluded from the MANIFEST so the
fresh repo doesn't flood recency searches.

**Verified behaviours:**
- `find -size +100M` → `huge_dataset.csv` only
- `find -size +1M` → `huge_dataset.csv`, `sales.csv`
- `-mmin -60` / `-mtime -1` → `train.log` only
- `-mtime -7` → `train.log`, `app.log`
- `-mtime +30` → the older files, excludes the recent ones

---

## Bindings (`bindings.env`)

Exports ~134 `$PLACEHOLDER` → absolute-path variables so the 360 scenarios'
reference commands resolve. Organized by header: maze paths, aliases
(`$TRAIN_LOG`→`$LOG_FILE`, `$PROJECT_ROOT`→`$PROJECT_DIR`), comparison pairs,
write targets (intentionally absent, parents present), read-only Windows
paths. A NOTES section documents genuine CSV conflicts (e.g. `$PARENT_DIR`
used two incompatible ways across rows; one row that writes to real Windows
Documents).

**Runtime values** (`runtime_setup.sh`, not bindable in a file):
- `$PID` — a `sleep 300` background job
- `$PORT` — a `python3 -m http.server` on a free port
- `$GPU_ID` — `0` if `nvidia-smi` exists, else unset
Call `runtime_teardown` to stop them and unset the vars.

---

## How to test with it

```bash
cd ~/linuxbuddy
./testlinuxbuddy/build_maze.sh          # fresh, deterministic tree
source testlinuxbuddy/bindings.env      # path variables
source testlinuxbuddy/runtime_setup.sh  # PID / PORT / GPU_ID
cd testlinuxbuddy/project

# thin-slice check:
$(lb csv files over 100 megs)           # → ./data/raw/huge_dataset.csv

# full dataset verification (Prompts/06):
#   run every reference command, classify PASS/EMPTY/FAIL/SKIP/UNSAFE

# when done:
runtime_teardown
```

### Safety when running tests against it
- Never execute anything whose target resolves outside `~/testlinuxbuddy`.
- Never `sudo`, never write to `/mnt/c` — mark those SKIP.
- `risk=network` rows: don't execute.
- Long-runners: wrap in `timeout 5`.
- Rebuild before any batch that follows a `writes` test, so each batch starts
  from a clean tree.

---

## Checking determinism (do this if you change `build_maze.sh`)

```bash
./build_maze.sh && sha256sum MANIFEST.txt
./build_maze.sh && sha256sum MANIFEST.txt   # same hash = deterministic
```

If the hash moves, a non-`RELATIVE` timestamp or a random value leaked into
the build. The `RELATIVE` token for the few now-relative files is expected
and correct.
