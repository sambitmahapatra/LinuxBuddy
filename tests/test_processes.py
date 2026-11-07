"""Task 10 tests — domain: processes (read-only intents) + 2-stage pipe.

TDD. kill/pkill are destructive and out of scope → abstain. top_by_* use a
2-stage pipeline (ps ... | head); the pipe round-trip is asserted here.
"""
import shlex

from linuxbuddy.nlu import parse, Frame
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


# --- the task's example table ---------------------------------------------

def test_list_processes():
    assert parse("what's running").intent == "list_processes"


def test_top_by_cpu_default_count():
    f = parse("what's using the most cpu")
    assert f.intent == "top_by_cpu"
    assert f.slots["count"] == 10


def test_top_by_mem_count_5():
    f = parse("biggest memory consumers top 5")
    assert f.intent == "top_by_mem"
    assert f.slots["count"] == 5


def test_find_process():
    f = parse("is python running")
    assert f.intent == "find_process"
    assert f.slots["pattern"] == "python"


def test_process_on_port():
    f = parse("what's using port 8080")
    assert f.intent == "process_on_port"
    assert f.slots["port"] == 8080


def test_show_pid():
    f = parse("show the process with pid 1234")
    assert f.intent == "show_pid"
    assert f.slots["pid"] == 1234


def test_kill_process_builds_gated_intent():
    # Task 15: kill now builds a real (gated) intent instead of abstaining.
    f = parse("kill python")
    assert f.intent == "kill_process"
    assert f.slots["pattern"] == "python"


def test_kill_process_named():
    f = parse("kill the training process")
    assert f.intent == "kill_process"
    assert f.slots["pattern"] == "training"
    assert compile(f) == ["pkill", "-f", "--", "training"]


def test_kill_pid():
    f = parse("kill process 4821")
    assert f.intent == "kill_pid"
    assert f.slots["pid"] == 4821
    assert compile(f) == ["kill", "--", "4821"]


def test_kill_unspecified_abstains():
    # "kill the process" with no name or pid → abstain, don't guess.
    assert parse("kill the process") is None


def test_kill_intents_gated():
    from linuxbuddy.planner import risk_ops
    from linuxbuddy import gate
    for intent in ("kill_process", "kill_pid"):
        assert risk_ops(intent) == ["write"]
        assert gate.check(risk_ops(intent), "/tmp") is not None


# --- pipe support (planner + render) ---------------------------------------

def test_top_by_cpu_is_a_two_stage_pipeline():
    stages = compile(parse("what's using the most cpu"))
    assert stages == [
        ["ps", "-eo", "pid,comm,%cpu", "--sort=-%cpu"],
        ["head", "-n", "10"],
    ]
    assert to_shell(stages) == "ps -eo pid,comm,%cpu --sort=-%cpu | head -n 10"


def test_pipe_round_trip_each_stage():
    # The | is compiler-inserted; each stage must re-tokenize to its own argv.
    stages = compile(parse("biggest memory consumers top 5"))
    rendered = to_shell(stages)
    parts = rendered.split(" | ")
    assert len(parts) == 2
    for part, stage in zip(parts, stages):
        assert shlex.split(part) == stage
    assert rendered.endswith("head -n 5")


def test_single_command_still_flat():
    argv = compile(parse("what's running"))
    assert argv == ["ps", "aux"]
    assert to_shell(argv) == "ps aux"


def test_process_on_port_quotes_the_filter():
    argv = compile(parse("what's using port 8080"))
    assert argv == ["ss", "-ltnp", "sport = :8080"]
    # the space-bearing filter is ONE argv element, quoted on render
    assert to_shell(argv) == "ss -ltnp 'sport = :8080'"
    assert shlex.split(to_shell(argv)) == argv


def test_show_pid_compiles():
    argv = compile(parse("show the process with pid 1234"))
    assert argv == ["ps", "-p", "1234", "-o", "pid,ppid,stat,%cpu,%mem,args"]


# --- regression ------------------------------------------------------------

def test_prior_domains_regression():
    assert parse("csv files over 100 megs").intent == "find_by_size"
    assert parse("first 20 lines of train.log").intent == "preview_head"
    assert parse("show errors in train.log").intent == "search_in_file"
