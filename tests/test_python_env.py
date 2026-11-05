"""Task 14 tests — domain: python_environments. Read intents work anywhere;
run_script/check_syntax write and are gated. Most of this domain is deferred
(network / shell-state / long-running), so the built surface is small (5).
"""
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile, risk_ops
from linuxbuddy.render import to_shell
from linuxbuddy import gate


def test_python_version_is_and_chain():
    f = parse("what python version do i have")
    assert f.intent == "python_version"
    plan = compile(f)
    assert plan == [["python3", "--version"], ["command", "-v", "python3"]]
    assert to_shell(plan) == "python3 --version && command -v python3"


def test_where_python():
    f = parse("where does python live")
    assert f.intent == "where_python"
    assert compile(f) == ["command", "-v", "python3"]


def test_check_package():
    f = parse("is pandas available")
    assert f.intent == "check_package"
    assert f.slots["pkg"] == "pandas"
    argv = compile(f)
    assert argv == ["python3", "-c",
                    'import importlib.util as u; print(u.find_spec("pandas") is not None)']


def test_check_package_rendered_round_trips():
    # the -c code is one argv element and survives shlex round-trip unchanged
    import shlex
    f = parse("does numpy import")
    assert f.intent == "check_package" and f.slots["pkg"] == "numpy"
    rendered = to_shell(compile(f))
    assert shlex.split(rendered) == compile(f)


def test_run_script():
    f = parse("run train.py")
    assert f.intent == "run_script"
    assert f.slots["path"] == "train.py"
    assert compile(f) == ["python3", "--", "train.py"]


def test_check_syntax():
    f = parse("check main.py for syntax errors")
    assert f.intent == "check_syntax"
    assert f.slots["path"] == "main.py"
    assert compile(f) == ["python3", "-m", "py_compile", "--", "main.py"]


# --- deferred → abstain ---

def test_pip_install_abstains():
    assert parse("install the requirements") is None


def test_venv_activate_abstains():
    assert parse("activate the venv") is None


# --- risk_ops / gating ---

def test_read_intents_read_only():
    for intent in ("python_version", "where_python", "check_package"):
        assert risk_ops(intent) == ["read"]


def test_write_intents_gated():
    for intent in ("run_script", "check_syntax"):
        assert risk_ops(intent) == ["write"]
        assert gate.check(risk_ops(intent), "/tmp") is not None


# --- regression (earlier domains still route) ---

def test_prior_domains_regression():
    assert parse("csv files over 100 megs").intent == "find_by_size"
    assert parse("show errors in train.log").intent == "search_in_file"
    assert parse("what's inside backup.tar.gz").intent == "list_archive"
    assert parse("how big is the data folder").intent == "disk_usage"
