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

__all__ = ["to_shell", "RenderError", "Stages"]


class RenderError(ValueError):
    """Raised when a rendered string fails to round-trip back to the argv."""


class Stages(list):
    """A multi-stage shell plan: a list of argv lists joined by a fixed
    operator ``op`` (``"|"`` for a pipe, ``"&&"`` for an and-chain). It
    subclasses ``list`` so equality with a plain list-of-lists still holds
    (handy in tests); the operator rides along as an attribute. The operator
    is ALWAYS compiler-chosen here — it never comes from a slot value or an
    argv element, so a hostile slot can never inject a pipe or a `&&`.
    """

    def __init__(self, stages, op: str):
        super().__init__(stages)
        self.op = op


def _render_stage(argv: list[str]) -> str:
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


def to_shell(argv: list) -> str:
    """Render a single-stage argv, or a multi-stage :class:`Stages` plan whose
    argv lists are joined by its operator (``|`` or ``&&``). The operator is
    inserted HERE, between independently-quoted stages — never from a slot or
    an argv element. Each stage round-trips on its own, so a hostile slot value
    in any stage stays one token.
    """
    if isinstance(argv, Stages):
        return f" {argv.op} ".join(_render_stage(stage) for stage in argv)
    if argv and all(isinstance(e, list) for e in argv):
        return " | ".join(_render_stage(stage) for stage in argv)
    return _render_stage(argv)
