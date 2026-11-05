"""Task 11 tests — domain: filesystem_permissions (read-only).

TDD. chmod is destructive → abstain. dir_empty needs a `$(...)` command
substitution that the flat-argv model can't represent safely → deferred
(abstain). check_* are `test ... && printf ...` and-chains.
"""
import shlex

from linuxbuddy.nlu import parse, Frame
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


# --- the task's example table ---------------------------------------------

def test_check_writable():
    f = parse("can I write to the output folder")
    assert f.intent == "check_writable"
    assert f.slots["path"] == "output"


def test_check_exists():
    f = parse("does config.yaml exist")
    assert f.intent == "check_exists"
    assert f.slots["path"] == "config.yaml"


def test_check_readable():
    f = parse("is the data folder readable")
    assert f.intent == "check_readable"
    assert f.slots["path"] == "data"


def test_show_permissions():
    f = parse("show permissions for the logs dir")
    assert f.intent == "show_permissions"
    assert f.slots["path"] == "logs"


def test_show_owner():
    f = parse("who owns train.log")
    assert f.intent == "show_owner"
    assert f.slots["path"] == "train.log"


def test_dir_empty_is_deferred():
    # deferred (command-substitution form); abstain rather than hack it in.
    assert parse("is the results folder empty") is None


def test_disk_usage():
    f = parse("how big is the data folder")
    assert f.intent == "disk_usage"
    assert f.slots["path"] == "data"


def test_chmod_abstains():
    assert parse("make this executable") is None


# --- planner + render ------------------------------------------------------

def test_check_writable_is_and_chain():
    plan = compile(parse("can I write to the output folder"))
    # printf's arg is the LITERAL two chars backslash-n (printf expands \n at
    # runtime); the KB subset parser does not process escapes.
    assert plan == [["test", "-w", "output"], ["printf", "writable\\n"]]
    assert to_shell(plan) == "test -w output && printf 'writable\\n'"


def test_and_chain_round_trips_each_stage():
    plan = compile(parse("does config.yaml exist"))
    rendered = to_shell(plan)
    parts = rendered.split(" && ")
    assert len(parts) == 2
    for part, stage in zip(parts, plan):
        assert shlex.split(part) == stage


def test_show_owner_compiles():
    assert compile(parse("who owns train.log")) == ["stat", "-c", "%U:%G", "--", "train.log"]


def test_disk_usage_compiles():
    assert compile(parse("how big is the data folder")) == ["du", "-sh", "--", "data"]


# --- regression ------------------------------------------------------------

def test_prior_domains_regression():
    assert parse("csv files over 100 megs").intent == "find_by_size"
    assert parse("first 20 lines of train.log").intent == "preview_head"
    assert parse("show errors in train.log").intent == "search_in_file"
    assert parse("what's using the most cpu").intent == "top_by_cpu"
