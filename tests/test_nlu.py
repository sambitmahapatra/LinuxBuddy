"""Task 02 tests — rule-based NLU for file_discovery.

Written before the implementation (TDD, per CLAUDE.md).
"""
from linuxbuddy.nlu import parse, Frame


def test_size_expression_csv_over_100_megs():
    f = parse("csv files over 100 megs")
    assert isinstance(f, Frame)
    assert f.intent == "find_by_size"
    assert f.slots["ext"] == "csv"
    assert f.slots["size_bytes"] == 104857600  # 100 * 1048576 (MiB)
    assert f.slots["path"] == "."


def test_time_expression_python_last_3_days():
    f = parse("python files changed in the last 3 days")
    assert f.intent == "find_by_time"
    assert f.slots["ext"] == "py"
    assert f.slots["days"] == 3


def test_name_expression_called_config():
    f = parse("find files called config")
    assert f.intent == "find_by_name"
    assert f.slots["pattern"] == "config"


def test_type_expression_log_files_here():
    f = parse("all the log files here")
    assert f.intent == "find_by_type"
    assert f.slots["ext"] == "log"
    assert f.slots["path"] == "."


def test_vague_big_in_downloads_now_abstains():
    # CHANGED by Task 05 (P1.1). A bare magnitude word with no numeric
    # threshold used to resolve to find_by_size WITHOUT size_bytes. That is
    # the silent-slot-dropping bug: it compiles to a match-everything
    # `find . -type f`. Per CLAUDE.md invariant #6 (abstain over guess) and
    # Task 05, find_by_size with no size_bytes now abstains.
    assert parse("big files in downloads") is None


def test_abstain_on_vague_input():
    assert parse("clean up my mess") is None


# --- Task 05: abstain on size-intent with no numeric threshold ------------

def test_abstain_biggest_files_here():
    assert parse("show me the biggest files here") is None


def test_abstain_largest_files():
    assert parse("largest files") is None


# --- Task 05: plural / possessive file-type words normalize to the ext ----

def test_plural_csvs_bigger_than_2_gigs():
    f = parse("csvs bigger than 2 gigs")
    assert f is not None
    assert f.intent == "find_by_size"
    assert f.slots["ext"] == "csv"
    assert f.slots["size_bytes"] == 2147483648  # 2 * 1073741824 (GiB)


def test_plural_logs_from_today():
    f = parse("logs from today")
    assert f is not None
    assert f.intent == "find_by_time"
    assert f.slots["ext"] == "log"
    assert f.slots["days"] == 1


# --- a few extra normalization checks the table implies -------------------

def test_size_unit_variants():
    assert parse("files 100mb").slots["size_bytes"] == 100 * 1048576
    assert parse("files over 100 mb").slots["size_bytes"] == 100 * 1048576
    assert parse("bigger than 2 gigs").slots["size_bytes"] == 2 * 1073741824
    assert parse("stuff over 100M").slots["size_bytes"] == 100 * 1048576


def test_time_keyword_variants():
    assert parse("changed today").slots["days"] == 1
    assert parse("changed this week").slots["days"] == 7
    assert parse("modified in the last 24 hours").slots["days"] == 1


def test_glob_and_quoted_ext():
    assert parse("*.log files").slots["ext"] == "log"
    assert parse("json").intent == "find_by_type"
    assert parse("json").slots["ext"] == "json"
