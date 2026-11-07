"""Task 20 tests — asymmetric abstain policy (help on reads, caution on
destructive). Read-only requests with a reasonable interpretation emit a
command; genuinely vague reads and unclear destructive requests still abstain.
"""
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile


# --- reads now EMIT (used to abstain) ---

def test_read_superlative_emits_not_hint():
    assert parse("show me the biggest files here").intent == "find_largest"
    assert parse("find big files").intent == "find_largest"
    # ("which files are huge" is a check_installed mis-route fixed in Task 23.)


def test_smallest_maps_to_find_smallest():
    f = parse("show me the smallest files")
    assert f.intent == "find_smallest"
    assert compile(f) == [["find", ".", "-type", "f", "-printf", "%s\\t%p\\n"],
                          ["sort", "-n"], ["head", "-n", "10"]]


# --- "open X" no longer mis-routes to a find ---

def test_open_file_abstains_not_find():
    # used to emit `find . -name '*.csv'` — a wrong command is worse than abstain
    assert parse("open huge_dataset.csv") is None


# --- genuinely vague reads STILL abstain ---

def test_vague_still_abstains():
    assert parse("do the thing") is None
    assert parse("fix this") is None
    assert parse("clean up my mess") is None


# --- destructive-with-unclear-target STILL abstains (unchanged) ---

def test_destructive_unclear_still_abstains():
    assert parse("make this executable") is None          # no file named
    assert parse("kill the process") is None              # no name/pid
    assert parse("change the permissions on config.yaml") is None  # no mode
