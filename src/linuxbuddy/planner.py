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

__all__ = ["compile", "PlanError"]

_PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")


class PlanError(ValueError):
    """Raised when a frame cannot be compiled into a complete argv."""


def _home() -> str:
    return os.environ.get("HOME") or os.path.expanduser("~")


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


def _resolved_slots(frame: Frame) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, val in frame.slots.items():
        if key == "path":
            resolved[key] = _resolve_path(str(val))
        else:
            resolved[key] = str(val)
    return resolved


def _substitute(element: str, slots: dict[str, str]) -> str:
    for key, val in slots.items():
        element = element.replace("{" + key + "}", val)
    return element


def _build_stage(base: list, optional: dict, frame: Frame, slots: dict) -> list[str]:
    argv: list[str] = [_substitute(elem, slots) for elem in base]
    # Append optional fragments in KB-declared order, only for slots present.
    # Iterating the KB (not the frame) fixes the flag order deterministically.
    for slot_key, fragment in optional.items():
        if slot_key in frame.slots:
            argv.extend(_substitute(elem, slots) for elem in fragment)
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

    pipe_argv = intent_spec.get("pipe_argv")
    if pipe_argv is None:
        return stage1

    stage2 = _build_stage(
        pipe_argv, intent_spec.get("pipe_optional_args", {}), frame, slots
    )
    return [stage1, stage2]
