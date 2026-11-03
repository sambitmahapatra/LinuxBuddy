"""Render an argv list to a display shell string.

SECURITY BOUNDARY. The rendered string is for the user to look at and drop
into their shell buffer. It is NEVER the execution source — the argv list is
the source of truth. This module's one job is to produce a string that, when
the user's shell re-tokenizes it, yields EXACTLY the argv we compiled.

The round-trip assertion (``shlex.split(result) == argv``) is what makes that
guarantee machine-checked: if quoting ever failed to neutralize a slot value,
the round trip would differ and we raise instead of emitting it.
"""
from __future__ import annotations

import shlex

__all__ = ["to_shell", "RenderError"]


class RenderError(ValueError):
    """Raised when a rendered string fails to round-trip back to the argv."""


def to_shell(argv: list[str]) -> str:
    for i, elem in enumerate(argv):
        if not isinstance(elem, str):
            raise RenderError(
                f"argv[{i}] is {type(elem).__name__}, not str: {elem!r}"
            )

    rendered = " ".join(shlex.quote(elem) for elem in argv)

    # The guarantee: the shell must re-tokenize this back to the exact argv.
    if shlex.split(rendered) != argv:
        raise RenderError(
            f"render did not round-trip: {rendered!r} -> {shlex.split(rendered)!r} "
            f"!= {argv!r}"
        )
    return rendered
