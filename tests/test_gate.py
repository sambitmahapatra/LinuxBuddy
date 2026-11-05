"""Task 12 tests — the destructive-containment gate (P2.0).

A plan's risk is its risk_ops; a "fake write plan" is just ["write"]. The
traversal test is the important one: a cwd that spells its way out of the maze
with `..` must be treated as outside.
"""
import os

import pytest

from linuxbuddy import gate


WRITE = ["write"]
READ = ["read"]


@pytest.fixture
def maze(tmp_path, monkeypatch):
    root = tmp_path / "maze"
    (root / "project").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    monkeypatch.setenv("LINUXBUDDY_MAZE_ROOT", str(root))
    monkeypatch.setenv("LINUXBUDDY_MODE", "prototype")
    return tmp_path, root


def test_prototype_write_outside_maze_abstains(maze):
    tmp_path, root = maze
    reason = gate.check(WRITE, str(tmp_path / "outside"))
    assert reason is not None
    assert "test maze" in reason


def test_prototype_write_inside_maze_allowed(maze):
    tmp_path, root = maze
    assert gate.check(WRITE, str(root / "project")) is None
    assert gate.check(WRITE, str(root)) is None  # root itself counts as inside


def test_prototype_read_anywhere_allowed(maze):
    tmp_path, root = maze
    assert gate.check(READ, str(tmp_path / "outside")) is None
    assert gate.check([], "/") is None


def test_prod_write_anywhere_allowed(maze, monkeypatch):
    tmp_path, root = maze
    monkeypatch.setenv("LINUXBUDDY_MODE", "prod")
    assert gate.check(WRITE, str(tmp_path / "outside")) is None


def test_path_traversal_treated_as_outside(maze):
    # cwd spells its way back out of the maze with `..` → must abstain.
    tmp_path, root = maze
    sneaky = str(root / "project" / ".." / ".." / "outside")
    assert os.path.realpath(sneaky) == str((tmp_path / "outside").resolve())
    assert gate.check(WRITE, sneaky) is not None


def test_symlink_out_of_maze_treated_as_outside(maze):
    # a symlink inside the maze pointing outside → realpath resolves it out.
    tmp_path, root = maze
    link = root / "escape"
    link.symlink_to(tmp_path / "outside")
    assert gate.check(WRITE, str(link)) is not None


def test_mixed_risk_ops_is_destructive(maze):
    tmp_path, root = maze
    # a plan that reads AND writes is destructive → gated
    assert gate.check(["read", "write"], str(tmp_path / "outside")) is not None
