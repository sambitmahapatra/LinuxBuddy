"""Task 09 tests — domain: text_and_logs (grep + sort, read-only).

TDD, behaviour-first. grep flags are modelled as a single combined token slot
(``gflags``, e.g. "-nF" / "-niF") so each argv element stays one piece and the
`--` that protects the pattern is compiler-inserted.
"""
import shlex

from linuxbuddy.nlu import parse, Frame
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


# --- the task's example table ---------------------------------------------

def test_search_word_in_file():
    f = parse("find the word convergence in report.txt")
    assert isinstance(f, Frame)
    assert f.intent == "search_in_file"
    assert f.slots["pattern"] == "convergence"
    assert f.slots["path"] == "report.txt"


def test_search_errors_is_case_insensitive():
    f = parse("show errors in train.log")
    assert f.intent == "search_in_file"
    assert f.slots["pattern"] == "error"
    assert "i" in f.slots["gflags"]  # -i defaulted for a log-level word


def test_search_recursive_todo():
    f = parse("find TODO across the src folder")
    assert f.intent == "search_recursive"
    assert f.slots["pattern"] == "TODO"
    assert f.slots["path"] == "src"
    assert "R" in f.slots["gflags"]


def test_count_matches_warnings():
    f = parse("how many warnings in the log")
    assert f.intent == "count_matches"
    assert f.slots["pattern"] == "warning"
    assert "c" in f.slots["gflags"]


def test_sort_lines():
    f = parse("sort names.txt alphabetically")
    assert f.intent == "sort_lines"
    assert f.slots["path"] == "names.txt"


def test_unique_lines():
    f = parse("show distinct rows in list.txt")
    assert f.intent == "unique_lines"
    assert f.slots["path"] == "list.txt"


def test_vague_find_abstains():
    assert parse("find stuff") is None


# --- planner + render ------------------------------------------------------

def test_search_in_file_compiles_and_renders():
    argv = compile(parse("find the word convergence in report.txt"))
    assert argv == ["grep", "-nF", "--", "convergence", "report.txt"]
    assert to_shell(argv) == "grep -nF -- convergence report.txt"


def test_recursive_compiles():
    argv = compile(parse("find TODO across the src folder"))
    assert argv == ["grep", "-RnF", "--", "TODO", "src"]


def test_count_compiles_case_insensitive():
    argv = compile(parse("how many warnings in train.log"))
    assert argv == ["grep", "-ciF", "--", "warning", "train.log"]


def test_sort_unique_compile():
    assert compile(parse("sort names.txt alphabetically")) == ["sort", "--", "names.txt"]
    assert compile(parse("show distinct rows in list.txt")) == ["sort", "-u", "--", "list.txt"]


def test_hostile_pattern_stays_one_element():
    # a pattern with shell metacharacters must survive as ONE argv element
    f = parse('find the word "x; rm -rf /" in report.txt')
    argv = compile(f)
    rendered = to_shell(argv)
    assert shlex.split(rendered) == argv
    assert "x; rm -rf /" in argv


# --- regression ------------------------------------------------------------

def test_prior_domains_regression():
    assert parse("csv files over 100 megs").intent == "find_by_size"
    assert parse("first 20 lines of train.log").intent == "preview_head"
