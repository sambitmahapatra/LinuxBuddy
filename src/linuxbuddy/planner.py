"""Compile a Frame into a typed argv list.

Invariants enforced here (CLAUDE.md):
  * The plan is a typed argv LIST. A slot value substitutes into exactly ONE
    argv element and is never joined into a command string.
  * $HOME and a leading ~ are resolved HERE, so the final argv holds absolute
    paths. We never emit ~ or $HOME for the shell to expand.
  * If any {placeholder} remains unresolved in the output, we raise
    PlanError — a placeholder must never reach the rendered string.
"""
from __future__ import annotations

import os
import re

from .kb import load_kb
from .nlu import Frame
from .render import Stages, Raw

__all__ = ["compile", "PlanError", "risk_ops"]

_PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")


class PlanError(ValueError):
    """Raised when a frame cannot be compiled into a complete argv."""


def _home() -> str:
    return os.environ.get("HOME") or os.path.expanduser("~")


def _resolve_literal(elem: str) -> str:
    """Resolve a WHOLE argv element that is a bare home/env reference, so the
    rendered command never relies on the shell to expand ~/$HOME/$SHELL/$USER
    (CLAUDE.md invariant #5). Only exact-match elements are resolved — a '$' as
    a substring of some other token is left untouched, so this can't corrupt a
    pattern. Used for KB base_argv literals like ``cd ~`` and ``printf $SHELL``.
    """
    if elem in ("~", "$HOME"):
        return _home()
    if elem == "$SHELL":
        return os.environ.get("SHELL", "/bin/sh")
    if elem == "$USER":
        return os.environ.get("USER") or os.environ.get("LOGNAME", "")
    return elem


def _resolve_path(value: str) -> str:
    """Resolve $HOME / leading ~ to an absolute path. '.' and others pass
    through unchanged (so a plain cwd search stays '.')."""
    home = _home()
    if value == "~":
        return home
    if value.startswith("~/"):
        return home + value[1:]
    if value == "$HOME":
        return home
    if value.startswith("$HOME/"):
        return home + value[len("$HOME"):]
    return value


def _lookup(intent: str) -> dict:
    for cap in load_kb().values():
        intents = cap.get("intents", {})
        if intent in intents:
            return intents[intent]
    raise PlanError(f"no capability provides intent {intent!r}")


def risk_ops(intent: str) -> list[str]:
    """The declared ``risk_ops`` for an intent (from the KB), for the gate.
    Empty list if the intent declares none (treated as read-only)."""
    return list(_lookup(intent).get("risk_ops", []))


def _resolved_slots(frame: Frame) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, val in frame.slots.items():
        if isinstance(val, Raw):
            resolved[key] = val  # a trusted glob — no ~/$HOME resolution, keep Raw
        elif key == "path":
            resolved[key] = _resolve_path(str(val))
        else:
            resolved[key] = str(val)
    return resolved


def _substitute(element: str, slots: dict[str, str]) -> str:
    for key, val in slots.items():
        element = element.replace("{" + key + "}", val)
    return element


def _build_stage(base: list, optional: dict, frame: Frame, slots: dict) -> list[str]:
    # A whole element that resolves exactly to a Raw (glob) slot value stays Raw,
    # so render emits it unquoted (and the shell expands it). A glob only ever
    # occupies a whole element ("{path}"/"{archive}"), never a fragment.
    raw_vals = {str(v) for v in slots.values() if isinstance(v, Raw)}

    def _sub(elem: str) -> str:
        out = _resolve_literal(_substitute(elem, slots))
        return Raw(out) if out in raw_vals else out

    argv: list[str] = [_sub(elem) for elem in base]
    # Append optional fragments in KB-declared order, only for slots present.
    # Iterating the KB (not the frame) fixes the flag order deterministically.
    for slot_key, fragment in optional.items():
        if slot_key in frame.slots:
            argv.extend(_sub(elem) for elem in fragment)
    for elem in argv:
        if _PLACEHOLDER_RE.search(elem):
            raise PlanError(f"unresolved placeholder in argv element {elem!r}")
    return argv


def compile(frame: Frame) -> list[str] | list[list[str]]:
    """Compile a frame to a typed argv list, or — for a piped intent (one with
    ``pipe_argv`` in its KB spec) — a LIST OF argv lists, one per stage. The
    ``|`` itself is never a slot or an argv element; the renderer inserts it
    between stages. Each stage independently satisfies the one-slot-one-element
    and no-surviving-placeholder invariants.
    """
    if frame is None:
        raise PlanError("cannot compile a None frame")

    intent_spec = _lookup(frame.intent)
    slots = _resolved_slots(frame)

    stage1 = _build_stage(
        intent_spec["base_argv"], intent_spec.get("optional_args", {}), frame, slots
    )

    # Extra stages are declared as a `|` pipe chain (`pipe_argv`, `pipe2_argv`,
    # `pipe3_argv` in order) OR a single `&&` stage (`and_argv`). The operator
    # is fixed by the KB spec here, never by a slot value. Each stage is built
    # independently so it round-trips and no slot can inject a `|`/`&&`.
    pipe_stages: list[list[str]] = []
    for key in ("pipe_argv", "pipe2_argv", "pipe3_argv"):
        spec = intent_spec.get(key)
        if spec is not None:
            opt = intent_spec.get(key.replace("_argv", "_optional_args"), {})
            pipe_stages.append(_build_stage(spec, opt, frame, slots))
    if pipe_stages:
        return Stages([stage1, *pipe_stages], "|")

    and_spec = intent_spec.get("and_argv")
    if and_spec is not None:
        stage2 = _build_stage(
            and_spec, intent_spec.get("and_optional_args", {}), frame, slots
        )
        return Stages([stage1, stage2], "&&")

    return stage1
