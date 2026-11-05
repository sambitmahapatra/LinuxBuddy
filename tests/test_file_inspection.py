"""Task 08 tests — domain: file_inspection (single-command intents).

Written before the implementation (TDD, per CLAUDE.md). Behaviour, not just
"it runs": each case asserts the intent and the defining slots, and the
compound request abstains rather than guessing one of its parts.
"""
import shlex

import pytest

from linuxbuddy.nlu import parse, Frame
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


# --- NLU: the task's example table ----------------------------------------

def test_first_20_lines():
    f = parse("first 20 lines of train.log")
    assert isinstance(f, Frame)
    assert f.intent == "preview_head"
    assert f.slots["count"] == 20
    assert f.slots["path"] == "train.log"


def test_last_50_lines():
    f = parse("last 50 lines of the log")
    assert f.intent == "preview_tail"
    assert f.slots["count"] == 50


def test_count_lines():
    f = parse("how many lines in access.log")
    assert f.intent == "count_lines"
    assert f.slots["path"] == "access.log"


def test_size_in_bytes():
    f = parse("size of config.yaml in bytes")
    assert f.intent == "show_size"
    assert f.slots["path"] == "config.yaml"


def test_detect_type():
    f = parse("what kind of file is data.bin")
    assert f.intent == "detect_type"
    assert f.slots["path"] == "data.bin"


def test_show_stat_time():
    f = parse("when was model.pt last changed")
    assert f.intent == "show_stat"
    assert f.slots["path"] == "model.pt"
    # a time-focused request picks a time format, not the full metadata dump
    assert "%y" in f.slots["fmt"]


def test_compound_abstains():
    # three distinct asks (preview + count + size) => abstain, do NOT fall
    # through to file_discovery's "csv" -> find_by_type.
    assert parse("preview, count and size of this csv") is None


# --- preview defaults ------------------------------------------------------

def test_preview_head_default_count():
    f = parse("show the top of config.yaml")
    assert f.intent == "preview_head"
    assert f.slots["count"] == 10


def test_preview_tail_default_count():
    f = parse("show the end of train.log")
    assert f.intent == "preview_tail"
    assert f.slots["count"] == 10


# --- planner + render: real commands, injection-safe fmt -------------------

def test_head_compiles_and_renders():
    argv = compile(parse("first 20 lines of train.log"))
    assert argv == ["head", "-n", "20", "--", "train.log"]
    assert to_shell(argv) == "head -n 20 -- train.log"


def test_count_lines_compiles():
    argv = compile(parse("how many lines in access.log"))
    assert argv == ["wc", "-l", "--", "access.log"]


def test_size_compiles_wc_c():
    argv = compile(parse("size of config.yaml in bytes"))
    assert argv == ["wc", "-c", "--", "config.yaml"]


def test_stat_fmt_is_single_argv_element():
    # The fmt string has spaces; it must remain ONE argv element and survive
    # the render round-trip quoted.
    argv = compile(parse("when was model.pt last changed"))
    assert argv[0] == "stat" and argv[1] == "-c"
    assert " " in argv[2]  # the fmt is one element with spaces
    rendered = to_shell(argv)
    assert shlex.split(rendered) == argv


# --- regression: file_discovery still works --------------------------------

def test_file_discovery_regression():
    f = parse("csv files over 100 megs")
    assert f.intent == "find_by_size"
    f = parse("all the log files here")
    assert f.intent == "find_by_type"
