"""Task 17 tests — domain: wsl_interop. All read-only. Clean single-level
intents are built; nested $(...) navigation is deferred (abstain).
"""
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile, risk_ops
from linuxbuddy.render import to_shell


def test_open_explorer():
    f = parse("open this folder in explorer")
    assert f.intent == "open_explorer"
    assert compile(f) == ["explorer.exe", "."]


def test_goto_cdrive():
    f = parse("take me to the C drive")
    assert f.intent == "goto_cdrive"
    assert compile(f) == ["cd", "/mnt/c"]


def test_path_to_linux():
    f = parse("convert C:\\Users\\me to a linux path")
    assert f.intent == "path_to_linux"
    assert f.slots["winpath"] == "C:\\Users\\me"
    assert compile(f) == ["wslpath", "-u", "--", "C:\\Users\\me"]


def test_path_to_windows():
    f = parse("how would /home/me/x look on windows")
    assert f.intent == "path_to_windows"
    assert f.slots["path"] == "/home/me/x"
    assert compile(f) == ["wslpath", "-w", "--", "/home/me/x"]


def test_copy_to_clipboard_is_pipe():
    f = parse("put my path on the windows clipboard")
    assert f.intent == "copy_to_clipboard"
    plan = compile(f)
    assert plan == [["pwd"], ["clip.exe"]]
    assert to_shell(plan) == "pwd | clip.exe"


def test_cdrive_space():
    f = parse("free space on the C drive")
    assert f.intent == "cdrive_space"
    assert compile(f) == ["df", "-h", "/mnt/c"]


def test_windows_user_folder_resolves():
    # Task 27 (E117/E118): a Windows user folder → cd /mnt/c/Users/$USER/<F>.
    # ($USER is emitted unquoted so the shell expands it; the user edits if their
    # Windows account name differs.) Previously deferred as needing nested $().
    f = parse("take me to my windows downloads")
    assert f.intent == "goto" and str(f.slots["path"]) == "/mnt/c/Users/$USER/Downloads"


def test_nested_substitution_abstains():
    # A genuine nested case (windows user/profile folder) still defers.
    assert parse("take me to my windows user folder") is None


def test_all_read_only():
    for intent in ("open_explorer", "goto_cdrive", "goto_home", "path_to_linux",
                   "path_to_windows", "copy_to_clipboard", "cdrive_space",
                   "home_space"):
        assert risk_ops(intent) == ["read"]


# --- regression (earlier domains still route; wsl doesn't steal nav) ---

def test_prior_domains_regression():
    assert parse("take me home").intent == "go_home"          # workspace, not wsl
    assert parse("go to the src folder").intent == "goto"      # workspace
    assert parse("csv files over 100 megs").intent == "find_by_size"
    assert parse("kill process 4821").intent == "kill_pid"
