"""Task 19 tests — find_largest ("biggest files"). Read-only, no threshold:
sort by size, show the top. 3-stage pipe (find | sort | head).
"""
import shlex

from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell, Stages


def test_biggest_files_here():
    f = parse("show me the biggest files here")
    assert f.intent == "find_largest"
    assert f.slots["path"] == "."
    assert f.slots["count"] == 10


def test_largest_in_data():
    f = parse("largest files in data")
    assert f.intent == "find_largest"
    assert f.slots["path"] == "data"


def test_top_n_files_by_size():
    f = parse("top 2 files by size")
    assert f.intent == "find_largest"
    assert f.slots["count"] == 2


def test_most_space():
    assert parse("what's taking up the most space").intent == "find_largest"


def test_files_over_threshold_unchanged():
    # a real threshold is still find_by_size
    assert parse("files over 100mb").intent == "find_by_size"


def test_find_largest_is_three_stage_pipe():
    f = parse("show me the biggest files here")
    plan = compile(f)
    assert isinstance(plan, Stages) and plan.op == "|"
    assert plan == [["find", ".", "-type", "f", "-printf", "%s\\t%p\\n"],
                    ["sort", "-rn"],
                    ["head", "-n", "10"]]
    shell = to_shell(plan)
    assert shell.count(" | ") == 2
    # each stage round-trips independently
    for stage in plan:
        piece = to_shell(stage)
        assert shlex.split(piece) == stage


def test_regression():
    assert parse("show errors in train.log").intent == "search_in_file"
    assert parse("what's using the most cpu").intent == "top_by_cpu"
