"""Task 34 — copy synonyms + no-destination copy (the last manual synonym patch).

"create a copy of X" / "duplicate X" / "make a duplicate of X" / "back up X.ext"
are copy intents, same as "make a copy of X". They used to fall through to the
greedy find/grep fallback (grep stole the all-caps filename stem, e.g.
MANIFEST.txt). All copy variants render the real `cp` → exit 3, maze-gated, and
must agree across the single-turn and session paths.
"""
import contextlib
import io

import pytest

from linuxbuddy import session
from linuxbuddy.session import classify
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell
from linuxbuddy.cli import main


def sh(req):
    return to_shell(compile(parse(req)))


# --------------------------------------------------------------------------
# Single-turn: the new copy cues render `cp`, no find/grep leakage.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("req, cmd", [
    ("create a copy of sales.csv", "cp -- sales.csv sales.csv.bak"),
    ("create a copy of sales.csv in this folder", "cp -- sales.csv sales.csv.bak"),
    ("create a copy of MANIFEST.txt in this folder", "cp -- MANIFEST.txt MANIFEST.txt.bak"),
    ("duplicate report.csv", "cp -- report.csv report.csv.bak"),
    ("make a duplicate of data.csv", "cp -- data.csv data.csv.bak"),
    ("back up config.yaml", "cp -- config.yaml config.yaml.bak"),
    ("make a copy of sales.csv here", "cp -- sales.csv sales.csv.bak"),
])
def test_copy_synonyms_render_cp(req, cmd):
    assert sh(req) == cmd


def test_make_a_copy_still_works(req="make a copy of config.yaml"):
    # Task 25/32 regression guard.
    assert sh(req) == "cp -- config.yaml config.yaml.bak"


def test_copy_to_dest_unchanged():
    assert sh("copy a.txt to b.txt") == "cp -- a.txt b.txt"


# --------------------------------------------------------------------------
# Discovery / search must NOT be captured by the new copy cues.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("req, cmd", [
    ("find all csv files", "find . -name '*.csv'"),
    ("where is settings.json", "find . -name settings.json"),
    ("back up the project", "tar -czf project.tar.gz -C . -- project"),
])
def test_discovery_and_folder_backup_unregressed(req, cmd):
    assert sh(req) == cmd


# --------------------------------------------------------------------------
# Session path agrees: a copy-synonym lead falls back to single-turn.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("req", [
    "create a copy of sales.csv",
    "duplicate report.csv",
    "make a duplicate of data.csv",
    "back up config.yaml",
    "make a copy of config.yaml",
])
def test_copy_synonyms_fall_back_in_session_classify(req):
    assert classify(req, None)[0] == "fallback"
    frame = session.SessionFrame(targets={"name": "*.csv"}, filters={"size": "+100M"})
    assert classify(req, frame)[0] == "fallback"


# --------------------------------------------------------------------------
# End-to-end through cli.main in SESSION mode, inside/outside the maze.
# --------------------------------------------------------------------------

def _run(req):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main([req])
    return rc, buf.getvalue().strip()


@pytest.fixture
def session_maze(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_SESSION", "task34")
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "maze"
    (root / "inside").mkdir(parents=True)
    monkeypatch.setenv("LINUXBUDDY_MAZE_ROOT", str(root))
    monkeypatch.setenv("LINUXBUDDY_MODE", "prototype")
    monkeypatch.chdir(root / "inside")
    session.clear(session.store_key())
    yield root
    session.clear(session.store_key())


@pytest.mark.parametrize("req, cmd", [
    ("create a copy of sales.csv", "cp -- sales.csv sales.csv.bak"),
    ("create a copy of MANIFEST.txt in this folder", "cp -- MANIFEST.txt MANIFEST.txt.bak"),
    ("duplicate report.csv", "cp -- report.csv report.csv.bak"),
])
def test_copy_synonyms_exit_three_in_session_mode(session_maze, req, cmd):
    assert _run(req) == (3, cmd)


def test_copy_refused_outside_maze(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_SESSION", "task34b")
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "maze"
    root.mkdir()
    monkeypatch.setenv("LINUXBUDDY_MAZE_ROOT", str(root))
    monkeypatch.setenv("LINUXBUDDY_MODE", "prototype")
    monkeypatch.chdir(tmp_path)   # OUTSIDE the maze
    session.clear(session.store_key())
    rc, out = _run("create a copy of sales.csv")
    assert rc == 1 and out == ""
    session.clear(session.store_key())
