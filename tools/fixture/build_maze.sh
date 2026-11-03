#!/usr/bin/env bash
#
# build_maze.sh — reproducible test filesystem for LinuxBuddy
#
# Wipes and rebuilds a deterministic, disposable tree under MAZE_ROOT.
# Two runs on two machines produce an identical MANIFEST.txt.
#
# Usage:   ./build_maze.sh
# Override root (still must live under $HOME): MAZE_ROOT=... ./build_maze.sh
#
# Pure bash + coreutils + git. No network, no pip, no downloads.

set -euo pipefail
export LC_ALL=C          # stable sort order & number formatting
export TZ=UTC            # stable timestamp formatting in the MANIFEST
umask 022

# ---------------------------------------------------------------------------
# 0. Configuration
# ---------------------------------------------------------------------------
MAZE_ROOT="${MAZE_ROOT:-$HOME/linuxbuddy/testlinuxbuddy}"

# A fixed baseline mtime for the bulk of the tree (fully deterministic).
BASE_DATE="2025-06-15 12:00:00"

# ---------------------------------------------------------------------------
# 1. Safety rails — refuse to run anywhere dangerous
# ---------------------------------------------------------------------------
HOME_REAL="$(realpath -m "$HOME")"
ROOT_REAL="$(realpath -m "$MAZE_ROOT")"

if [ -z "$HOME" ] || [ "$HOME" = "/" ]; then
  echo "FATAL: \$HOME is empty or '/'. Refusing to run." >&2
  exit 1
fi
if [ "$ROOT_REAL" = "$HOME_REAL" ]; then
  echo "FATAL: MAZE_ROOT resolves to \$HOME itself ($ROOT_REAL). Refusing." >&2
  exit 1
fi
case "$ROOT_REAL/" in
  "$HOME_REAL/"*) : ;;   # good: strictly under $HOME
  *)
    echo "FATAL: MAZE_ROOT ($ROOT_REAL) is not under \$HOME ($HOME_REAL). Refusing." >&2
    exit 1
    ;;
esac

# Absolute path to this very script, so the wipe never deletes itself.
SELF_REAL="$(realpath -m "${BASH_SOURCE[0]}")"

echo ">> MAZE_ROOT = $ROOT_REAL"

