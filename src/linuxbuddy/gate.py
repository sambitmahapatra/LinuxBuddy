"""Destructive-containment gate (Task 12, P2.0).

"Safety by containment" (CLAUDE.md / ROADMAP): in prototype mode (the default)
LinuxBuddy refuses to emit a write/delete/chmod command unless the current
working directory is under the maze root, where damage is disposable. Read-only
intents work anywhere. In prod mode the gate is off.

The gate's decision is based on a plan's ``risk_ops`` (declared per intent in
the KB). A plan is *destructive* if its risk_ops include any of ``write``,
``delete`` or ``privilege``. ``check`` returns ``None`` to allow, or a
ready-to-print abstain message string to refuse.
"""
from __future__ import annotations

import os

from . import config

__all__ = ["check", "is_destructive", "DESTRUCTIVE_OPS"]

DESTRUCTIVE_OPS = frozenset({"write", "delete", "privilege"})


def is_destructive(risk_ops) -> bool:
    return any(op in DESTRUCTIVE_OPS for op in (risk_ops or []))


def _under(path: str, root: str) -> bool:
    """True if ``path`` is ``root`` or lives under it. Both are resolved to
    real absolute paths first, so ``..`` or a symlink cannot slip the check."""
    rp = os.path.realpath(path)
    try:
        return os.path.commonpath([rp, root]) == root
    except ValueError:
        # Different drives / mixed absolute-relative — treat as outside.
        return False


def check(risk_ops, cwd: str) -> str | None:
    """Return ``None`` to allow the plan, or an abstain message to refuse it.

    ``risk_ops`` is the plan's risk list (from the KB); a stub ``["write"]``
    is a valid "fake destructive plan" for tests. ``cwd`` is the directory the
    command would run in (the caller passes ``os.getcwd()``).
    """
    if not config.is_prototype():
        return None  # prod: gate off
    if not is_destructive(risk_ops):
        return None  # read-only: allowed anywhere
    root = config.maze_root()
    if _under(cwd, root):
        return None  # destructive, but safely inside the maze
    return (
        "LinuxBuddy (prototype): destructive commands only run inside the "
        f"test maze. cd into {root} first."
    )
