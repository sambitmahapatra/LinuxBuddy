"""Task 18 tests — lb signals risk by exit code so the shell widget can tier its
confirm: 0 = read-only, 3 = destructive, 1 = abstain."""
from linuxbuddy.cli import main


def test_read_only_command_exits_zero(capsys):
    code = main(["what's running"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() != ""  # a command was emitted


def test_destructive_command_exits_three(capsys, monkeypatch):
    # chmod is destructive (risk_ops write). prod mode lifts the containment
    # gate so the command is emitted here regardless of cwd; the exit code is 3.
    monkeypatch.setenv("LINUXBUDDY_MODE", "prod")
    code = main(["make run.sh executable"])
    out = capsys.readouterr().out
    assert code == 3
    assert out.strip() == "chmod u+x -- run.sh"


def test_destructive_denied_outside_maze_exits_one(capsys, monkeypatch):
    # prototype mode + cwd outside the maze → gate refuses → exit 1, no stdout.
    monkeypatch.setenv("LINUXBUDDY_MODE", "prototype")
    monkeypatch.chdir("/tmp")
    code = main(["make run.sh executable"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""


def test_abstain_exits_one(capsys):
    code = main(["do the thing"])
    assert code == 1
    assert capsys.readouterr().out == ""
