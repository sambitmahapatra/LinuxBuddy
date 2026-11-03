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

import sys

from .nlu import parse
from .planner import compile, PlanError
from .render import to_shell, RenderError

__all__ = ["main"]

_ABSTAIN_MSG = "LinuxBuddy: not sure what you mean"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    request = " ".join(args)

    frame = parse(request)
    if frame is None:
        print(_ABSTAIN_MSG, file=sys.stderr)
        return 1

    try:
        argv_plan = compile(frame)
        command = to_shell(argv_plan)
    except (PlanError, RenderError):
        # Any planning/rendering failure is treated as "not sure": never
        # emit a partial or unsafe command to stdout.
        print(_ABSTAIN_MSG, file=sys.stderr)
        return 1

    print(command)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
