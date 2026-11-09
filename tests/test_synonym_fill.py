"""Task 27 tests — intent & synonym fill. Each test is anchored to a named
sweep row (E0xx). Destructive intents must signal exit 3 (gate-permitting)."""
from linuxbuddy.cli import main
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


def sh(req):
    return to_shell(compile(parse(req)))


# --- env_var (E076/E077/E078) — $VAR stays UNQUOTED so the shell expands it ---

def test_E076_path_var():
    assert sh("what's my PATH") == "echo $PATH"


def test_E077_port_var():
    assert sh("show the PORT variable") == "echo $PORT"


def test_E078_home_var():
    assert sh("print the home variable") == "echo $HOME"


# --- disk_space (E079/E081) ---

def test_E079_space_left_is_df():
    assert sh("how much space is left") == "df -h"


def test_E081_running_out_of_disk_is_df():
    assert sh("am i running out of disk") == "df -h"


# --- which / pip location (E085) ---

def test_E085_which_pip():
    assert sh("which pip am i using") == "command -v -- pip"


# --- pip_list (E134/E135) ---

def test_E134_what_packages_installed():
    assert sh("what packages are installed") == "pip list"


def test_E135_list_pip_packages():
    assert sh("list my pip packages") == "pip list"


# --- package vs CLI (E129/E130/E132) ---

def test_E129_do_i_have_pandas_is_importlib():
    assert parse("do i have pandas").intent == "check_package"
    assert "find_spec" in sh("do i have pandas")


def test_E130_check_torch_is_importlib():
    assert parse("check if torch is there").intent == "check_package"


def test_E132_check_docker_is_cli():
    # docker is not a known python package → command -v (not importlib, not find)
    assert sh("check if docker is there") == "command -v -- docker"


# --- extract (E123/E124) — destructive, exit 3 ---

def test_E123_extract_tarball(monkeypatch, tmp_path):
    assert sh("extract the tarball") == "tar -xzf *.tar.gz"


def test_E124_unzip_archive():
    assert sh("unzip the archive") == "unzip *.zip"


# --- create_archive synonyms (E120/E122) ---

def test_E120_make_a_backup():
    assert sh("make a backup of the project") == "tar -czf project.tar.gz -C . -- project"


def test_E122_compress_the_results():
    assert sh("compress the results") == "tar -czf results.tar.gz -C . -- results"


# --- wsl: win_path / vscode / win_folders (E113/E114/E116/E117/E118) ---

def test_E113_windows_path_default_cwd():
    assert sh("what's the windows path for this folder") == "wslpath -w -- ."


def test_E114_convert_to_windows_path():
    assert sh("convert this path to a windows path") == "wslpath -w -- ."


def test_E116_open_vscode():
    assert sh("open this in vs code") == "code ."


def test_E117_windows_downloads():
    assert sh("take me to my windows downloads") == "cd -- /mnt/c/Users/$USER/Downloads"


def test_E118_windows_documents():
    assert sh("where are my windows documents") == "cd -- /mnt/c/Users/$USER/Documents"


# --- filesystem: chmod lock-down / find_perms (E094/E097/E098) ---

def test_E094_lock_down_is_chmod_600():
    out = sh("lock down the key file")
    assert out.startswith("chmod 600 ") and parse("lock down the key file").intent == "set_permission"


def test_E097_world_writable():
    assert sh("find world-writable files") == "find . -perm -002"


def test_E098_readable_by_everyone():
    assert sh("anything readable by everyone") == "find . -perm -004"


# --- processes (E100) ---

def test_E100_show_my_processes():
    assert sh("show my processes") == "ps aux"


# --- text: recursive grep (E065/E070) — cwd-synonym dirs → "." ---

def test_E065_search_in_the_code():
    assert sh("search for TODO in the code") == "grep -RnF -- TODO ."


def test_E070_search_all_files():
    assert sh("search all files for API_KEY") == "grep -RnF -- API_KEY ."


# --- file_discovery: find_empty / find_recent / count_files (E043-E046, E039) ---

def test_E043_find_empty_files():
    assert sh("find empty files") == "find . -empty -type f"


def test_E044_empty_folders():
    assert sh("any empty folders") == "find . -empty -type d"


def test_E039_last_hour_is_mmin():
    assert sh("what did i touch in the last hour") == "find . -type f -mmin -60"


def test_E045_how_many_csv_files():
    assert sh("how many csv files are there") == "find . -name '*.csv' | wc -l"


def test_E046_count_python_files():
    assert sh("count the python files") == "find . -name '*.py' | wc -l"


# --- exit codes: destructive synonyms must signal 3 (or 1 if gated outside maze) ---

def test_extract_is_destructive():
    assert main(["extract the tarball"]) in (3, 1)


def test_lock_down_is_destructive():
    assert main(["lock down the key file"]) in (3, 1)
