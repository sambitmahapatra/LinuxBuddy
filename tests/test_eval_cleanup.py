"""Task 23 tests — eval cleanup: wrong-routes, defaults, known synonyms.
Each test is anchored to a named eval row (E###). Destructive rows assert the
parse/compile directly (the containment gate is a separate layer)."""
from linuxbuddy.nlu import parse
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


# --- A. wrong commands (priority: these emitted misleading commands) ---

def test_E004_huge_files_is_find_largest_not_command_v():
    assert parse("which files are huge").intent == "find_largest"


def test_E024_print_file_is_preview_not_find():
    f = parse("print config.yaml")
    assert f.intent in ("preview_head", "preview_tail")
    assert "find" not in to_shell(compile(f))
    assert "config.yaml" in to_shell(compile(f))


def test_E090_known_package_uses_importlib_not_command_v():
    f = parse("is numpy installed")
    assert f.intent == "check_package"
    assert "importlib" in to_shell(compile(f))


def test_E016_recently_modified_keeps_mtime():
    f = parse("recently modified logs")
    assert f.intent == "find_by_time"
    assert "-mtime" in to_shell(compile(f))


def test_E018_concrete_name_is_exact_match():
    f = parse("where is settings.json")
    assert f.intent == "find_by_name"
    assert to_shell(compile(f)) == "find . -name settings.json"


# --- B. missing-argument defaults ---

def test_E056_E058_port_default_lists_listening():
    assert to_shell(compile(parse("what's on my port"))) == "ss -ltnp"
    assert to_shell(compile(parse("what's listening"))) == "ss -ltnp"


# --- C. known synonyms ---

def test_E060_E062_stop_terminate_are_kill():
    assert parse("stop the training process").intent == "kill_process"
    assert parse("stop the training process").slots["pattern"] == "training"
    assert parse("terminate the sleep process").slots["pattern"] == "sleep"


def test_E111_check_if_installed_is_check_installed():
    f = parse("check if git is installed")
    assert f.intent == "check_installed"
    assert f.slots["tool"] == "git"


def test_E119_room_is_home_space():
    assert parse("how much room is left on ubuntu").intent == "home_space"


def test_E084_zip_up_is_create_archive():
    f = parse("zip up the project")
    assert f.intent == "create_archive"
    assert f.slots["name"] == "project"


def test_E075_needs_executable_is_chmod_ux():
    f = parse("this script needs to be executable")
    assert f.intent == "make_executable"
    assert to_shell(compile(f)) == "chmod u+x -- *.sh"


def test_E077_private_is_chmod_600():
    f = parse("make this file private")
    assert f.intent == "set_permission"
    assert f.slots["mode"] == "600"


def test_E078_only_i_can_read_is_chmod_600():
    f = parse("only I should be able to read this")
    assert f.intent == "set_permission"
    assert f.slots["mode"] == "600"


# --- regression: the new synonyms must not over-trigger ---

def test_stop_non_process_does_not_kill():
    # "stop" without "process" is not a kill (would be a different/unknown intent)
    f = parse("stop the server")
    assert f is None or f.intent != "kill_process"


def test_can_i_read_stays_check_readable_not_chmod():
    assert parse("can i read secret.txt").intent == "check_readable"


def test_unknown_tool_install_check_stays_command_v():
    # a non-Python-package token keeps the CLI check (command -v), not importlib
    f = parse("is docker installed")
    assert f.intent == "check_installed"