# ---------------------------------------------------------------------------
# 2. Wipe everything under MAZE_ROOT except this script
# ---------------------------------------------------------------------------
mkdir -p "$ROOT_REAL"
# Restore perms first so a 000 dir from a previous run can be removed.
chmod -R u+rwX "$ROOT_REAL" 2>/dev/null || true
shopt -s dotglob nullglob
for entry in "$ROOT_REAL"/*; do
  [ "$(realpath -m "$entry")" = "$SELF_REAL" ] && continue
  rm -rf "$entry"
done
shopt -u dotglob nullglob
echo ">> wiped (script preserved)"

# ---------------------------------------------------------------------------
# 3. Deterministic timestamps
# ---------------------------------------------------------------------------
# Most files use the fixed BASE_DATE. A small, tracked set of files use
# now-relative mtimes so that find's relative-time tests are meaningful even
# though the fixture is regenerated fresh before each test run:
#     -mmin -60     matches ~train.log (30 min old)
#     -mtime -1     matches ~train.log
#     -mtime -7     matches train.log + app.log (3 days) + recent data (10 days? no)
#     -mtime +30    matches the rotated old logs (45/60/90 days)
# These now-relative files are listed as RELATIVE in the MANIFEST so that two
# builds still produce byte-identical MANIFEST.txt.
NOW="$(date +%s)"
TS_30MIN=$(( NOW - 1800 ))
TS_3DAY=$((  NOW - 3*86400 ))
TS_10DAY=$(( NOW - 10*86400 ))
TS_45DAY=$(( NOW - 45*86400 ))
TS_60DAY=$(( NOW - 60*86400 ))
TS_90DAY=$(( NOW - 90*86400 ))

# Relative paths (relative to MAZE_ROOT) whose mtime is now-based.
REL_PATHS=(
  "project/logs/train.log"
  "project/logs/app.log"
  "project/logs/old/app.log.1"
  "project/logs/old/app.log.2"
  "project/logs/old/app.log.3"
  "project/data/raw/recent_events.jsonl"
  "project/scratch/old_run.log"
  "project/scratch/old_tmp.dat"
  "project/scratch/fresh.txt"
)

P="$ROOT_REAL/project"      # shorthand for the project dir

# ---------------------------------------------------------------------------
# 4. Directory skeleton
# ---------------------------------------------------------------------------
mkdir -p \
  "$P/src" "$P/tests" "$P/notebooks" \
  "$P/data/raw" "$P/data/processed" \
  "$P/logs/old" \
  "$P/configs" \
  "$P/.venv/bin" "$P/.venv/lib/python3.11/site-packages" \
  "$P/output" "$P/build/__pycache__" \
  "$P/scripts" "$P/archives" "$P/perms" \
  "$P/results" "$P/backups" "$P/downloads" "$P/exports" \
  "$P/tools" "$P/models" "$P/private" "$P/reports" \
  "$P/runs/run_001" "$P/runs/run_002" \
  "$P/compare" "$P/compare/venv_a/bin" "$P/compare/venv_b/bin" \
  "$P/photos/trip" "$P/shared" "$P/scratch" "$P/tmp" \
  "$ROOT_REAL/awkward"

# ---------------------------------------------------------------------------
# 5. Python source (~15 files, some importing each other)
# ---------------------------------------------------------------------------
cat > "$P/src/constants.py" <<'EOF'
# Project-wide constants.
API_URL = "https://api.example.com/v1"   # TODO: move to configs/config.yaml
MAX_ITER = 1000
CONVERGENCE_TOL = 1e-6   # convergence tolerance for the optimizer
EOF

cat > "$P/src/config.py" <<'EOF'
import os
from src.constants import API_URL, MAX_ITER

def load_config():
    # FIXME: this ignores configs/config.yaml and reads only the environment.
    return {
        "api_url": os.environ.get("API_URL", API_URL),
        "max_iter": MAX_ITER,
    }
EOF

cat > "$P/src/io_utils.py" <<'EOF'
import csv

def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.reader(fh))

def write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
EOF

cat > "$P/src/data_loader.py" <<'EOF'
from src.io_utils import read_csv
from src.constants import API_URL

class DataLoader:
    """Loads raw data. TODO: stream large files instead of read_csv."""
    def __init__(self, path):
        self.path = path
        self.api_url = API_URL

    def load(self):
        return read_csv(self.path)
EOF

cat > "$P/src/preprocess.py" <<'EOF'
from src.data_loader import DataLoader

def clean(rows):
    # drop empty rows
    return [r for r in rows if any(c.strip() for c in r)]

def run(path):
    return clean(DataLoader(path).load())
EOF

cat > "$P/src/features.py" <<'EOF'
def extract(rows):
    # FIXME: naive feature extraction, no scaling
    return [[float(c) for c in r if c.replace('.', '', 1).isdigit()] for r in rows]
EOF

cat > "$P/src/metrics.py" <<'EOF'
def mse(pred, true):
    n = len(true)
    return sum((p - t) ** 2 for p, t in zip(pred, true)) / n if n else 0.0

def accuracy(pred, true):
    n = len(true)
    return sum(p == t for p, t in zip(pred, true)) / n if n else 0.0
EOF

cat > "$P/src/optimizer.py" <<'EOF'
from src.constants import MAX_ITER, CONVERGENCE_TOL

def optimize(step, x0):
    """Iterate until convergence or MAX_ITER."""
    x = x0
    for i in range(MAX_ITER):
        nx = step(x)
        if abs(nx - x) < CONVERGENCE_TOL:
            # reached convergence
            return nx, i
        x = nx
    return x, MAX_ITER
EOF

cat > "$P/src/model.py" <<'EOF'
from src.optimizer import optimize
from src.features import extract

class Model:
    def __init__(self):
        self.weights = None

    def fit(self, rows):
        feats = extract(rows)
        # TODO: real training loop; this is a placeholder for convergence tests
        self.weights = [sum(col) for col in zip(*feats)] if feats else []
        return self

    def predict(self, rows):
        return [sum(r) for r in extract(rows)]
EOF

cat > "$P/src/train.py" <<'EOF'
from src.model import Model
from src.preprocess import run as preprocess
from src.metrics import mse

def train(path):
    rows = preprocess(path)
    model = Model().fit(rows)
    # API_URL referenced in logs for traceability
    return model

if __name__ == "__main__":
    train("data/raw/sales.csv")
EOF

cat > "$P/src/evaluate.py" <<'EOF'
from src.metrics import mse, accuracy
from src.model import Model

def evaluate(model, rows, truth):
    pred = model.predict(rows)
    return {"mse": mse(pred, truth), "acc": accuracy(pred, truth)}
EOF

cat > "$P/src/pipeline.py" <<'EOF'
from src.preprocess import run as preprocess
from src.model import Model
from src.evaluate import evaluate

def pipeline(path, truth):
    rows = preprocess(path)
    model = Model().fit(rows)
    return evaluate(model, rows, truth)
EOF

cat > "$P/src/plot.py" <<'EOF'
# Plotting helpers. TODO: switch from print-based stubs to matplotlib.
def plot_loss(history):
    for i, v in enumerate(history):
        print(f"{i}\t{v}")
EOF

cat > "$P/src/cli.py" <<'EOF'
import sys
from src.train import train

def main(argv=None):
    argv = argv or sys.argv[1:]
    path = argv[0] if argv else "data/raw/sales.csv"
    train(path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
EOF

cat > "$P/src/utils.py" <<'EOF'
import time

def timer(fn):
    def wrapped(*a, **k):
        t0 = time.time()
        try:
            return fn(*a, **k)
        finally:
            _ = time.time() - t0
    return wrapped
EOF

cat > "$P/src/__init__.py" <<'EOF'
__all__ = ["model", "train", "evaluate", "pipeline"]
EOF

# ---------------------------------------------------------------------------
# 6. Tests (~5 test_*.py)
# ---------------------------------------------------------------------------
cat > "$P/tests/__init__.py" <<'EOF'
EOF
cat > "$P/tests/test_metrics.py" <<'EOF'
from src.metrics import mse, accuracy

def test_mse_zero():
    assert mse([1, 2, 3], [1, 2, 3]) == 0.0

def test_accuracy():
    assert accuracy([1, 0], [1, 1]) == 0.5
EOF
cat > "$P/tests/test_model.py" <<'EOF'
from src.model import Model

def test_fit_empty():
    assert Model().fit([]).weights == []
EOF
cat > "$P/tests/test_preprocess.py" <<'EOF'
from src.preprocess import clean

def test_clean_drops_empty():
    assert clean([["", ""], ["1", "2"]]) == [["1", "2"]]
EOF
cat > "$P/tests/test_optimizer.py" <<'EOF'
from src.optimizer import optimize

def test_converges():
    # x -> x/2 converges to 0
    x, iters = optimize(lambda x: x / 2.0, 1.0)
    assert abs(x) < 1e-5
EOF
cat > "$P/tests/test_pipeline.py" <<'EOF'
from src.pipeline import pipeline

def test_pipeline_smoke(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("1,2\n3,4\n")
    out = pipeline(str(p), [3.0, 7.0])
    assert "mse" in out
EOF

# The five files above are pytest-style (bare `def test_*` functions), which
# `python3 -m unittest discover` cannot collect — it reports "Ran 0 tests".
# This one is a real unittest.TestCase so that the compile-then-unittest row
# actually runs something. Self-contained: no `src.*` import, so it passes
# from any working directory.
cat > "$P/tests/test_unittest_smoke.py" <<'EOF'
"""A unittest.TestCase, so `unittest discover` has something to collect.

The other test modules here are pytest-style and are invisible to unittest.
This one imports nothing from the project so it passes regardless of cwd.
"""
import unittest


class SmokeTest(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(2 + 2, 4)

    def test_string_join(self):
        self.assertEqual(",".join(["a", "b"]), "a,b")


if __name__ == "__main__":
    unittest.main()
EOF

# ---------------------------------------------------------------------------
# 7. Notebooks (3 valid minimal .ipynb)
# ---------------------------------------------------------------------------
make_ipynb() {  # $1=path  $2=first-cell-source
  cat > "$1" <<EOF
{
 "cells": [
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "$2"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
  "language_info": {"name": "python", "version": "3.11.0"}
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
EOF
}
make_ipynb "$P/notebooks/01_explore.ipynb"   "import pandas as pd  # explore the raw data"
make_ipynb "$P/notebooks/02_features.ipynb"  "from src.features import extract"
make_ipynb "$P/notebooks/03_report.ipynb"    "print('convergence report')"

# ---------------------------------------------------------------------------
# 8. Data files of varied size (sizes exact so `find -size` works)
# ---------------------------------------------------------------------------
# 2 KB CSV (2048 bytes)
{
  echo "id,name,value,category"
  i=0
  while [ "$(wc -c < "$P/data/raw/small.csv" 2>/dev/null || echo 0)" -lt 2048 ] 2>/dev/null; do
    printf '%d,item_%d,%d.%02d,cat_%d\n' "$i" "$i" "$i" $(( i % 100 )) $(( i % 5 ))
    i=$(( i + 1 ))
    [ "$i" -gt 500 ] && break
  done
} > "$P/data/raw/small.csv"
truncate -s 2048 "$P/data/raw/small.csv"

# 90 KB CSV (92160 bytes) built fast from a repeating deterministic line.
# `yes` is killed by SIGPIPE when head closes the pipe; `|| true` keeps that
# from tripping `pipefail`/`set -e`.
{ yes "id,x,y,label,note,extra_padding_field_for_width" || true; } \
  | head -c 92160 > "$P/data/raw/measurements.csv"

# 5 MB CSV (5242880 bytes), real content, generated fast
{ yes "row,alpha,beta,gamma,delta,epsilon,zeta,comment_column_here" || true; } \
  | head -c 5242880 > "$P/data/raw/sales.csv"

# 120 MB CSV (125829120 bytes) — sparse; apparent size is correct for find -size
truncate -s 125829120 "$P/data/raw/huge_dataset.csv"

# A TSV and a JSONL
printf 'id\tname\tscore\n1\talice\t0.91\n2\tbob\t0.78\n3\tcarol\t0.85\n' \
  > "$P/data/raw/table.tsv"
{
  printf '{"id":1,"event":"start","ok":true}\n'
  printf '{"id":2,"event":"step","ok":true}\n'
  printf '{"id":3,"event":"timeout","ok":false}\n'
} > "$P/data/raw/events.jsonl"
# recent_events.jsonl gets a now-relative mtime (see REL_PATHS)
{
  printf '{"id":10,"event":"recent","ok":true}\n'
  printf '{"id":11,"event":"recent","ok":true}\n'
} > "$P/data/raw/recent_events.jsonl"

# A top-level data inventory + a windows stub + a linux-native file
printf 'sku,qty,location\nA1,10,shelf-1\nB2,5,shelf-2\n' > "$P/data/inventory.csv"
printf 'This file stands in for a native Linux-filesystem file.\n' > "$P/data/linux_native.txt"
printf 'Stub. Real /mnt/c tests run against the Windows mount, not here.\n' > "$P/data/windows_stub.txt"

# Blank out the `note` column on every 10th line of measurements.csv.
# Four spaces replace the four characters of "note", so the file stays exactly
# 92160 bytes and the `find -size` tests above are unaffected — but the column
# now has 192 missing values, so INS-037 ("how many rows have an empty value in
# the target column") counts something instead of passing on a column that has
# no blanks anywhere.
sed -i '0~10s/,note,/,    ,/' "$P/data/raw/measurements.csv"

# --- one-item-per-line text fixtures (sort / uniq / cut rows) ---
# Deliberately unsorted and with repeats: `sort -u` and `uniq -c` have to
# actually do something for the row to prove anything.
{
  printf 'widget\ngadget\nwidget\nsprocket\ngadget\nwidget\ncog\n'
} > "$P/data/raw/items.txt"

{
  printf 'Yusuf\nAnna\nmarek\nBeatriz\nanna\nChidi\n'
} > "$P/data/raw/names.txt"

# "network" is the clear winner (4), so `sort | uniq -c | sort -nr` has an
# unambiguous first line to check.
{
  printf 'network\ndisk\nnetwork\nmemory\nnetwork\ndisk\nnetwork\ncpu\n'
} > "$P/data/raw/categories.txt"

# Three distinct domains, one of them repeated.
{
  printf 'ana@example.com\nbob@test.org\ncarol@example.com\n'
  printf 'dan@other.net\neve@example.com\n'
} > "$P/data/raw/emails.txt"

# Status-code-only export; 200 dominates, 404 second.
{
  printf '200\n200\n404\n200\n500\n404\n200\n301\n200\n404\n'
} > "$P/data/raw/status_codes.txt"

# A list with blank AND whitespace-only lines, so `grep -v "^[[:space:]]*$"`
# removes 3 of the 8 lines rather than nothing.
{
  printf 'alpha\n\nbeta\n   \ngamma\n\t\ndelta\nepsilon\n'
} > "$P/data/raw/list_with_blanks.txt"

# JSONL whose line 3 is malformed (trailing comma) — the point of the row is
# to find a bad line, which needs one to exist.
{
  printf '{"id":1,"event":"start","ok":true}\n'
  printf '{"id":2,"event":"step","ok":true}\n'
  printf '{"id":3,"event":"step","ok":true,}\n'
  printf '{"id":4,"event":"done","ok":true}\n'
} > "$P/data/raw/malformed.jsonl"

# 256 bytes of genuinely non-text data for `od -N64`. Built from a fixed byte
# sequence rather than /dev/urandom so two builds agree.
# 0x00..0xff once: every byte value, so the file is unambiguously binary.
{ _b=0; while [ "$_b" -le 255 ]; do printf "$(printf '\\%03o' "$_b")"; _b=$(( _b + 1 )); done; } \
  > "$P/data/raw/sample.bin"

# A temp-notes file to be renamed (the `mv -n` row needs an existing source).
printf 'scratch thoughts, to be renamed\n' > "$P/data/raw/old_notes.txt"

# processed outputs
printf 'metric,value\nmse,0.0123\nacc,0.98\n' > "$P/data/processed/metrics.csv"
printf 'cleaned rows: 4210\n' > "$P/data/processed/summary.txt"
printf '# Summary Report\n\nConvergence reached at iter 412.\n' > "$P/data/processed/summary_report.md"

# ---------------------------------------------------------------------------
# 9. Logs
# ---------------------------------------------------------------------------
# train.log ~2000 lines with INFO/WARNING/ERROR, a traceback, "timeout" and
# "failed" (the latter for the "save every line containing failed" row).
{
  n=1
  while [ "$n" -le 1980 ]; do
    sec=$(( n % 60 )); mnt=$(( (n / 60) % 60 ))
    ts=$(printf '2025-06-15 09:%02d:%02d' "$mnt" "$sec")
    lvl=INFO
    [ $(( n % 50 )) -eq 0 ] && lvl=WARNING
    [ $(( n % 137 )) -eq 0 ] && lvl=ERROR
    [ $(( n % 211 )) -eq 0 ] && lvl=ERROR
    if [ $(( n % 137 )) -eq 0 ]; then
      printf '%s %s epoch=%d loss=%.4f timeout waiting for data batch\n' \
        "$ts" "$lvl" "$(( n / 10 ))" "0.$(( 9999 - n ))"
    elif [ $(( n % 211 )) -eq 0 ]; then
      printf '%s %s epoch=%d step=%d checkpoint upload failed (retrying)\n' \
        "$ts" "$lvl" "$(( n / 10 ))" "$n"
    else
      printf '%s %s epoch=%d step=%d loss=%.4f convergence_delta=%.6f\n' \
        "$ts" "$lvl" "$(( n / 10 ))" "$n" "0.$(( 5000 + n ))" "0.00$(( n % 1000 ))"
    fi
    n=$(( n + 1 ))
  done
  # A traceback near the end
  cat <<'TB'
2025-06-15 09:59:58 ERROR Uncaught exception during final evaluation
Traceback (most recent call last):
  File "src/train.py", line 9, in train
    model = Model().fit(rows)
  File "src/model.py", line 12, in fit
    self.weights = [sum(col) for col in zip(*feats)]
ValueError: not enough values to unpack (timeout on data loader)
2025-06-15 10:00:00 INFO run finished with errors
TB
} > "$P/logs/train.log"

# app.log — smaller, different (syslog-ish) format
{
  printf 'Jun 15 08:00:01 host linuxbuddy[1024]: service started\n'
  printf 'Jun 15 08:00:02 host linuxbuddy[1024]: loaded config\n'
  printf 'Jun 15 08:00:05 host linuxbuddy[1024]: WARN cache miss\n'
  printf 'Jun 15 08:01:00 host linuxbuddy[1024]: request handled in 12ms\n'
} > "$P/logs/app.log"

# a status file some commands target
printf 'status: idle\nlast_run: 2025-06-15\n' > "$P/logs/status.txt"

# 3 rotated logs (older mtimes set later)
printf 'rotated app log 1\n' > "$P/logs/old/app.log.1"
printf 'rotated app log 2\n' > "$P/logs/old/app.log.2"
printf 'rotated app log 3\n' > "$P/logs/old/app.log.3"

# ---------------------------------------------------------------------------
# 10. Configs
# ---------------------------------------------------------------------------
cat > "$P/configs/config.yaml" <<'EOF'
project: linuxbuddy-demo
seed: 42
training:
  max_iter: 1000
  tol: 1.0e-6
  convergence_patience: 10
api:
  url: https://api.example.com/v1
  timeout: 30
EOF
cat > "$P/configs/settings.json" <<'EOF'
{
  "project": "linuxbuddy-demo",
  "seed": 42,
  "paths": {"data": "data/raw", "output": "output"},
  "flags": {"verbose": true, "dry_run": false}
}
EOF
cat > "$P/configs/.env.example" <<'EOF'
API_URL=https://api.example.com/v1
API_TOKEN=replace-me
DATA_DIR=./data/raw
LOG_LEVEL=INFO
EOF

# ---------------------------------------------------------------------------
# 11. .venv skeleton (looks like a venv, need not work)
# ---------------------------------------------------------------------------
cat > "$P/.venv/pyvenv.cfg" <<'EOF'
home = /usr/bin
include-system-site-packages = false
version = 3.11.0
executable = /usr/bin/python3.11
command = /usr/bin/python3.11 -m venv
EOF
cat > "$P/.venv/bin/activate" <<'EOF'
# This file must be used with "source bin/activate" from bash
deactivate () {
    unset -f deactivate
    [ -n "${_OLD_VIRTUAL_PATH:-}" ] && PATH="$_OLD_VIRTUAL_PATH" && export PATH
}
VIRTUAL_ENV="__VENV_DIR__"
export VIRTUAL_ENV
_OLD_VIRTUAL_PATH="$PATH"
PATH="$VIRTUAL_ENV/bin:$PATH"
export PATH
EOF
printf '#!/bin/sh\nexec /usr/bin/python3.11 "$@"\n' > "$P/.venv/bin/python"
ln -s python "$P/.venv/bin/python3"
chmod 755 "$P/.venv/bin/python"
printf 'pip 23.0 from .venv\n' > "$P/.venv/bin/pip"
chmod 755 "$P/.venv/bin/pip"
printf 'numpy==1.26.0\n' > "$P/.venv/lib/python3.11/site-packages/_marker.txt"

# ---------------------------------------------------------------------------
# 12. build caches to find/preview-delete
# ---------------------------------------------------------------------------
printf 'cache\n' > "$P/build/__pycache__/model.cpython-311.pyc"
printf 'cache\n' > "$P/build/__pycache__/train.cpython-311.pyc"
mkdir -p "$P/src/__pycache__"
printf 'cache\n' > "$P/src/__pycache__/utils.cpython-311.pyc"

# ---------------------------------------------------------------------------
# 13. scripts (WSL-specific material)
# ---------------------------------------------------------------------------
# good_script.sh — LF, executable, prints something
printf '#!/usr/bin/env bash\necho "good_script OK: $(date -u +%%Y)"\n' > "$P/scripts/good_script.sh"
chmod 755 "$P/scripts/good_script.sh"

# not_executable.sh — LF, chmod 644
printf '#!/usr/bin/env bash\necho "you should chmod +x me first"\n' > "$P/scripts/not_executable.sh"
chmod 644 "$P/scripts/not_executable.sh"

# crlf_script.sh — CRLF endings + shebang -> "bad interpreter" when run
printf '#!/usr/bin/env bash\r\necho "this line has CRLF endings"\r\n' > "$P/scripts/crlf_script.sh"
chmod 755 "$P/scripts/crlf_script.sh"

# ---------------------------------------------------------------------------
# 14. Archives
# ---------------------------------------------------------------------------
# A small tarball with a few files
_tmp_tar="$(mktemp -d)"
printf 'alpha\n' > "$_tmp_tar/a.txt"
printf 'beta\n'  > "$_tmp_tar/b.txt"
printf 'gamma\n' > "$_tmp_tar/c.txt"
# A README member, so "extract just the README from this backup" has something
# to extract (ARCHIVE_MEMBER binds to this name).
printf 'Backup README\n\nContents: a.txt, b.txt, c.txt\nCreated by build_maze.sh\n' \
  > "$_tmp_tar/README.md"
# Deterministic tar: fixed mtime, sorted, no owner metadata noise
tar --sort=name --mtime="$BASE_DATE" --owner=0 --group=0 --numeric-owner \
    -czf "$P/archives/backup_2026-01.tar.gz" -C "$_tmp_tar" README.md a.txt b.txt c.txt
rm -rf "$_tmp_tar"

# A single gzipped file (-n => no name/mtime in header => deterministic)
printf 'this is a single gzipped payload\nline two\n' \
  | gzip -n -c > "$P/archives/data.gz"

# A deliberately truncated / corrupt tar.gz
head -c 64 "$P/archives/backup_2026-01.tar.gz" > "$P/archives/corrupt.tar.gz"

# release.zip — zip not installed on this box; leave a clear note instead
if command -v zip >/dev/null 2>&1; then
  _tmp_zip="$(mktemp -d)"
  printf 'release artifact 1\n' > "$_tmp_zip/release1.txt"
  printf 'release artifact 2\n' > "$_tmp_zip/release2.txt"
  ( cd "$_tmp_zip" && zip -q -X "$P/archives/release.zip" release1.txt release2.txt )
  rm -rf "$_tmp_zip"
else
  printf 'NOTE: zip binary not available at build time; real release.zip not created.\n' \
    > "$P/archives/release.zip.MISSING.txt"
fi

# ---------------------------------------------------------------------------
# 14b. Comparison pairs — project/compare/
# ---------------------------------------------------------------------------
# The CSV has ~12 rows that compare two things ($FILE_A/$FILE_B, $OLD_CONFIG/
# $NEW_CONFIG, $LOG_A/$LOG_B, $JSON_A/$JSON_B, $VENV_A/$VENV_B, ...). Each pair
# below differs DELIBERATELY and in a small, stated way. Two identical files
# would make every one of those rows pass without comparing anything, which is
# the failure mode this directory exists to prevent.
#
# Note on exit codes: for a pair that differs, `cmp -s a b && echo identical`
# prints nothing and exits 1, and `diff -u a b` exits 1. That is the correct
# result for differing inputs — a verifier must judge these rows on their
# output, not on exit status alone.
C="$P/compare"

# FILE_A / FILE_B — differ in ONE cell (row 2 units: 95 -> 97).
printf 'id,region,units\n1,north,120\n2,south,95\n3,east,143\n'  > "$C/export_a.csv"
printf 'id,region,units\n1,north,120\n2,south,97\n3,east,143\n'  > "$C/export_b.csv"

# OLD_CONFIG / NEW_CONFIG — three changes: one value edited, one removed,
# one added. `diff -u` therefore shows a +, a - and a changed line.
cat > "$C/config_old.yaml" <<'EOF'
batch_size: 32
learning_rate: 0.001
epochs: 10
optimizer: adam
early_stopping: true
EOF
cat > "$C/config_new.yaml" <<'EOF'
batch_size: 64
learning_rate: 0.001
epochs: 10
optimizer: adam
weight_decay: 0.0001
EOF

# JSON_A / JSON_B — different TOP-LEVEL key sets ("cache" dropped,
# "telemetry" added), which is what the row prints.
cat > "$C/settings_v1.json" <<'EOF'
{
  "api": {"url": "https://api.example.com/v1", "timeout": 30},
  "cache": {"enabled": true, "ttl": 300},
  "logging": {"level": "INFO"}
}
EOF
cat > "$C/settings_v2.json" <<'EOF'
{
  "api": {"url": "https://api.example.com/v2", "timeout": 15},
  "logging": {"level": "DEBUG"},
  "telemetry": {"enabled": false}
}
EOF

# LOG_A / LOG_B — each ALREADY sorted by its leading ISO timestamp, and they
# interleave, so `sort -m` has a real merge to perform.
cat > "$C/log_a.log" <<'EOF'
2025-06-15T09:00:01Z a: started
2025-06-15T09:00:05Z a: loading data
2025-06-15T09:00:09Z a: finished
EOF
cat > "$C/log_b.log" <<'EOF'
2025-06-15T09:00:02Z b: started
2025-06-15T09:00:04Z b: connected
2025-06-15T09:00:07Z b: finished
EOF

# LIST_A / LIST_B — overlap of exactly 3 ids, each list unsorted with a repeat
# (the row sorts and dedupes them itself).
printf 'ID-004\nID-001\nID-003\nID-005\nID-001\nID-002\n' > "$C/ids_a.txt"
printf 'ID-005\nID-008\nID-003\nID-009\nID-004\nID-008\n' > "$C/ids_b.txt"

# COMPLETED_IDS / FAILED_IDS — "in failed but not completed" is JOB-1003 and
# JOB-1005, i.e. a non-empty answer.
printf 'JOB-1001\nJOB-1002\nJOB-1004\n'            > "$C/completed_ids.txt"
printf 'JOB-1002\nJOB-1003\nJOB-1005\n'            > "$C/failed_ids.txt"

# RUN_A_STATUS / RUN_B_STATUS — "timeout" is the label that disappeared.
printf 'ok\nok\nretry\ntimeout\nfailed\nok\n'    > "$C/run_a_status.txt"
printf 'ok\nretry\nfailed\nok\nok\n'              > "$C/run_b_status.txt"

# RESULT_A / RESULT_B — different sizes AND different mtimes, since the row
# prints both (mtimes are set in section 19).
printf 'run A: converged at iter 412\n'                              > "$C/result_a.txt"
printf 'run B: converged at iter 1180 after a learning-rate restart\n' > "$C/result_b.txt"

# FIRST_FILE / SECOND_FILE — 4 KiB vs 64 KiB, far enough apart that `du -h`
# shows two visibly different values (4.0K vs 64K).
{ yes 'id,value,label_padding_for_width' || true; } | head -c 4096  > "$C/dataset_small.csv"
{ yes 'id,value,label_padding_for_width' || true; } | head -c 65536 > "$C/dataset_large.csv"

# DEST_FILE / NEW_EXPORT — the "current" export and a "proposed" replacement:
# one changed row and one extra row, so size and content both differ.
printf 'sku,qty\nA1,10\nB2,5\nC3,7\n'        > "$C/export_current.csv"
printf 'sku,qty\nA1,12\nB2,5\nC3,7\nD4,3\n' > "$C/export_proposed.csv"

# BACKUP_A / BACKUP_B — two tarballs that are NOT byte-identical (b.txt
# differs). Deterministic: sorted members, fixed mtime, no owner noise, and
# tar pipes to gzip so no filename/mtime lands in the gzip header.
_tmp_a="$(mktemp -d)"; _tmp_b="$(mktemp -d)"
printf 'alpha\n'         > "$_tmp_a/a.txt"; printf 'alpha\n'        > "$_tmp_b/a.txt"
printf 'beta\n'          > "$_tmp_a/b.txt"; printf 'beta REVISED\n' > "$_tmp_b/b.txt"
printf 'shared config\n' > "$_tmp_a/c.txt"; printf 'shared config\n' > "$_tmp_b/c.txt"
for _v in a b; do
  eval "_src=\$_tmp_$_v"
  tar --sort=name --mtime="$BASE_DATE" --owner=0 --group=0 --numeric-owner \
      -czf "$C/backup_$_v.tar.gz" -C "$_src" a.txt b.txt c.txt
done
rm -rf "$_tmp_a" "$_tmp_b"

# BASELINE_FILE — a timestamp reference older than everything in
# $RESULTS_DIR, so `find -newer` returns a non-empty list. Its old mtime is
# set in section 19.
printf 'baseline checkpoint marker\n' > "$C/baseline_checkpoint.txt"

# VENV_A / VENV_B — two venv skeletons whose bin/python answers exactly one
# command: `-m pip freeze`. A real pair of venvs cannot be built here (the
# builder is offline and must be deterministic, and pip is neither), but the
# row under test is the pip-freeze-and-diff pipeline, not pip itself. The two
# package lists differ by one version bump, one removal and one addition.
for _v in a b; do
  cat > "$P/compare/venv_$_v/bin/python" <<'EOF'
#!/usr/bin/env bash
# Stub interpreter — NOT a working Python. It implements `-m pip freeze` only,
# so the "which packages differ between these two venvs" row is runnable
# offline and gives the same answer on every machine.
if [ "$1" = "-m" ] && [ "$2" = "pip" ] && [ "$3" = "freeze" ]; then
  cat "$(dirname "$0")/../freeze.txt"
  exit 0
fi
echo "stub python: only '-m pip freeze' is implemented" >&2
exit 2
EOF
  chmod 755 "$P/compare/venv_$_v/bin/python"
done
printf 'numpy==1.26.0\npandas==2.1.0\npyyaml==6.0.1\nrequests==2.31.0\n' \
  > "$P/compare/venv_a/freeze.txt"
printf 'numpy==1.26.4\npandas==2.1.0\npyyaml==6.0.1\nscipy==1.11.4\n' \
  > "$P/compare/venv_b/freeze.txt"

# ---------------------------------------------------------------------------
# 15. Permissions material
# ---------------------------------------------------------------------------
printf 'world readable\n' > "$P/perms/readable.txt";    chmod 644 "$P/perms/readable.txt"
printf 'owner only\n'     > "$P/perms/private.txt";     chmod 600 "$P/perms/private.txt"
printf '#!/usr/bin/env bash\necho exec\n' > "$P/perms/executable.sh"; chmod 755 "$P/perms/executable.sh"
mkdir -p "$P/perms/noaccess_dir"
printf 'hidden behind 000 dir\n' > "$P/perms/noaccess_dir/secret.txt"
# chmod 000 applied LAST (after timestamps) — see section 19.

# private dir (for PRIVATE_DIR binding)
printf 'secret notes\n' > "$P/private/notes.txt"; chmod 600 "$P/private/notes.txt"

# ---------------------------------------------------------------------------
# 16. Misc project files referenced by bindings
# ---------------------------------------------------------------------------
cat > "$P/requirements.txt" <<'EOF'
numpy==1.26.0
pandas==2.1.0
pyyaml==6.0.1
pytest==7.4.0
EOF

cat > "$P/README.md" <<'EOF'
# LinuxBuddy Test Maze — project

A synthetic data-science project used as a fixture for verifying generated
shell commands. Everything here is disposable and regenerated by
`build_maze.sh`.

## WSL / Windows note
Tests that touch `/mnt/c` (the real Windows mount) are NOT simulated in this
tree. The file `data/windows_stub.txt` is only a stand-in. Any `/mnt/c`
command must be run against the actual Windows mount on a WSL host.

## Layout
- `src/`        Python source (some modules import each other)
- `tests/`      pytest-style tests
- `notebooks/`  minimal Jupyter notebooks
- `data/`       raw (varied sizes, tsv, jsonl) and processed outputs
- `logs/`       train.log (~2000 lines, traceback, "timeout", "failed"), app.log, old/
- `configs/`    config.yaml, settings.json, .env.example, runtime.env, credentials.txt
- `.venv/`      venv skeleton (not a working venv)
- `scripts/`    good / not-executable / CRLF scripts, train_stub.py
- `archives/`   tar.gz (incl. a README member), gz, truncated corrupt.tar.gz
- `perms/`      files with varied permissions incl. a 000 dir
- `compare/`    deliberately-differing pairs for the comparison rows
- `photos/`     .jpg / .JPG / .jpeg mix, for case-insensitive matching
- `shared/`     files owned by the build user
- `scratch/`    two files older than 30 days, one fresh
- `tmp/`        *.tmp files at depth 1 and deeper
EOF

cat > "$P/.gitignore" <<'EOF'
__pycache__/
*.pyc
.venv/
output/
build/
data/raw/huge_dataset.csv
EOF

printf 'reusable tool stub\n' > "$P/tools/helper.sh"; chmod 755 "$P/tools/helper.sh"
printf 'model bytes (not a real pickle)\n' > "$P/models/model.pkl"
{
  printf 'sku,qty,revenue\n'
  printf 'A1,10,120.50\n'
  printf 'B2,5,64.00\n'
  printf '\n'
  printf 'C3,7,88.25\n'
  printf 'D4,2,19.99\n'
  printf 'E5,9,210.75\n'
  printf 'F6,1,12.00\n'
} > "$P/exports/export_2025-06.csv"
printf 'backup of sales\n' > "$P/backups/sales.bak.csv"
printf 'id,value\n1,10\n2,20\n' > "$P/downloads/dataset.csv"
printf 'run 001 metrics\nacc=0.97\n' > "$P/runs/run_001/metrics.txt"
printf 'run 002 metrics\nacc=0.98\n' > "$P/runs/run_002/metrics.txt"
printf '# Analysis report\n\nSee data/processed/summary_report.md\n' > "$P/reports/report.md"
printf 'plain text sample for TEXT_FILE binding\n' > "$P/data/processed/notes.txt"

# ---------------------------------------------------------------------------
# 16b. Fixtures for the remaining newly bound placeholders
# ---------------------------------------------------------------------------

# --- PHOTO_DIR: the row counts *.jpg case-INSENSITIVELY -------------------
# .jpg + .JPG + a nested .jpg match -iname "*.jpg" (3); the .jpeg and the
# .txt do not. A case-sensitive -name would find only 1, so the row's -iname
# is doing visible work.
printf 'jpeg stub 1\n' > "$P/photos/img_01.jpg"
printf 'jpeg stub 2\n' > "$P/photos/img_02.JPG"
printf 'jpeg stub 3\n' > "$P/photos/trip/img_03.jpg"
printf 'jpeg stub 4\n' > "$P/photos/trip/sunset.jpeg"
printf 'not an image\n' > "$P/photos/captions.txt"

# --- SHARED_DIR: files owned by the invoking user --------------------------
# Every file here is owned by whoever ran the build, which is what
# `find -user "$(id -un)"` selects. Seeding a file owned by ANOTHER user would
# need root, so this row cannot be made discriminating in an unprivileged
# fixture — see the note in bindings.env.
printf 'shared dataset notes\n' > "$P/shared/notes.txt"
printf 'sku,qty\nX1,3\n'        > "$P/shared/inventory.csv"
printf 'team readme\n'           > "$P/shared/README.md"

# --- SCRATCH_DIR: "older than 30 days" needs both sides of the cutoff -----
# old_* get mtimes far past the cutoff and fresh.txt gets a now-relative one
# inside it (section 19), so the -mmin test has to discriminate. fresh.txt
# cannot simply keep BASE_DATE: that is a fixed past date, so it drifts and
# would itself count as "older than 30 days".
printf 'abandoned run output\n' > "$P/scratch/old_run.log"
printf 'stale intermediate\n'   > "$P/scratch/old_tmp.dat"
printf 'still in use\n'         > "$P/scratch/fresh.txt"

# --- TEMP_DIR: *.tmp among non-.tmp, and one in a subdir ------------------
# The row is -maxdepth 1, so nested/deep.tmp must be excluded by the depth
# limit rather than by luck.
printf 'temp payload 1\n' > "$P/tmp/cache_a.tmp"
printf 'temp payload 2\n' > "$P/tmp/cache_b.tmp"
printf 'keep me\n'        > "$P/tmp/keep.txt"
mkdir -p "$P/tmp/nested"
printf 'deeper temp\n'    > "$P/tmp/nested/deep.tmp"

# --- SECRET_FILE: starts world-readable so `chmod 600` is observable -----
# project/private/notes.txt is already 600, so binding SECRET_FILE there
# would make the chmod row a no-op.
cat > "$P/configs/credentials.txt" <<'EOF'
# Fake credentials for permission tests. Not a real secret.
DB_USER=maze
DB_PASSWORD=not-a-real-password
API_TOKEN=replace-me
EOF
chmod 644 "$P/configs/credentials.txt"

# --- ENV_FILE: a file that is SAFE to `source` ----------------------------
# configs/.env.example is the obvious candidate but it sets DATA_DIR, which
# would clobber the bound $DATA_DIR in the caller's shell and break every
# later row that uses it. This file deliberately defines only names that no
# binding uses.
cat > "$P/configs/runtime.env" <<'EOF'
APP_ENV=staging
FEATURE_FLAGS=fast-path,new-loader
MAX_WORKERS=4
LOG_FORMAT=json
EOF

# --- TRAIN_SCRIPT: a script that actually runs -----------------------------
# src/train.py imports `src.*`, so `python3 src/train.py` fails on sys.path
# and `python3 -m src.train` needs cwd=$PROJECT_DIR. The rows that bind
# TRAIN_SCRIPT just run it and capture output, so they need something
# self-contained: no imports beyond the stdlib, deterministic output, exit 0.
cat > "$P/scripts/train_stub.py" <<'EOF'
"""Stand-in training script: deterministic, no third-party imports, exit 0.

Prints a few epoch lines so a captured log has content to inspect, and echoes
CUDA_VISIBLE_DEVICES so the "run it with these environment settings" rows can
be checked from their own output.
"""
import os
import sys

def main() -> int:
    print(f"device: CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '<unset>')}")
    print(f"mode:   RUN_MODE={os.environ.get('RUN_MODE', '<unset>')}")
    loss = 1.0
    for epoch in range(1, 4):
        loss /= 2
        print(f"epoch {epoch}/3  loss={loss:.4f}")
    print("training complete")
    return 0

if __name__ == "__main__":
    sys.exit(main())
EOF
chmod 755 "$P/scripts/train_stub.py"

# --- MANIFEST_FILE: a checksum file `sha256sum -c` can verify -------------
# The row cds into $BACKUP_DIR first, so the manifest must name its files
# relative to that directory and must not list itself.
printf 'backup of inventory\n' > "$P/backups/inventory.bak.csv"
printf 'backup of config\n'    > "$P/backups/config.bak.yaml"
(
  cd "$P/backups"
  LC_ALL=C sha256sum config.bak.yaml inventory.bak.csv sales.bak.csv > MANIFEST.sha256
)

# ---------------------------------------------------------------------------
# 17. Awkward content
# ---------------------------------------------------------------------------
A="$ROOT_REAL/awkward"
printf 'has spaces\n'        > "$A/file with spaces.txt"
printf 'has single quotes\n' > "$A/file with 'single quotes'.txt"
printf 'leading dash\n'      > "$A/-dashfile.txt"
printf 'unicode name\n'      > "$A/café_ünïcode_文件.txt"
# newline-in-name (may fail on some filesystems — guarded)
if printf 'newline name\n' > "$A/$(printf 'line1\nline2').txt" 2>/dev/null; then
  :
else
  echo ">> note: filesystem refused newline-in-name file; skipped" >&2
fi
# broken symlink (relative target that does not exist)
ln -s does_not_exist_target "$A/broken_link"
# valid symlink into project/ (relative, so it stays machine-independent)
ln -s ../project/src "$A/link_to_project_src"
# deeply nested chain, 8 levels
mkdir -p "$A/nest/l1/l2/l3/l4/l5/l6/l7/l8"
printf 'bottom of the 8-level chain\n' > "$A/nest/l1/l2/l3/l4/l5/l6/l7/l8/bottom.txt"
# empty directory
mkdir -p "$A/empty_dir"
# directory containing 2000 small files
BIG="$A/manyfiles"
mkdir -p "$BIG"
i=1
while [ "$i" -le 2000 ]; do
  printf 'file number %04d\n' "$i" > "$BIG/$(printf 'f%04d.txt' "$i")"
  i=$(( i + 1 ))
done

# ---------------------------------------------------------------------------
# 18. Real git repo: 3 commits on main + one extra branch
# ---------------------------------------------------------------------------
# Deterministic identity & dates so the repo is reproducible.
export GIT_AUTHOR_NAME="Maze Builder"      GIT_AUTHOR_EMAIL="maze@example.com"
export GIT_COMMITTER_NAME="Maze Builder"   GIT_COMMITTER_EMAIL="maze@example.com"
(
  cd "$P"
  git -c init.defaultBranch=main init -q
  git config user.name  "Maze Builder"
  git config user.email "maze@example.com"
  git config commit.gpgsign false

  export GIT_AUTHOR_DATE="2025-01-01T00:00:00 +0000" GIT_COMMITTER_DATE="2025-01-01T00:00:00 +0000"
  git add README.md requirements.txt .gitignore 2>/dev/null || git add README.md requirements.txt
  git commit -q -m "Initial commit: project scaffold"

  export GIT_AUTHOR_DATE="2025-02-01T00:00:00 +0000" GIT_COMMITTER_DATE="2025-02-01T00:00:00 +0000"
  git add src
  git commit -q -m "Add source package"

  export GIT_AUTHOR_DATE="2025-03-01T00:00:00 +0000" GIT_COMMITTER_DATE="2025-03-01T00:00:00 +0000"
  git add tests configs
  git commit -q -m "Add tests and configs"

  # extra branch pointing at the second commit
  git branch feature/experiment HEAD~1
)

# ---------------------------------------------------------------------------
# 19. Timestamps — set AFTER all content is written
# ---------------------------------------------------------------------------
# a) Baseline: everything under the tree gets the fixed BASE_DATE — including
#    .git internals, so the freshly-written repo does not pollute the recent
#    find time-tests (-mmin -60 / -mtime -1). (-h touches symlinks themselves.)
find "$ROOT_REAL" -print0 \
  | while IFS= read -r -d '' f; do
      [ "$(realpath -m "$f")" = "$SELF_REAL" ] && continue
      touch -h -d "$BASE_DATE" "$f" 2>/dev/null || true
    done

# b) now-relative mtimes for the find relative-time tests
touch -d "@$TS_30MIN" "$P/logs/train.log"
touch -d "@$TS_3DAY"  "$P/logs/app.log"
touch -d "@$TS_10DAY" "$P/data/raw/recent_events.jsonl"
touch -d "@$TS_45DAY" "$P/logs/old/app.log.1"
touch -d "@$TS_60DAY" "$P/logs/old/app.log.2"
touch -d "@$TS_90DAY" "$P/logs/old/app.log.3"
# scratch/: "older than 30 days" (-mmin +43200). 45 and 90 days clear the
# cutoff by a wide margin; scratch/fresh.txt keeps BASE_DATE and must not match.
touch -d "@$TS_45DAY" "$P/scratch/old_run.log"
touch -d "@$TS_90DAY" "$P/scratch/old_tmp.dat"
# 3 days old: comfortably INSIDE the 30-day cutoff, so it must not be listed.
touch -d "@$TS_3DAY"  "$P/scratch/fresh.txt"

# c) a couple of fixed OLD absolute mtimes (always match -mtime +30 regardless
#    of when the fixture is rebuilt, and give MANIFEST stable values)
touch -d "2024-01-01 00:00:00" "$P/archives/backup_2026-01.tar.gz"
touch -d "2024-03-10 00:00:00" "$P/data/raw/huge_dataset.csv"
# The baseline reference must predate everything in $RESULTS_DIR so that
# `find "$RESULTS_DIR" -newer "$BASELINE_FILE"` returns a non-empty list.
touch -d "2024-01-01 00:00:00" "$P/compare/baseline_checkpoint.txt"
# RESULT_A / RESULT_B are compared on mtime as well as size, so give them two
# clearly different fixed times.
touch -d "2025-05-01 08:30:00" "$P/compare/result_a.txt"
touch -d "2025-06-10 17:45:00" "$P/compare/result_b.txt"

# d) finally lock down the 000 dir (do this LAST so touch above still worked)
chmod 000 "$P/perms/noaccess_dir"

# ---------------------------------------------------------------------------
# 20. bindings.env
# ---------------------------------------------------------------------------
# A few values have to be discovered or computed at build time rather than
# hardcoded, so they are resolved here and interpolated into the heredoc below.

# The real SHA256 of the download fixture. The "does this file match its
# expected checksum?" row is only a test if the expected value is the true one.
DOWNLOAD_SHA256="$(sha256sum < "$P/downloads/dataset.csv" | cut -d' ' -f1)"

# The Windows user profile under /mnt/c, for the READ-ONLY Windows bindings.
# Prefer a profile matching $USER; fall back to any profile that has both
# Downloads and Documents. Left empty on a non-WSL host, in which case the
# Windows bindings below are emitted commented out.
WIN_HOME=""
if [ -d /mnt/c/Users ]; then
  for _cand in "/mnt/c/Users/$USER" /mnt/c/Users/*; do
    case "${_cand##*/}" in
      "All Users"|Default|"Default User"|Public) continue ;;
    esac
    if [ -d "$_cand/Downloads" ] && [ -d "$_cand/Documents" ]; then
      WIN_HOME="$_cand"; break
    fi
  done
