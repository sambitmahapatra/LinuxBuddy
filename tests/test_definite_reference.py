"""Task 22 tests — typed definite references ("the log", "the backup") resolve
to a shell glob so a command is emitted instead of abstaining. Globs are emitted
UNQUOTED (render.Raw) so the user's shell expands them. Generic references with
no implied type still abstain.
"""
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell, Raw


def test_the_log_resolves_to_glob():
    f = parse("show me the errors in the log")
    assert f.intent == "search_in_file"
    assert f.slots["path"] == "*.log"
    # emitted UNQUOTED so the shell expands it
    assert to_shell(compile(f)) == "grep -niF -- error *.log"


def test_warnings_count_in_the_log():
    f = parse("how many warnings in the log")
    assert f.intent == "count_matches"
    assert to_shell(compile(f)) == "grep -ciF -- warning *.log"


def test_the_backup_tarball_lists():
    f = parse("what's inside the backup tarball")
    assert f.intent == "list_archive"
    assert f.slots["archive"] == "*.tar.gz"
    assert to_shell(compile(f)) == "tar -tf *.tar.gz"


def test_gzipped_archive_integrity():
    f = parse("does the gzipped archive pass its integrity check")
    assert f.intent == "archive_integrity"
    assert to_shell(compile(f)) == "gzip -t -- *.gz"


def test_who_owns_the_config_file():
    f = parse("who owns the config file")
    assert f.intent == "show_owner"
    assert f.slots["path"] == "config.*"
    assert to_shell(compile(f)) == "stat -c %U:%G -- config.*"


def test_run_the_script():
    f = parse("run the script")
    assert f.intent == "run_script"
    assert f.slots["path"] == "*.py"
    assert to_shell(compile(f)) == "python3 -- *.py"


def test_glob_is_raw_and_round_trips():
    f = parse("show errors in the log")
    plan = compile(f)
    # the path element is Raw (unquoted) and the stage still round-trips
    assert any(isinstance(e, Raw) for e in plan)
    import shlex
    assert shlex.split(to_shell(plan)) == [str(e) for e in plan]


def _lb_abstains(request: str) -> bool:
    """True if `lb` abstains end-to-end: exit 1 and nothing on stdout. The op may
    be recognised but have no file, so the abstain happens at compile, not parse."""
    from linuxbuddy.cli import main
    import contextlib, io
    out = io.StringIO()
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out):
        code = main(request.split())
    return code == 1 and out.getvalue() == ""


def test_generic_reference_still_abstains():
    # No implied type → no glob → abstain (the v2-model residual). The op may be
    # recognised but has no file, so it abstains end-to-end at the CLI.
    assert _lb_abstains("sort this list")
    assert _lb_abstains("how big is this file")


def test_concrete_filename_unaffected():
    # a real filename still wins over the glob and stays quoted-safe
    f = parse("show errors in train.log")
    assert f.slots["path"] == "train.log"
    assert "train.log" in to_shell(compile(f))
