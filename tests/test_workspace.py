"""Task 16 tests — domain: workspace_and_shell (scoped multi-step).

Navigation/shell reads work anywhere; make_dir and the setup_project recipe
write and are gated. setup_project is ONE fixed recipe, not general compound.
"""
import os

from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile, risk_ops
from linuxbuddy.render import to_shell
from linuxbuddy import gate


def test_where_am_i():
    assert parse("where am I").intent == "where_am_i"
    assert compile(parse("where am I")) == ["pwd"]


def test_go_home_resolves_tilde():
    f = parse("take me home")
    assert f.intent == "go_home"
    # ~ is resolved at compile — no bare ~ is emitted
    argv = compile(f)
    assert argv[0] == "cd" and argv[1] == os.path.expanduser("~")
    assert "~" not in to_shell(argv)


def test_goto():
    f = parse("go to the src folder")
    assert f.intent == "goto"
    assert f.slots["path"] == "src"
    assert compile(f) == ["cd", "--", "src"]


def test_check_installed():
    f = parse("do I have git installed")
    assert f.intent == "check_installed"
    assert f.slots["tool"] == "git"
    assert compile(f) == ["command", "-v", "--", "git"]


def test_who_am_i_is_and_chain():
    f = parse("what account am I using")
    assert f.intent == "who_am_i"
    assert compile(f) == [["whoami"], ["id", "-nG"]]
    assert to_shell(compile(f)) == "whoami && id -nG"


def test_which_shell_resolves_env():
    f = parse("which shell is this")
    assert f.intent == "which_shell"
    argv = compile(f)
    # KB keeps '%s\n' as a literal backslash-n (printf expands it at runtime)
    assert argv[:2] == ["printf", "%s\\n"]
    assert "$SHELL" not in argv[2]  # resolved at compile


def test_make_dir_gated():
    f = parse("make an outputs folder")
    assert f.intent == "make_dir"
    assert f.slots["path"] == "outputs"
    assert compile(f) == ["mkdir", "-p", "--", "outputs"]
    assert risk_ops("make_dir") == ["write"]
    assert gate.check(risk_ops("make_dir"), "/tmp") is not None


def test_setup_project_recipe():
    f = parse("set up a project folder called demo")
    assert f.intent == "setup_project"
    assert f.slots["name"] == "demo"
    plan = compile(f)
    assert plan == [["mkdir", "-p", "--", "demo/data", "demo/reports"],
                    ["cd", "--", "demo"]]
    assert to_shell(plan) == "mkdir -p -- demo/data demo/reports && cd -- demo"
    assert risk_ops("setup_project") == ["write"]
    assert gate.check(risk_ops("setup_project"), "/tmp") is not None


def test_compound_abstains():
    assert parse("export the path then cd and show me python") is None


# --- regression (earlier domains still route) ---

def test_prior_domains_regression():
    assert parse("csv files over 100 megs").intent == "find_by_size"
    assert parse("show errors in train.log").intent == "search_in_file"
    assert parse("is pandas available").intent == "check_package"
    assert parse("how big is the data folder").intent == "disk_usage"
    assert parse("kill process 4821").intent == "kill_pid"