fi
if [ -n "$WIN_HOME" ]; then
  echo ">> windows profile: $WIN_HOME (read-only bindings)"
  WIN_DOCS_WINPATH="$(wslpath -w "$WIN_HOME/Documents" 2>/dev/null || true)"
  [ -n "$WIN_DOCS_WINPATH" ] || WIN_DOCS_WINPATH="C:\\Users\\${WIN_HOME##*/}\\Documents"
  WIN_PREFIX=""
else
  echo ">> windows profile: none found under /mnt/c (Windows bindings commented out)" >&2
  WIN_HOME="/mnt/c/Users/<your-windows-user>"
  WIN_DOCS_WINPATH="C:\\Users\\<your-windows-user>\\Documents"
  WIN_PREFIX="# NOT-ON-THIS-HOST: "
fi

cat > "$ROOT_REAL/bindings.env" <<EOF
# bindings.env — placeholder -> real path mappings for the LinuxBuddy test maze
#
# GENERATED by build_maze.sh (section 20). Edit the generator, not this file:
# a rebuild overwrites it.
#
# Source this before verifying generated commands:  source bindings.env
#
# Sections below, in order:
#   1. maze paths ................ exist after a build
#   2. aliases ................... another name for something already bound
#   3. comparison pairs .......... two files that deliberately DIFFER
#   4. write targets ............. intentionally absent; commands create them
#   5. read-only Windows paths ... real /mnt/c, OUTSIDE the maze
#   6. literal values ............ strings and names, not paths
#   7. runtime values ............ not bound here; see runtime_setup.sh

