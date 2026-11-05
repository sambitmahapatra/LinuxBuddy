"""Runtime mode + containment root for LinuxBuddy (Task 12, P2.0).

One place to read the two env vars that govern the destructive-containment
gate. Pure stdlib. Values are read live (not cached) so a caller/test can set
the environment per invocation.

  * ``LINUXBUDDY_MODE``       : "prototype" (default) | "prod"
  * ``LINUXBUDDY_MAZE_ROOT``  : the directory under which destructive commands
                                are allowed in prototype mode. Defaults to
                                ``~/linuxbuddy/testlinuxbuddy``.
"""
from __future__ import annotations

import os

__all__ = ["mode", "maze_root", "is_prototype"]

_DEFAULT_MAZE_ROOT = "~/linuxbuddy/testlinuxbuddy"


def mode() -> str:
    """"prototype" (default) or "prod". Anything that is not exactly "prod"
    is treated as prototype — fail safe toward containment."""
    return os.environ.get("LINUXBUDDY_MODE", "prototype").strip().lower()


def is_prototype() -> bool:
    return mode() != "prod"


def maze_root() -> str:
    """The containment root as a real absolute path (symlinks and ``..``
    resolved), so the gate's under-root check cannot be fooled by a symlink."""
    raw = os.environ.get("LINUXBUDDY_MAZE_ROOT") or _DEFAULT_MAZE_ROOT
    return os.path.realpath(os.path.expanduser(raw))
