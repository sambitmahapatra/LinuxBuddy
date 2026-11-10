"""Task 32 — file-management intents (move/copy/delete/mkdir) + nested navigation.

Part A: every file-management op is destructive-tier → renders the real command,
exits 3, and is maze-gated. Part B: "X inside Y" nested navigation resolves Y to
an ancestor (absolute) or a child dir (relative), else abstains.

Render assertions use the parse→compile→render pipeline directly (sh()); exit
codes and the gate go through the real cli.main.
"""
import pytest

from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell
from linuxbuddy.cli import main


def sh(req):
    return to_shell(compile(parse(req)))


def at_cwd(monkeypatch, path):
    monkeypatch.setattr("linuxbuddy.nlu.os.getcwd", lambda: path)


# ==========================================================================
# Part A — file-management intents (all destructive → exit 3, maze-gated)
# ==========================================================================

@pytest.mark.parametrize("req, cmd", [
    ("move report.txt to docs", "mv -- report.txt docs"),
    ("rename old.txt to new.txt", "mv -- old.txt new.txt"),
    ("put config.yaml in backups", "mv -- config.yaml backups"),
    ("move report.txt into archive", "mv -- report.txt archive"),
])
def test_move_rename_renders_mv(req, cmd):
    assert sh(req) == cmd


def test_move_definite_image_glob():
    # "the image" → an image glob (Raw, emitted unquoted so the shell expands it)
    assert sh("move the image to photos") == "mv -- *.{jpg,png} photos"


@pytest.mark.parametrize("req, cmd", [
    ("copy report.txt to docs", "cp -- report.txt docs"),
    ("make a copy of config.yaml", "cp -- config.yaml config.yaml.bak"),
    ("copy data.csv into backups", "cp -- data.csv backups"),
])
def test_copy_with_and_without_dest(req, cmd):
    assert sh(req) == cmd


@pytest.mark.parametrize("req, cmd", [
    ("delete build.log", "rm -- build.log"),
    ("remove temp.txt", "rm -- temp.txt"),
    ("get rid of output.tmp", "rm -- output.tmp"),
])
def test_delete_renders_rm(req, cmd):
    assert sh(req) == cmd


def test_delete_definite_old_logs():
    assert sh("remove the old logs") == "rm -- *.log"


@pytest.mark.parametrize("req, cmd", [
    ("make a folder logs", "mkdir -p -- logs"),
    ("create a directory src/new", "mkdir -p -- src/new"),
    ("new folder data", "mkdir -p -- data"),
])
def test_mkdir_noun_then_name(req, cmd):
    assert sh(req) == cmd


# ---- exit codes: every file-management op is destructive (exit 3) ----

@pytest.mark.parametrize("req", [
    "move report.txt to docs",
    "copy report.txt to docs",
    "delete build.log",
    "make a folder logs",
])
def test_file_mgmt_exits_three(req, capsys, monkeypatch):
    monkeypatch.setenv("LINUXBUDDY_MODE", "prod")   # lift the gate; check risk
    code = main([req])
    capsys.readouterr()
    assert code == 3


# ---- the containment gate applies to all four ----

@pytest.fixture
def maze(tmp_path, monkeypatch):
    root = tmp_path / "maze"
    (root / "inside").mkdir(parents=True)
    monkeypatch.setenv("LINUXBUDDY_MAZE_ROOT", str(root))
    monkeypatch.setenv("LINUXBUDDY_MODE", "prototype")
    return root


def test_delete_refused_outside_maze(maze, monkeypatch, capsys):
    monkeypatch.chdir("/tmp")
    code = main(["delete build.log"])
    out = capsys.readouterr().out
    assert code == 1 and out == ""        # gate refuses, nothing emitted


def test_delete_allowed_inside_maze(maze, monkeypatch, capsys):
    monkeypatch.chdir(maze / "inside")
    code = main(["delete build.log"])
    out = capsys.readouterr().out
    assert code == 3 and out.strip() == "rm -- build.log"


# ---- destructive with an unclear target must abstain, never guess ----

@pytest.mark.parametrize("req", ["delete everything", "get rid of it", "remove them"])
def test_delete_unclear_target_abstains(req):
    assert parse(req) is None


def test_remove_executable_bit_is_still_chmod_not_rm():
    # "remove the executable bit" is a chmod a-x, NOT a file deletion.
    assert sh("remove the executable bit from run.sh") == "chmod a-x -- run.sh"


# ==========================================================================
# Part B — nested navigation ("X inside Y")
# ==========================================================================

def test_nested_nav_ancestor_absolute(monkeypatch):
    at_cwd(monkeypatch, "/home/sambi/linuxbuddy/some/deep/dir")
    # Y (linuxbuddy) is an ancestor of cwd → resolve its absolute path + X.
    assert sh("go to test_02 inside linuxbuddy") == \
        "cd -- /home/sambi/linuxbuddy/test_02"


def test_nested_nav_ancestor_in_connector(monkeypatch):
    at_cwd(monkeypatch, "/home/sambi/linuxbuddy/project")
    assert sh("take me to src in linuxbuddy") == \
        "cd -- /home/sambi/linuxbuddy/src"


def test_nested_nav_unresolvable_abstains(monkeypatch):
    at_cwd(monkeypatch, "/home/sambi/linuxbuddy")
    # Y is neither an ancestor nor a child dir → don't guess.
    assert parse("go to foo inside nonexistent_zzz_dir") is None


def test_nested_nav_child_relative(monkeypatch, tmp_path):
    (tmp_path / "parentdir" / "kiddir").mkdir(parents=True)
    monkeypatch.setattr("linuxbuddy.nlu.os.getcwd", lambda: str(tmp_path))
    monkeypatch.chdir(tmp_path)   # os.path.isdir checks resolve against cwd
    assert sh("go to kiddir inside parentdir") == "cd -- parentdir/kiddir"


# ---- existing navigation is unregressed ----

@pytest.mark.parametrize("req, cmd", [
    ("take me to the logs folder", "cd -- logs"),
    ("go into src", "cd -- src"),
    ("move into data", "cd -- data"),
])
def test_navigation_unregressed(req, cmd):
    assert sh(req) == cmd