export MAZE_ROOT="$ROOT_REAL"

# ===========================================================================
# 1. MAZE PATHS — these exist after a build
# ===========================================================================

# --- core project locations ---
export PROJECT_DIR="$P"
export SOURCE_DIR="$P/src"
export DATA_DIR="$P/data"
export LOG_DIR="$P/logs"
export LOG_FILE="$P/logs/train.log"
export VENV_DIR="$P/.venv"
export REQUIREMENTS_FILE="$P/requirements.txt"
export PARENT_DIR="$P"
export CONFIG_DIR="$P/configs"
export SCRIPTS_DIR="$P/scripts"
export TEST_DIR="$P/tests"            # unittest discovery needs cwd=\$PROJECT_DIR

# --- data files (varied) ---
export CSV_FILE="$P/data/raw/measurements.csv"
export TSV_FILE="$P/data/raw/table.tsv"
export JSON_FILE="$P/configs/settings.json"
export DATA_FILE="$P/data/raw/sales.csv"
export CONFIG_FILE="$P/configs/config.yaml"
export INVENTORY_FILE="$P/data/inventory.csv"
export TEXT_FILE="$P/data/processed/notes.txt"
export LINUX_FILE="$P/data/linux_native.txt"
export WINDOWS_FILE="$P/data/windows_stub.txt"   # stand-in; see section 5 for real /mnt/c
export BINARY_FILE="$P/data/raw/sample.bin"      # 256 bytes, 0x00..0xff
export JSONL_FILE="$P/data/raw/malformed.jsonl"  # line 3 is deliberately invalid JSON
export LIST_FILE="$P/data/raw/items.txt"         # unsorted, with repeats
export NAMES_FILE="$P/data/raw/names.txt"        # unsorted, mixed case
export CATEGORIES_FILE="$P/data/raw/categories.txt"    # "network" wins, 4 of 8
export EMAIL_LIST="$P/data/raw/emails.txt"             # 3 domains, one repeated
export STATUS_CODES_FILE="$P/data/raw/status_codes.txt" # 200 most common
export INPUT_FILE="$P/data/raw/list_with_blanks.txt"   # 3 of 8 lines are blank
export OLD_FILE="$P/data/raw/old_notes.txt"            # the \$NEW_FILE rename source

