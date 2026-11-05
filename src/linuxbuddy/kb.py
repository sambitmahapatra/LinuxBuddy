"""Knowledge-base loader for LinuxBuddy command specs.

Reads the YAML command files under ``kb/commands`` and exposes capabilities.

Runtime invariant (CLAUDE.md): pure Python + stdlib only — no PyYAML. The
command files are therefore written in a small, well-defined YAML subset that
``_parse_yaml`` below understands:

  * block mappings nested by (space) indentation, e.g. ``key:`` then indented
    children;
  * ``key: value`` scalars on one line;
  * flow sequences on one line, e.g. ``["a", "b"]``;
  * scalars may be single/double quoted or plain;
  * ``#`` begins a comment only at the start of a (stripped) line, and blank
    lines are ignored.

This is deliberately NOT a general YAML parser. It is enough for the command
specs and nothing more.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

__all__ = ["load_kb", "get_capability", "KBError"]


class KBError(ValueError):
    """Raised when a command spec is malformed."""


# --------------------------------------------------------------------------
# Minimal YAML-subset parser (stdlib only)
# --------------------------------------------------------------------------


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _split_top_level_commas(s: str) -> list[str]:
    """Split on commas that are OUTSIDE quotes.

    Needed so a quoted item that itself contains commas stays intact, e.g.
    ``ps -o "pid,ppid,stat"`` or ``ps -eo "pid,comm,%cpu"``.
    """
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for ch in s:
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _parse_flow_list(text: str) -> list[str]:
    """Parse ``[a, "b c", 'd', "x,y,z"]`` into a list of strings.

    Commas inside a quoted item do not split it (see
    :func:`_split_top_level_commas`), so an ``-o`` field list like
    ``"pid,ppid,stat"`` survives as one element.
    """
    inner = text.strip()
    assert inner.startswith("[") and inner.endswith("]")
    inner = inner[1:-1].strip()
    if not inner:
        return []
    return [_unquote(part) for part in _split_top_level_commas(inner)]


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text.startswith("["):
        return _parse_flow_list(text)
    return _unquote(text)


def _content_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(raw.rstrip())
    return out


def _parse_block(lines: list[str], index: int) -> tuple[dict, int]:
    """Parse a block mapping starting at ``lines[index]``.

    Returns the mapping and the index of the first line that does not belong
    to this block (i.e. is dedented past the block's indent).
    """
    result: dict[str, Any] = {}
    block_indent: int | None = None

    while index < len(lines):
        line = lines[index]
        cur_indent = _indent_of(line)

        if block_indent is None:
            block_indent = cur_indent
        if cur_indent < block_indent:
            break
        if cur_indent > block_indent:
            raise KBError(f"unexpected indentation: {line!r}")

        key, sep, val = line.strip().partition(":")
        if not sep:
            raise KBError(f"expected 'key: value' mapping line: {line!r}")
        key = key.strip()
        val = val.strip()
        index += 1

        if val == "":
            # Nested block mapping, if the next content line is deeper.
            if index < len(lines) and _indent_of(lines[index]) > block_indent:
                child, index = _parse_block(lines, index)
                result[key] = child
            else:
                result[key] = {}
        else:
            result[key] = _parse_scalar(val)

    return result, index


def _parse_yaml(text: str) -> dict:
    lines = _content_lines(text)
    if not lines:
        return {}
    data, _ = _parse_block(lines, 0)
    return data


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def _validate_argv(where: str, argv: Any) -> None:
    if not isinstance(argv, list):
        raise KBError(f"{where}: expected a list, got {type(argv).__name__}")
    for elem in argv:
        if not isinstance(elem, str):
            raise KBError(f"{where}: argv element {elem!r} is not a string")


def _validate_capability(cap: dict, source: str) -> None:
    name = cap.get("capability")
    if not name:
        raise KBError(f"{source}: spec has no 'capability' name")
    intents = cap.get("intents")
    if not isinstance(intents, dict) or not intents:
        raise KBError(f"{source}: capability {name!r} has no intents")
    for intent_name, intent in intents.items():
        if not isinstance(intent, dict):
            raise KBError(f"{source}: intent {intent_name!r} is not a mapping")
        _validate_argv(f"{name}/{intent_name}/base_argv", intent.get("base_argv"))
        optional = intent.get("optional_args", {})
        if not isinstance(optional, dict):
            raise KBError(f"{source}: {intent_name} optional_args is not a mapping")
        for slot, fragment in optional.items():
            _validate_argv(f"{name}/{intent_name}/optional_args/{slot}", fragment)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def _kb_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    # Resolve relative to the repo root (two levels up from this file:
    # src/linuxbuddy/kb.py -> repo root), falling back to the cwd.
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / p
    if candidate.exists():
        return candidate
    return p


def load_kb(path: str | os.PathLike = "kb/commands") -> dict[str, dict]:
    """Load every ``*.yaml`` command spec under ``path``.

    Returns a mapping of capability name -> capability dict. Raises
    :class:`KBError` on a malformed spec.
    """
    directory = _kb_dir(path)
    if not directory.is_dir():
        raise KBError(f"kb directory not found: {directory}")

    capabilities: dict[str, dict] = {}
    for yaml_file in sorted(directory.glob("*.yaml")):
        cap = _parse_yaml(yaml_file.read_text(encoding="utf-8"))
        _validate_capability(cap, yaml_file.name)
        capabilities[cap["capability"]] = cap
    return capabilities


def get_capability(name: str, path: str | os.PathLike = "kb/commands") -> dict:
    """Return the capability dict named ``name``.

    Raises :class:`KeyError` if the capability is not present.
    """
    kb = load_kb(path)
    return kb[name]  # KeyError propagates, as specified.
