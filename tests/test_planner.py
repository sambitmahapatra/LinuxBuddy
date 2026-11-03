"""Task 03 tests — planner compile correctness."""
import pytest

from linuxbuddy.nlu import parse, Frame
from linuxbuddy.planner import compile, PlanError
from linuxbuddy.render import to_shell


def test_csv_over_100_megs_exact_command():
    frame = parse("csv files over 100 megs")
    argv = compile(frame)
    assert argv == ["find", ".", "-type", "f", "-name", "*.csv", "-size", "+104857600c"]
    assert to_shell(argv) == "find . -type f -name '*.csv' -size +104857600c"


def test_unresolved_placeholder_raises():
    # base_argv carries {path}; a frame with no path slot leaves it
    # unresolved, which must raise rather than emit a stray placeholder.
    with pytest.raises(PlanError):
        compile(Frame("find_by_size", {}))


def test_home_resolved_to_absolute():
    import os
    home = os.environ.get("HOME") or os.path.expanduser("~")
    argv = compile(Frame("find_by_type", {"path": "$HOME/Downloads", "ext": "csv"}))
    assert argv[1] == home + "/Downloads"
    assert "$HOME" not in argv[1] and "~" not in argv[1]


def test_unknown_intent_raises():
    with pytest.raises(PlanError):
        compile(Frame("no_such_intent", {"path": "."}))