# --- scripts / tools ---
export SCRIPT_FILE="$P/scripts/good_script.sh"
export TOOLS_DIR="$P/tools"
export TRAIN_SCRIPT="$P/scripts/train_stub.py"   # self-contained; see note A

# --- configs that are read, sourced or chmod-ed ---
export ENV_FILE="$P/configs/runtime.env"         # safe to source; see note B
export SECRET_FILE="$P/configs/credentials.txt"  # starts 644 so chmod 600 shows

# --- archives & backup ---
export ARCHIVE_DIR="$P/archives"
export ARCHIVE_FILE="$P/archives/backup_2026-01.tar.gz"
export ZIP_FILE="$P/archives/release.zip"        # see release.zip.MISSING.txt if zip absent at build
export GZIP_FILE="$P/archives/data.gz"
export BACKUP_DIR="$P/backups"
export MANIFEST_FILE="$P/backups/MANIFEST.sha256"  # verifies the 3 files beside it

# --- models / runs / results / reports ---
export MODEL_FILE="$P/models/model.pkl"
export RUNS_DIR="$P/runs"
export RUN_DIR="$P/runs/run_001"
export RESULTS_DIR="$P/data/processed"
export REPORT_FILE="$P/data/processed/summary_report.md"

# --- directories with a specific property the rows test for ---
export PHOTO_DIR="$P/photos"        # .jpg + .JPG + nested .jpg; -iname matters
export SHARED_DIR="$P/shared"       # all files owned by \$(id -un); see note C
export SCRATCH_DIR="$P/scratch"     # 2 files >30d old, 1 fresh
export TEMP_DIR="$P/tmp"            # 2 *.tmp at depth 1, 1 deeper, 1 non-tmp

