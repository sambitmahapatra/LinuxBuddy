"""Task 28 tests — the last rules-v1 residual cleanup. Each test is anchored to
a named sweep row (E0xx). Four fixes + regression guards that the new defaults
(history, README glob, lines-grep, windows-folder glob) don't steal other rows.
"""
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


def sh(req):
    return to_shell(compile(parse(req)))


# --- E086: a command-history request beats find_recent even with "recently" ---

def test_E086_commands_i_ran_is_history():
    f = parse("what commands did i run recently")
    assert f.intent == "show_history"
    assert sh("what commands did i run recently") == "history"


def test_E086_recent_commands_is_history():
    assert parse("show me my recent commands").intent == "show_history"


def test_E086_what_have_i_run_is_history():
    assert parse("what have i run").intent == "show_history"


# --- E048: "print/show the readme" previews README* (definite-ref, Task 22) ---

def test_E048_print_the_readme():
    assert sh("print the readme") == "head -n 10 -- README*"


def test_E048_show_the_readme():
    assert sh("show the readme") == "head -n 10 -- README*"


# --- E066: "which lines mention X" with no file → recursive grep in cwd -------

def test_E066_which_lines_mention():
    # warning is a case-word → -i; recursive (-Rn…F) in cwd (.), like E070/E071.
    assert sh("which lines mention warning") == "grep -RniF -- warning ."


def test_E066_lines_with_pattern():
    assert sh("lines with warning") == "grep -RniF -- warning ."


def test_E066_lines_mentioning_pattern():
    assert parse("lines mentioning warning").intent == "search_recursive"


def test_E066_named_file_still_searches_that_file():
    # When a file IS named, stay a normal single-file grep (no recursive default).
    f = parse("which lines mention warning in app.log")
    assert f.intent == "search_in_file" and f.slots["path"] == "app.log"


# --- E117/E118: windows user folder uses a GLOB, not $USER -------------------

def test_E117_windows_downloads_glob():
    assert sh("take me to my windows downloads") == "cd -- /mnt/c/Users/*/Downloads"


def test_E118_windows_documents_glob():
    assert sh("where are my windows documents") == "cd -- /mnt/c/Users/*/Documents"


# --- regression: history must NOT steal file-discovery rows (E036–E039) ------

def test_history_does_not_steal_recent_files():
    assert parse("files modified in the last 7 days").intent == "find_by_time"


def test_history_does_not_steal_last_hour():
    # E039: a sub-day recency file window stays find_recent (-mmin), not history.
    assert parse("what did i touch in the last hour").intent == "find_recent"


def test_readme_default_does_not_break_other_definite_refs():
    # "the log" still resolves to *.log, unaffected by the README addition.
    assert sh("show errors in the log") == "grep -niF -- error *.log"


def test_lines_grep_does_not_break_named_file_grep():
    # A normal file-named grep stays single-file (not the recursive lines-grep
    # default), because a path was detected.
    f = parse("search for deprecated in train.log")
    assert f.intent == "search_in_file" and f.slots["path"] == "train.log"
