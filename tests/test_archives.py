"""Task 13 tests — domain: archives_backup. Read intents work anywhere; write
intents (create/extract/compress) are gated to the maze via risk_ops=[write].
"""
from linuxbuddy.nlu import parse, Frame
from linuxbuddy.planner import compile, risk_ops
from linuxbuddy.render import to_shell
from linuxbuddy import gate


# --- the task's example table ---------------------------------------------

def test_list_archive_tar():
    f = parse("what's inside backup.tar.gz")
    assert f.intent == "list_archive"
    assert f.slots["archive"] == "backup.tar.gz"
    # No `--`: tar's -f takes the next token as the archive name, so a `--`
    # right after -tf would be treated as the filename (matches dataset ARCH-002).
    assert compile(f) == ["tar", "-tf", "backup.tar.gz"]


def test_list_archive_zip_uses_zipfile():
    f = parse("show files in release.zip")
    assert f.intent == "list_zip"
    assert compile(f) == ["python3", "-m", "zipfile", "-l", "release.zip"]


def test_archive_integrity():
    f = parse("does data.gz pass its integrity check")
    assert f.intent == "archive_integrity"
    assert compile(f) == ["gzip", "-t", "--", "data.gz"]


def test_create_archive():
    f = parse("package the src folder into src.tar.gz")
    assert f.intent == "create_archive"
    assert f.slots["archive"] == "src.tar.gz"
    assert f.slots["name"] == "src"
    assert compile(f) == ["tar", "-czf", "src.tar.gz", "-C", ".", "--", "src"]


def test_extract_archive_is_and_chain():
    f = parse("unpack backup.tar.gz into output")
    assert f.intent == "extract_archive"
    assert f.slots["archive"] == "backup.tar.gz"
    assert f.slots["path"] == "output"
    plan = compile(f)
    assert plan == [["mkdir", "-p", "--", "output"],
                    ["tar", "-xf", "backup.tar.gz", "-C", "output"]]
    assert to_shell(plan) == "mkdir -p -- output && tar -xf backup.tar.gz -C output"


def test_compress_file():
    f = parse("compress train.log")
    assert f.intent == "compress_file"
    assert f.slots["path"] == "train.log"
    assert compile(f) == ["gzip", "-k", "--", "train.log"]


# --- risk_ops / gating -----------------------------------------------------

def test_read_intents_are_read_only():
    for intent in ("list_archive", "list_zip", "archive_integrity", "archive_size"):
        assert risk_ops(intent) == ["read"]


def test_write_intents_are_gated():
    for intent in ("create_archive", "extract_archive", "compress_file"):
        assert risk_ops(intent) == ["write"]
        # a write plan outside the maze is refused by the gate
        assert gate.check(risk_ops(intent), "/tmp") is not None


# --- regression ------------------------------------------------------------

def test_prior_domains_regression():
    assert parse("csv files over 100 megs").intent == "find_by_size"
    assert parse("show errors in train.log").intent == "search_in_file"
    assert parse("how big is the data folder").intent == "disk_usage"
    assert parse("what's using the most cpu").intent == "top_by_cpu"
