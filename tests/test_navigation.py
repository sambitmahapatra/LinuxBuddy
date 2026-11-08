"""Task 26 tests — the navigation domain (cd_parent/home/previous/ancestor/
child/absolute/pwd). cwd-aware intents monkeypatch nlu.os.getcwd so the test
does not depend on the real working directory."""
import pytest

from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


def sh(req):
    return to_shell(compile(parse(req)))


def at_cwd(monkeypatch, path):
    monkeypatch.setattr("linuxbuddy.nlu.os.getcwd", lambda: path)


# --- cd_child (E001-E005) ---

@pytest.mark.parametrize("req, d", [
    ("take me to the logs folder", "logs"),   # E001 — NOT the *.log glob
    ("go into src", "src"),                    # E002
    ("enter the data directory", "data"),      # E003
    ("open the src folder", "src"),            # E004 — open folder → cd
    ("move into data", "data"),                # E005
])
def test_cd_child(req, d):
    assert sh(req) == f"cd -- {d}"


def test_E001_no_glob_leak():
    assert "*.log" not in sh("take me to the logs folder")


# --- cd_parent (E006-E011) ---

@pytest.mark.parametrize("req", [
    "take me back", "go up", "up a level",
    "take me to the parent folder",            # E009 — NOT `cd -- parent`
    "go back up one directory",                # E010 — NOT `cd -`
])
def test_cd_parent_one_level(req):
    assert sh(req) == "cd .."


def test_cd_parent_two_levels():
    assert sh("up two levels") == "cd ../.."     # E011


# --- cd_home (E012-E014) ---

@pytest.mark.parametrize("req", ["take me home", "go to my home directory", "home"])
def test_cd_home(req):
    # go_home emits `cd ~`, resolved to the absolute $HOME at compile (invariant #5)
    out = sh(req)
    assert out.startswith("cd ") and ("~" in out or out.endswith(("/home", "home")) or "/" in out)
    assert parse(req).intent == "go_home"


# --- cd_ancestor (E015-E017) ---

def test_cd_ancestor_immediate(monkeypatch):
    at_cwd(monkeypatch, "/a/b/project/logs")
    assert sh("take me to project") == "cd -- /a/b/project"       # E015


def test_cd_ancestor_root_phrase(monkeypatch):
    at_cwd(monkeypatch, "/a/b/project/src")
    assert sh("go back to the project root") == "cd -- /a/b/project"  # E016 (not cd -)


def test_cd_ancestor_grandparent(monkeypatch):
    at_cwd(monkeypatch, "/a/testlinuxbuddy/project/logs")
    assert sh("take me to testlinuxbuddy") == "cd -- /a/testlinuxbuddy"  # E017


# --- cd_absolute (E018-E019) ---

def test_cd_absolute_tmp():
    assert sh("go to /tmp") == "cd -- /tmp"                       # E018


def test_cd_absolute_full_path():
    assert sh("take me to /mnt/c/Users") == "cd -- /mnt/c/Users"  # E019 — whole path


# --- cd_previous (E020) ---

def test_cd_previous():
    assert sh("go back to where i was") == "cd -"                 # E020


# --- pwd (E021-E023) ---

@pytest.mark.parametrize("req", ["where am i", "what folder am i in", "show my current directory"])
def test_pwd(req):
    assert sh(req) == "pwd"


# --- collisions: directional cues must not steal non-navigation ---

def test_back_up_the_data_is_not_cd():
    f = parse("back up the project")
    assert f is None or f.intent not in ("cd_parent", "go_back", "goto")


def test_open_file_is_not_cd():
    f = parse("open config.yaml")
    assert f is None or f.intent != "goto"
