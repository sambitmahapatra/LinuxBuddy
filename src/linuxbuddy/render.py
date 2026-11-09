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

import re
import shlex

__all__ = ["to_shell", "RenderError", "Stages", "Raw"]


class RenderError(ValueError):
    """Raised when a rendered string fails to round-trip back to the argv."""


# A Raw element is a TRUSTED shell-literal — a glob WE generated (e.g. "*.log",
# "config.*") or an env-var reference ("$PATH", "/mnt/c/Users/$USER/Downloads")
# that must reach the shell UNQUOTED so the shell expands it. shlex.quote would
# wrap it in quotes and kill the expansion. Raw is only ever produced by the
# planner/nlu from a recognised reference — NEVER from a user-supplied slot
# value — and is restricted to a safe charset so it still tokenizes back to
# itself (the round-trip guarantee holds). `$ { }` are allowed for env-var
# references; command substitution `$(` / backticks cannot form because `(`,
# `)`, backtick and whitespace are all excluded.
_SAFE_RAW_RE = re.compile(r"^[\w*?.@%+=:,/${}-]+$")


class Raw(str):
    """A trusted glob/shell-literal argv element, emitted unquoted by render."""


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

    parts = []
    for elem in argv:
        if isinstance(elem, Raw):
            # Trusted glob → emit unquoted so the shell expands it. Guard the
            # charset so an unexpected value can never smuggle in whitespace or
            # a shell operator.
            if not _SAFE_RAW_RE.match(elem):
                raise RenderError(f"unsafe Raw element: {elem!r}")
            parts.append(str(elem))
        else:
            parts.append(shlex.quote(elem))
    rendered = " ".join(parts)

    # The guarantee: the shell must re-tokenize this back to the exact argv
    # (comparing as plain strings, since Raw is a str subclass).
    if shlex.split(rendered) != [str(e) for e in argv]:
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