# --- copy / move sources ---
export ORIGINAL_FILE="$P/data/raw/sales.csv"
export SOURCE_FILE="$P/data/raw/sales.csv"
export TARGET_DIR="$P/output"

# --- existing output / export locations ---
export OUTPUT_DIR="$P/output"
export STATUS_FILE="$P/logs/status.txt"
export EXPORT_DIR="$P/exports"
export EXPORT_FILE="$P/exports/export_2025-06.csv"   # 7 lines, one of them blank
export DOWNLOAD_FILE="$P/downloads/dataset.csv"

# --- links & private ---
export LINK_PATH="$ROOT_REAL/awkward/link_to_project_src"
export PRIVATE_DIR="$P/private"

# --- awkward playground ---
export AWKWARD_DIR="$ROOT_REAL/awkward"

# ===========================================================================
# 2. ALIASES — another name for something already bound above.
#    No duplicate files are created; these are references.
# ===========================================================================
export PROJECT_ROOT="\$PROJECT_DIR"
export WORKSPACE_DIR="\$PROJECT_DIR"
export LINUX_DIR="\$PROJECT_DIR"        # explorer.exe target; a Linux path by design
export EXPERIMENT_DIR="\$RUN_DIR"
export OLD_RUNS_DIR="\$RUNS_DIR"
export ARTIFACT_FILE="\$MODEL_FILE"
export CHECKPOINT_FILE="\$MODEL_FILE"
export NOTES_FILE="\$TEXT_FILE"

