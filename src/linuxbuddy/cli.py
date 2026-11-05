"""The ``lb`` command: natural-language request -> a runnable command string.

Pipeline: nlu.parse -> planner.compile -> render.to_shell.

Contract (so a caller can trust stdout):
  * success           -> print the command to stdout, exit 0.
  * abstain / failure -> print a short message to stderr, exit 1, and print
    NOTHING to stdout. stdout is therefore always either empty or a single
    runnable command.

Nothing is executed. LinuxBuddy only prints a command for the user to run.
"""
from __future__ import annotations

import os
import sys

from . import gate
from .nlu import parse, abstain_hint
from .planner import compile, risk_ops, PlanError
from .render import to_shell, RenderError

__all__ = ["main"]

_ABSTAIN_MSG = "LinuxBuddy: not sure what you mean"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    request = " ".join(args)

    frame = parse(request)
    if frame is None:
        # Prefer a specific hint ("how big? try ...") when we can tell which
        # defining slot was missing; otherwise the generic message.
        print(abstain_hint(request) or _ABSTAIN_MSG, file=sys.stderr)
        return 1

    try:
        argv_plan = compile(frame)
    except PlanError:
        print(_ABSTAIN_MSG, file=sys.stderr)
        return 1

    # Destructive-containment gate (P2.0): a write/delete/chmod plan may only
    # be emitted when cwd is inside the maze (prototype mode). Checked AFTER
    # compile, BEFORE rendering/printing — so nothing destructive reaches
    # stdout from the wrong place.
    denied = gate.check(risk_ops(frame.intent), os.getcwd())
    if denied:
        print(denied, file=sys.stderr)
        return 1

    try:
        command = to_shell(argv_plan)
    except RenderError:
        print(_ABSTAIN_MSG, file=sys.stderr)
        return 1

    print(command)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
