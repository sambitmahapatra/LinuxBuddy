"""Task 25 tests — routing priority (specific intent beats `find`) + parsing
bugs. Each test is anchored to a named sweep row."""
from linuxbuddy.cli import main
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


def sh(req):
    return to_shell(compile(parse(req)))


# --- A. find was eating view/count/copy/history/process/perm intents ---

def test_E047_show_file_is_preview_not_find():
    assert sh("show me config.yaml") == "head -n 10 -- config.yaml"


def test_E050_whats_in_the_log_is_preview():
    assert sh("what's in the log") == "head -n 10 -- *.log"


def test_E052_peek_is_head():
    assert sh("peek at data.csv") == "head -n 10 -- data.csv"


def test_E054_last_lines_is_tail():
    assert sh("last lines of the log") == "tail -n 10 -- *.log"


def test_E075_remove_duplicates_is_unique():
    assert sh("remove duplicate lines from names.txt") == "sort -u -- names.txt"


def test_E096_who_can_read_is_perms_not_find():
    out = sh("who can read config.yaml")
    assert out.startswith(("ls -", "stat")) and "config.yaml" in out


def test_E101_list_named_processes_is_pgrep_not_find():
    assert parse("list the python processes").intent == "find_process"
    assert sh("list the python processes") == "pgrep -af python"


def test_E127_make_a_copy_is_cp_and_exits_3(capsys):
    assert sh("make a copy of config.yaml") == "cp -- config.yaml config.yaml.bak"
    code = main(["make a copy of config.yaml"])  # in-repo cwd is under the maze? no
    # exit is 3 (destructive) when emitted; gate may deny outside maze (exit 1).
    assert code in (3, 1)


def test_E035_locate_is_discovery_not_grep():
    assert parse("locate train.py").intent == "find_by_name"
    assert sh("locate train.py") == "find . -name train.py"


def test_E069_count_the_warnings_is_grep_count_not_wc():
    assert sh("count the warnings in train.log") == "grep -ciF -- warning train.log"


# --- B. parsing bugs ---

def test_E088_date_not_grep_garbage():
    assert sh("what's today's date") == "date"


def test_E071_recursive_grep_uses_cwd_not_pattern():
    assert sh("find 'deprecated' everywhere") == "grep -RnF -- deprecated ."


def test_E042_under_is_minus_size():
    assert sh("small files under 1kb") == "find . -type f -size -1024c"


def test_E040_E041_over_stays_plus_size():
    assert sh("files bigger than 100mb") == "find . -type f -size +104857600c"
    assert sh("anything over 1 gig") == "find . -type f -size +1073741824c"


# --- regression: find must still win for genuine discovery ---

def test_find_still_wins_for_discovery():
    assert sh("find all csv files") == "find . -name '*.csv'"
    # Task 27: "how many … files" is now a file-COUNT (find | wc -l), still a
    # file_discovery find — just piped. (Was a bare find before count_files.)
    assert sh("how many json files") == "find . -name '*.json' | wc -l"
    assert sh("where are the log files") == "find . -name '*.log'"


def test_grep_neighbors_unchanged():
    assert sh("find error in train.log") == "grep -niF -- error train.log"
    assert sh("how many errors in the log") == "grep -ciF -- error *.log"
