"""Task 33 — file-management verbs must win over `find` in the SESSION path.

Regression guard for the Task-32 bug that only showed up in the real widget:
multi-turn mode is opt-in via ``$LINUXBUDDY_SESSION`` (the shell widget exports
it), and in that path ``session.classify`` treated ANY request carrying a
filename extension as a new ``find``-by-type query — so "move report.csv to
archive" emitted ``find . -name '*.csv'`` (exit 0) instead of ``mv -- …``
(exit 3). The single-turn router already routed these correctly; only the
session layer hijacked them. These tests pin the session path to the same
behaviour as single-turn.
"""
import contextlib
import io

import pytest

from linuxbuddy import session
from linuxbuddy.session import classify
from linuxbuddy.cli import main


# --------------------------------------------------------------------------
# classify() — a file-op primary verb is NOT a find query; it falls back to
# the v1 single-turn path (which routes it to file_management correctly).
# --------------------------------------------------------------------------

@pytest.mark.parametrize("req", [
    "move report.csv to archive",
    "delete old.log",
    "copy requirements.txt to archives",
    "rename a.txt to b.txt",
    "get rid of output.tmp",
    "put config.yaml in backups",
    "make a copy of config.yaml",
    "rm build.log",
    "remove the executable bit from run.sh",   # chmod in single-turn, not find
])
def test_fileop_verbs_fall_back_not_hijacked_to_find(req):
    # No frame and (critically) WITH a frame present: a file-op verb never
    # becomes a new/refine/operate on a running find query.
    assert classify(req, None)[0] == "fallback"
    frame = session.SessionFrame(targets={"name": "*.csv"}, filters={"size": "+100M"})
    assert classify(req, frame)[0] == "fallback"


@pytest.mark.parametrize("req", [
    "find all csv files",
    "find CSV files larger than 100MB",
    "where is settings.json",
    "locate train.py",
    "list the csv files",
    "how many csv files",
    "recently modified logs",
])
def test_discovery_verbs_unregressed(req):
    # Discovery requests must NOT be swept into the file-op fallback guard —
    # they still start/replace a session find query ("new").
    assert classify(req, None)[0] == "new"


def test_refine_and_operate_still_work_with_frame():
    frame = session.SessionFrame(targets={"name": "*.csv"}, filters={"size": "+100M"})
    assert classify("only the ones modified yesterday", frame)[0] == "refine"
    assert classify("show the biggest one", frame)[0] == "operate"


# --------------------------------------------------------------------------
# End-to-end through the real CLI in SESSION mode (the path the widget uses).
# --------------------------------------------------------------------------

def _run(req):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main([req])
    return rc, buf.getvalue().strip()


@pytest.fixture
def session_maze(monkeypatch, tmp_path):
    """Session mode (LINUXBUDDY_SESSION set) + an isolated cache + a maze root,
    cwd placed INSIDE the maze so destructive ops are allowed (exit 3)."""
    monkeypatch.setenv("LINUXBUDDY_SESSION", "task33")
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
    ("move report.csv to archive", "mv -- report.csv archive"),
    ("delete old.log", "rm -- old.log"),
    ("copy requirements.txt to archives", "cp -- requirements.txt archives"),
    ("rename a.txt to b.txt", "mv -- a.txt b.txt"),
])
def test_fileops_emit_destructive_in_session_mode(session_maze, req, cmd):
    rc, out = _run(req)
    assert (rc, out) == (3, cmd)


@pytest.mark.parametrize("req, cmd", [
    ("make a folder photos", "mkdir -p -- photos"),
    # "logs" looks like a .log type — must still be a mkdir, not a find.
    ("make a folder logs", "mkdir -p -- logs"),
    ("create a directory src/new", "mkdir -p -- src/new"),
])
def test_mkdir_unchanged_in_session_mode(session_maze, req, cmd):
    rc, out = _run(req)
    assert (rc, out) == (3, cmd)


def test_backup_copy_still_works_in_session_mode(session_maze):
    rc, out = _run("make a copy of config.yaml")
    assert (rc, out) == (3, "cp -- config.yaml config.yaml.bak")


def test_fileop_refused_outside_maze_in_session_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_SESSION", "task33b")
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "maze"
    root.mkdir()
    monkeypatch.setenv("LINUXBUDDY_MAZE_ROOT", str(root))
    monkeypatch.setenv("LINUXBUDDY_MODE", "prototype")
    monkeypatch.chdir(tmp_path)   # OUTSIDE the maze
    session.clear(session.store_key())
    rc, out = _run("delete something.txt")
    assert rc == 1 and out == ""   # gate refuses, nothing emitted
    session.clear(session.store_key())


# --------------------------------------------------------------------------
# Regression: discovery + the multi-turn chain are untouched by the guard.
# --------------------------------------------------------------------------

@pytest.fixture
def session_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_SESSION", "task33chain")
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    session.clear(session.store_key())
    yield
    session.clear(session.store_key())


def test_discovery_still_finds_in_session_mode(session_mode):
    rc, out = _run("find all csv files")
    assert (rc, out) == (0, "find . -name '*.csv'")


def test_three_turn_chain_still_accumulates(session_mode):
    rc1, c1 = _run("find CSV files larger than 100MB")
    rc2, c2 = _run("only the ones modified yesterday")
    rc3, c3 = _run("show the biggest one")
    assert (rc1, c1) == (0, "find . -name '*.csv' -size +100M")
    assert (rc2, c2) == (0, "find . -name '*.csv' -size +100M -daystart -mtime 1")
    assert (rc3, c3) == (
        0,
        "find . -name '*.csv' -size +100M -daystart -mtime 1 "
        "-printf '%s\\t%p\\n' | sort -rn | head -1",
    )
