"""Rule-based NLU for the file_discovery domain.

Pure rules + regex. No machine learning, no network, no model (CLAUDE.md
invariant). ``parse`` turns a natural-language request into a :class:`Frame`
or returns ``None`` to abstain.

Abstention is a feature: on vague input ("clean up my files") we return
``None`` rather than guess a command.

----------------------------------------------------------------------------
Vague-"big" resolution (required by Task 02)
----------------------------------------------------------------------------
"big files in downloads" names a size *intent* but no threshold. We resolve
it to ``find_by_size`` WITHOUT a ``size_bytes`` slot, rather than abstaining,
because:
  * the user clearly expressed a size-ordered goal (unlike "clean up my
    mess", which expresses no capability at all), and
  * the test for this row asserts a resolved ``path`` slot, which only
    exists if a Frame is produced.
The downstream planner can then either list candidates or prompt for a
threshold; the frame faithfully records "size intent, threshold unknown".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["Frame", "parse"]


@dataclass
class Frame:
    intent: str
    slots: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Size
# --------------------------------------------------------------------------

_KB = 1024
_MB = 1048576          # MiB (binary units, per spec)
_GB = 1073741824       # GiB

# Units ordered longest-first so regex alternation prefers "megs" over "m".
_SIZE_UNITS: list[tuple[str, int]] = [
    ("gigabytes", _GB), ("gigabyte", _GB), ("gigs", _GB), ("gig", _GB),
    ("gib", _GB), ("gb", _GB), ("g", _GB),
    ("megabytes", _MB), ("megabyte", _MB), ("megs", _MB), ("meg", _MB),
    ("mib", _MB), ("mb", _MB), ("m", _MB),
    ("kilobytes", _KB), ("kilobyte", _KB), ("kib", _KB), ("kb", _KB),
    ("k", _KB),
]
_SIZE_MULT = {unit: mult for unit, mult in _SIZE_UNITS}
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(" + "|".join(u for u, _ in _SIZE_UNITS) + r")\b",
    re.IGNORECASE,
)

# Bare magnitude words that signal size-intent with no numeric threshold.
_SIZE_CUE_RE = re.compile(
    r"\b(big|bigger|biggest|large|larger|largest|huge|small|smaller|tiny)\b",
    re.IGNORECASE,
)


def _detect_size(text: str) -> tuple[int | None, bool]:
    """Return (size_bytes_or_None, size_cue_present)."""
    m = _SIZE_RE.search(text)
    if m:
        number = float(m.group(1))
        mult = _SIZE_MULT[m.group(2).lower()]
        return int(number * mult), True
    if _SIZE_CUE_RE.search(text):
        return None, True
    return None, False


# --------------------------------------------------------------------------
# Time -> days (for find -mtime -N)
# --------------------------------------------------------------------------

_DAYS_RE = re.compile(r"(\d+)\s*days?\b", re.IGNORECASE)
_WEEKS_RE = re.compile(r"(\d+)\s*weeks?\b", re.IGNORECASE)
_HOURS_RE = re.compile(r"(\d+)\s*(?:hours?|hrs?|h)\b", re.IGNORECASE)


def _detect_time(text: str) -> int | None:
    m = _DAYS_RE.search(text)
    if m:
        return int(m.group(1))
    m = _WEEKS_RE.search(text)
    if m:
        return int(m.group(1)) * 7
    m = _HOURS_RE.search(text)
    if m:
        hours = int(m.group(1))
        return max(1, round(hours / 24))
    if re.search(r"\b(today|yesterday|last 24 hours|past 24 hours)\b", text):
        return 1
    if re.search(r"\b(this|last|past)\s+week\b", text):
        return 7
    return None


# --------------------------------------------------------------------------
# Extension / file type
# --------------------------------------------------------------------------

_LANG_TO_EXT = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "markdown": "md",
    "text": "txt",
    "shell": "sh",
    "notebook": "ipynb",
}

_KNOWN_EXTS = {
    "csv", "tsv", "json", "jsonl", "log", "txt", "py", "js", "ts", "md",
    "yaml", "yml", "xml", "html", "ini", "cfg", "conf", "toml", "sh",
    "parquet", "pkl", "pickle", "ipynb", "png", "jpg", "jpeg", "pdf",
    "gz", "tar", "zip", "sql", "env",
}

_DOT_EXT_RE = re.compile(r"\*?\.([a-z0-9]+)\b", re.IGNORECASE)
_WORD_FILES_RE = re.compile(r"\b([a-z0-9+]{1,12})\s+files?\b", re.IGNORECASE)


def _normalize_ext(word: str) -> str | None:
    w = word.lower()
    if w in _LANG_TO_EXT:
        return _LANG_TO_EXT[w]
    if w in _KNOWN_EXTS:
        return w
    return None


def _detect_ext(text: str) -> str | None:
    # 1. explicit "*.ext" or ".ext"
    m = _DOT_EXT_RE.search(text)
    if m:
        ext = _normalize_ext(m.group(1))
        if ext:
            return ext
        return m.group(1).lower()  # trust an explicit dotted extension
    # 2. "<word> files" where <word> is a known ext or language
    m = _WORD_FILES_RE.search(text)
    if m:
        ext = _normalize_ext(m.group(1))
        if ext:
            return ext
    # 3. a bare known extension token anywhere
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        ext = _normalize_ext(tok)
        if ext:
            return ext
    return None


# --------------------------------------------------------------------------
# Name / pattern
# --------------------------------------------------------------------------

_CALLED_RE = re.compile(r"\b(?:called|named)\s+([^\s]+)", re.IGNORECASE)
_QUOTED_RE = re.compile(r"""['"]([^'"]+)['"]""")


def _detect_name(text: str) -> str | None:
    m = _QUOTED_RE.search(text)
    if m:
        return m.group(1)
    m = _CALLED_RE.search(text)
    if m:
        return m.group(1).strip(".,!?;:")
    return None


# --------------------------------------------------------------------------
# Path
# --------------------------------------------------------------------------

_NAMED_DIRS = {
    "downloads": "$HOME/Downloads",
    "documents": "$HOME/Documents",
    "desktop": "$HOME/Desktop",
    "home": "$HOME",
}
# a token that looks like a filesystem path
_PATH_TOKEN_RE = re.compile(r"(?:^|\s)((?:~|\.{1,2})?/[^\s]+|/[^\s]+)")


def _detect_path(text: str, low: str) -> str:
    if re.search(r"\b(here|this (?:folder|directory)|current (?:folder|directory))\b", low):
        return "."
    for name, resolved in _NAMED_DIRS.items():
        if re.search(rf"\b{name}\b", low):
            return resolved
    m = _PATH_TOKEN_RE.search(text)
    if m:
        return m.group(1)
    return "."


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def parse(text: str) -> Frame | None:
    if not text or not text.strip():
        return None
    low = text.lower()

    ext = _detect_ext(low)
    size_bytes, size_cue = _detect_size(low)
    days = _detect_time(low)
    pattern = _detect_name(text)
    path = _detect_path(text, low)

    slots: dict = {"path": path}
    if ext is not None:
        slots["ext"] = ext

    # Intent precedence: size -> time -> name -> type -> abstain.
    if size_cue:
        if size_bytes is not None:
            slots["size_bytes"] = size_bytes
        return Frame("find_by_size", slots)
    if days is not None:
        slots["days"] = days
        return Frame("find_by_time", slots)
    if pattern is not None:
        slots["pattern"] = pattern
        return Frame("find_by_name", slots)
    if ext is not None:
        return Frame("find_by_type", slots)
    return None
