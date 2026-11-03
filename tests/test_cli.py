"""Task 04 tests — the lb CLI entry point (invoked in-process)."""
from linuxbuddy.cli import main


def test_success_prints_command_and_exits_zero(capsys):
    code = main(["csv", "files", "over", "100", "megs"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "find . -type f -name '*.csv' -size +104857600c"
    assert captured.err == ""


def test_abstain_prints_nothing_to_stdout_and_exits_one(capsys):
    code = main(["clean", "up", "my", "mess"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "not sure what you mean" in captured.err


def test_single_string_arg_from_widget(capsys):
    # The zsh widget passes the whole buffer as one argument.
    code = main(["csv files over 100 megs"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.strip() == "find . -type f -name '*.csv' -size +104857600c"