# ===========================================================================
# 3. COMPARISON PAIRS — project/compare/
#    Each pair DIFFERS deliberately; see build_maze.sh section 14b for what
#    the difference is in each case. Identical files would make these rows
#    pass without comparing anything.
#
#    Exit codes: for inputs that differ, \`cmp -s a b && echo identical\`
#    prints nothing and exits 1, and \`diff -u a b\` exits 1. That is the
#    correct outcome here — judge these rows on output, not exit status.
# ===========================================================================
export FILE_A="$P/compare/export_a.csv"          # one cell differs
export FILE_B="$P/compare/export_b.csv"
export OLD_CONFIG="$P/compare/config_old.yaml"   # 1 edited, 1 removed, 1 added
export NEW_CONFIG="$P/compare/config_new.yaml"
export JSON_A="$P/compare/settings_v1.json"      # top-level key sets differ
export JSON_B="$P/compare/settings_v2.json"
export LOG_A="$P/compare/log_a.log"              # each ISO-sorted, interleaving
export LOG_B="$P/compare/log_b.log"
export LIST_A="$P/compare/ids_a.txt"             # 3 ids in common
export LIST_B="$P/compare/ids_b.txt"
export COMPLETED_IDS="$P/compare/completed_ids.txt"   # failed-not-completed = 2
export FAILED_IDS="$P/compare/failed_ids.txt"
export RUN_A_STATUS="$P/compare/run_a_status.txt"     # "timeout" disappeared
export RUN_B_STATUS="$P/compare/run_b_status.txt"
export RESULT_A="$P/compare/result_a.txt"        # different size AND mtime
export RESULT_B="$P/compare/result_b.txt"
export FIRST_FILE="$P/compare/dataset_small.csv" # 4 KiB vs 64 KiB
export SECOND_FILE="$P/compare/dataset_large.csv"
export DEST_FILE="$P/compare/export_current.csv" # current vs proposed export
export NEW_EXPORT="$P/compare/export_proposed.csv"
export BACKUP_A="$P/compare/backup_a.tar.gz"     # b.txt differs inside
export BACKUP_B="$P/compare/backup_b.tar.gz"
export ARCHIVE_A="\$BACKUP_A"   # alias of the pair above (kept here for order)
export ARCHIVE_B="\$BACKUP_B"
export VENV_A="$P/compare/venv_a"   # bin/python answers \`-m pip freeze\` only
export VENV_B="$P/compare/venv_b"   # see note D
export BASELINE_FILE="$P/compare/baseline_checkpoint.txt"  # mtime 2024-01-01

# ===========================================================================
# 4. WRITE TARGETS — intentionally ABSENT. The command under test creates
#    them. Their parent directory exists; the leaf does not.
# ===========================================================================
export COPIED_FILE="$P/output/sales_copy.csv"
export TARGET_FILE="$P/output/target.txt"
export OUTPUT_FILE="$P/output/result.txt"
export BACKUP_FILE="$P/backups/config.yaml.bak"
export CLEAN_FILE="$P/output/list_clean.txt"
export DEST_DIR="$P/output/src_copy"
export MATCHES_FILE="$P/output/failed_lines.txt"
export MERGED_LOG="$P/output/merged.log"
export FREEZE_A="$P/output/freeze_a.txt"
export FREEZE_B="$P/output/freeze_b.txt"
export IMPORT_TIMINGS_FILE="$P/output/importtime.txt"
export MANIFEST_OUT="$P/output/archive_members.txt"
export OUTPUT_SCRIPT="$P/output/script_lf.sh"
export RESULT_FILE="$P/output/results_new.txt"
export SNAPSHOT_FILE="$P/output/top_cpu.txt"
export NEW_FILE="$P/data/raw/notes.txt"          # the \$OLD_FILE rename target
export RUN_LOG="$P/logs/run_history.log"
export TRAIN_LOG="$P/logs/train_run.log"         # NOT \$LOG_FILE; see note E
export WHEEL_DIR="$P/wheels"                     # pip download -d; needs network
export LINUX_TARGET_DIR="$P/output/windows_import"

# ===========================================================================
# 5. READ-ONLY WINDOWS PATHS — real /mnt/c, OUTSIDE the maze.
#
#    READ-ONLY. Every binding in this section is a real directory belonging
#    to the Windows user, not a disposable fixture: build_maze.sh never
#    creates, touches or wipes anything here, and no write target is ever
#    bound to /mnt/c. A row that writes to one of these must be redirected
#    to a maze path or skipped — see note F for the one row that does.
# ===========================================================================
${WIN_PREFIX}export DOWNLOADS_DIR="$WIN_HOME/Downloads"             # READ-ONLY
${WIN_PREFIX}export WINDOWS_DOWNLOADS="\$DOWNLOADS_DIR"             # READ-ONLY (alias)
${WIN_PREFIX}export WINDOWS_DOCUMENTS_DIR="$WIN_HOME/Documents"     # READ-ONLY — see note F
${WIN_PREFIX}export WINDOWS_DATA_DIR="$WIN_HOME/Documents"          # READ-ONLY (copy source)
${WIN_PREFIX}export LINUX_PATH="$WIN_HOME"                          # READ-ONLY; wslpath -w input
${WIN_PREFIX}export WINDOWS_PATH="$WIN_DOCS_WINPATH"                # a Windows-FORM string, not a POSIX path

# ===========================================================================
# 6. LITERAL VALUES — strings and names, not paths.
# ===========================================================================
export PROJECT_NAME="project"          # tar member name; see note G
export DATA_DIR_NAME="data"            # tar -C "\$PARENT_DIR" "\$DATA_DIR_NAME"
export ARCHIVE_MEMBER="README.md"      # a real member of \$ARCHIVE_FILE
export COLUMN_NAME="note"              # column of \$CSV_FILE; 192 rows blank it
export MODULE_NAME="src.cli"           # python3 -m; needs cwd=\$PROJECT_DIR
export BRANCH_NAME="feature/binding-check"   # must NOT already exist; see note H
export FILE_NAME="measurements.csv"    # a bare filename, for the clipboard row
export JOB_PATTERN="sleep 300"         # matches the runtime_setup.sh helper only
export RUN_MODE="debug"                # arbitrary one-off env value
export EXPECTED_SHA256="$DOWNLOAD_SHA256"   # the true checksum of \$DOWNLOAD_FILE

# ===========================================================================
# 7. RUNTIME VALUES — deliberately NOT bound here.
#
#    \$PID, \$PORT and \$GPU_ID describe live processes and hardware, so they
#    cannot be baked into a fixture. Start the helper processes and export
#    them with:
#
#        source runtime_setup.sh      # exports PID, PORT, and GPU_ID if any
#        runtime_teardown             # stops them again
#
#    \$GPU_ID is exported only when nvidia-smi is present; on a host without
#    an NVIDIA GPU it is left unset on purpose, so a row that needs it fails
#    loudly instead of silently testing device "".
# ===========================================================================
# PID=<runtime>      see runtime_setup.sh
# PORT=<runtime>     see runtime_setup.sh
# GPU_ID=<runtime>   see runtime_setup.sh (only if nvidia-smi exists)

# ===========================================================================
# NOTES
# ===========================================================================
# A. TRAIN_SCRIPT is scripts/train_stub.py, not src/train.py: src/train.py
#    does \`from src.model import ...\`, so \`python3 src/train.py\` fails on
#    sys.path and \`python3 -m src.train\` only works from \$PROJECT_DIR. The
#    rows that use TRAIN_SCRIPT test output capture and env passing, so the
#    script has to run anywhere, deterministically, and exit 0.
# B. ENV_FILE is configs/runtime.env, not configs/.env.example: .env.example
#    sets DATA_DIR=./data/raw, and \`set -a && source\` would overwrite the
#    bound \$DATA_DIR in the caller's shell, breaking every later row that
#    uses it. runtime.env defines only names no binding uses.
# C. SHARED_DIR cannot be made discriminating without root: every file in it
#    is owned by the build user, so \`find -user "\$(id -un)"\` matches all of
#    them. The row still verifies the command, not the selectivity.
# D. VENV_A/VENV_B are skeletons whose bin/python implements \`-m pip freeze\`
#    and nothing else. Two real venvs cannot be built by this script (it is
#    offline and must be byte-reproducible; pip is neither). The pip-freeze
#    comparison row is therefore fully runnable; anything else in those
#    "venvs" is not.
# E. TRAIN_LOG is NOT an alias of LOG_FILE. Its row redirects into it
#    (\`python3 -u "\$TRAIN_SCRIPT" > "\$TRAIN_LOG" 2>&1\`), and LOG_FILE is the
#    2000-line train.log fixture that several other rows grep. Aliasing them
#    would let one row truncate another row's fixture mid-session.
# F. The "send my backup to Windows Documents" row copies INTO
#    \$WINDOWS_DOCUMENTS_DIR. That is a real Windows directory and this file
#    binds it read-only, so that row must not be executed as written — point
#    it at a maze path or skip it.
# G. PROJECT_NAME="project" is the project folder's real name, but its row
#    does \`tar -C "\$PARENT_DIR" -- "\$PROJECT_NAME"\`, which needs PARENT_DIR
#    to be the project's PARENT (\$MAZE_ROOT). Another row does
#    \`tar -C "\$PARENT_DIR" "\$DATA_DIR_NAME"\`, which needs PARENT_DIR to be
#    the project dir itself. One variable, two incompatible meanings — the
#    CSV has to change for both to work. PARENT_DIR is left as the project
#    dir, so the DATA_DIR_NAME row works and the PROJECT_NAME one does not.
# H. BRANCH_NAME is created by \`git switch -c\`, so the row succeeds once per
#    build. Rebuild the maze (or delete the branch) before re-running it.
# I. WINDOWS_DATA_DIR is the Windows Documents folder because it is real,
#    read-only and small. On a profile where Documents holds only the usual
#    My Music / My Pictures / My Videos links, the "copy my training data
#    from C: into Linux home" row copies those links and no actual files —
#    the command is exercised, but no bytes move. Point it at a Windows
#    folder that does hold a few files if that row needs real content;
#    do NOT point it at Downloads, which is tens of gigabytes.
EOF

# ---------------------------------------------------------------------------
# 20b. runtime_setup.sh — the three values a fixture cannot hold
# ---------------------------------------------------------------------------
# Generated, like bindings.env, so that section 2's wipe does not remove it.
cat > "$ROOT_REAL/runtime_setup.sh" <<'EOF'
#!/usr/bin/env bash
#
# runtime_setup.sh — start the helper processes that $PID, $PORT and $GPU_ID
# refer to, and export those three values.
#
# GENERATED by build_maze.sh (section 20b). Edit the generator, not this file.
#
#   source runtime_setup.sh      start the helpers, export PID/PORT/GPU_ID
#   runtime_teardown             stop them again (defined by sourcing)
#   ./runtime_setup.sh stop      stop them from another shell, via the pid file
#
# $PID and $PORT cannot live in bindings.env: a PID is only meaningful while
# that exact process is alive, and a port has to be one that is actually free
# on this host at this moment. Both are therefore produced here and exported
# into the caller's shell, which is why this file is SOURCED, not executed.
#
# Started helpers:
#   sleep 300                      -> $PID   (also what $JOB_PATTERN matches)
#   python3 -m http.server $PORT   -> $PORT  (bound to 127.0.0.1, serving
#                                             $RESULTS_DIR)

_rt_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
_rt_pidfile="$_rt_root/.runtime_pids"

runtime_teardown() {
  local f="${_rt_pidfile:-$_rt_root/.runtime_pids}"
  if [ -f "$f" ]; then
    local pid
    while read -r pid; do
      [ -n "$pid" ] || continue
      kill "$pid" 2>/dev/null && echo "   stopped pid $pid"
    done < "$f"
    rm -f "$f"
  fi
  unset PID PORT
  echo ">> runtime helpers stopped"
}

# Standalone `./runtime_setup.sh stop` — works without sourcing.
if [ "${1:-}" = "stop" ]; then
  runtime_teardown
  exit 0
fi

# Refuse to double-start: two http.servers would leave $PORT ambiguous.
if [ -f "$_rt_pidfile" ]; then
  echo "!! runtime helpers already running (see $_rt_pidfile)." >&2
  echo "!! run 'runtime_teardown' first, or './runtime_setup.sh stop'." >&2
  return 1 2>/dev/null || exit 1
fi

# --- PORT: ask the kernel for a free one, then serve on it ------------------
# Binding port 0 and reading back the assignment is the only reliable way to
# get a free port. There is an unavoidable gap between releasing it and
# http.server claiming it; on a busy host, re-run if the server did not come up.
if ! command -v python3 >/dev/null 2>&1; then
  echo "!! python3 not found; cannot start the http.server helper." >&2
  return 1 2>/dev/null || exit 1
fi
PORT="$(python3 -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()')"
export PORT

_rt_serve_dir="${RESULTS_DIR:-$_rt_root}"
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$_rt_serve_dir" \
  > "$_rt_root/.runtime_http.log" 2>&1 &
_rt_http_pid=$!

# --- PID: the long-lived placeholder process ------------------------------
# A plain `sleep 300`, which is also what $JOB_PATTERN is bound to match.
sleep 300 &
PID=$!
export PID

printf '%s\n%s\n' "$PID" "$_rt_http_pid" > "$_rt_pidfile"

# --- GPU_ID: only if there is actually a GPU ------------------------------
# Left unset when nvidia-smi is absent, so a row that needs it fails loudly
# rather than quietly running against device "".
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_ID="$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | head -n 1 | tr -d ' \r')"
  if [ -n "$GPU_ID" ]; then
    export GPU_ID
  else
    unset GPU_ID
    echo ">> nvidia-smi present but reported no GPU; GPU_ID left unset" >&2
  fi
else
  unset GPU_ID
  echo ">> no nvidia-smi on this host; GPU_ID left unset (by design)" >&2
fi

# --- report ---------------------------------------------------------------
sleep 1   # give http.server a moment to bind before anyone probes $PORT
echo ">> PID=$PID            (sleep 300; matches \$JOB_PATTERN)"
echo ">> PORT=$PORT          (http.server on 127.0.0.1, serving $_rt_serve_dir)"
if [ -n "${GPU_ID:-}" ]; then
  echo ">> GPU_ID=$GPU_ID"
fi
echo ">> stop with: runtime_teardown"
EOF
chmod 755 "$ROOT_REAL/runtime_setup.sh"

# ---------------------------------------------------------------------------
# 21. MANIFEST.txt — full tree, sizes & mtimes, for diffing two builds
# ---------------------------------------------------------------------------
# Excludes: .git internals, build_maze.sh, bindings.env, runtime_setup.sh,
# the runtime pid/log droppings, and MANIFEST.txt itself.
# now-relative files show mtime "RELATIVE" so two builds stay byte-identical.
MAN="$ROOT_REAL/MANIFEST.txt"

# associative set of relative paths with now-based mtimes
declare -A RELSET
for rp in "${REL_PATHS[@]}"; do RELSET["$rp"]=1; done

{
  echo "# LinuxBuddy maze MANIFEST"
  echo "# root: \$MAZE_ROOT (paths below are relative to it)"
  echo "# columns: TYPE  PERMS  SIZE  MTIME  PATH"
  echo "# excludes: .git/ internals, build_maze.sh, bindings.env, runtime_setup.sh, MANIFEST.txt"
  echo "# MTIME == RELATIVE marks intentionally now-relative files (see build_maze.sh)"
  echo "#"
} > "$MAN"

# Walk the tree deterministically. Prune .git. Skip meta files.
# `2>/dev/null || true`: the 000 perms/noaccess_dir is listed (find prints the
# dir before it fails to descend); its inaccessible contents are omitted.
{ find "$ROOT_REAL" -name .git -prune -o -print0 2>/dev/null || true; } \
  | LC_ALL=C sort -z \
  | while IFS= read -r -d '' f; do
      rel="${f#$ROOT_REAL/}"
      [ "$f" = "$ROOT_REAL" ] && continue
      case "$rel" in
        build_maze.sh|bindings.env|runtime_setup.sh|MANIFEST.txt) continue ;;
        .runtime_pids|.runtime_http.log) continue ;;
      esac
      # type
      if   [ -L "$f" ]; then t="l"
      elif [ -d "$f" ]; then t="d"
      else                   t="f"
      fi
      perms="$(stat -c '%A' "$f")"
      size="$(stat -c '%s' "$f")"
      if [ -n "${RELSET[$rel]:-}" ]; then
        mt="RELATIVE"
      else
        mt="$(date -u -d "@$(stat -c '%Y' "$f")" '+%Y-%m-%dT%H:%M:%SZ')"
      fi
      printf '%s  %s  %10s  %-20s  %s\n' "$t" "$perms" "$size" "$mt" "$rel" >> "$MAN"
    done

# ---------------------------------------------------------------------------
# 22. Done
# ---------------------------------------------------------------------------
echo ">> build complete"
echo ">> bindings: $ROOT_REAL/bindings.env"
echo ">> runtime:   $ROOT_REAL/runtime_setup.sh  (source it for PID/PORT/GPU_ID)"
echo ">> manifest: $MAN"
