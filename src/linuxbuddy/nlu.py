"""Rule-based NLU for the file_discovery domain.

Pure rules + regex. No machine learning, no network, no model (CLAUDE.md
invariant). ``parse`` turns a natural-language request into a :class:`Frame`
or returns ``None`` to abstain.

Abstention is ASYMMETRIC by risk (CLAUDE.md invariant #6, revised Task 20):
read-only intents lean toward emitting a reasonable command (defaults, glob-
resolved references) — a wrong `grep`/`find` is cheap and editable, and an
abstain that sends a Linux-new user back to Google is itself a failure. We
abstain on a read only when no operation is named at all ("clean up my files").
Destructive intents keep the strict bar: an unclear target/mode refuses, because
a wrong `rm`/`chmod`/`kill` is a disaster.

----------------------------------------------------------------------------
Abstention gate (Task 05, P1.1) — supersedes the old vague-"big" rule
----------------------------------------------------------------------------
An intent is emitted ONLY when its defining slot is present:
  * ``find_by_size`` needs ``size_bytes``,
  * ``find_by_time`` needs ``days``,
  * ``find_by_name`` needs ``pattern``.
A size cue with no number used to abstain to avoid a match-everything bare
``find . -type f``. That rule still holds for ``find_by_size`` (a thresholdless
``-size`` filter is meaningless), BUT a size SUPERLATIVE ("biggest files", "big
files in downloads") now routes to ``find_largest`` (Task 19) — a BOUNDED
``find | sort -rn | head`` — instead of abstaining. So the defining-slot gate
below still governs find_by_size/time/name; superlatives are handled before it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .render import Raw

__all__ = ["Frame", "parse", "abstain_hint"]


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
# Direction for a numeric size threshold (E042): "under/less/smaller" → -N,
# otherwise +N. The sign is chosen HERE, not hardcoded in the KB.
_SIZE_UNDER_RE = re.compile(
    r"\b(?:under|below|less than|smaller than|at most|no (?:more|bigger|larger) than"
    r"|up to|within|tinier than)\b",
    re.IGNORECASE,
)


def _size_sign(low: str) -> str:
    return "-" if _SIZE_UNDER_RE.search(low) else "+"

# Age superlatives that signal time-intent with no numeric window. Like the
# size superlatives, these abstain-with-a-hint rather than guess a window.
_TIME_CUE_RE = re.compile(
    r"\b(oldest|newest|latest|most recent|recent)\b",
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


_MIN_NUM_WORDS = {"an": 1, "a": 1, "one": 1, "two": 2, "three": 3, "half an": 0}


def _detect_minutes(low: str) -> int | None:
    """A sub-day recency window in MINUTES (for `find -mmin`), or None.
    "last hour"→60, "last 30 minutes"→30, "past 2 hours"→120 (E039)."""
    m = re.search(r"\b(?:last|past|within|in\s+the\s+last)\s+(\d+)\s*min", low)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:last|past|within|in\s+the\s+last)\s+(\d+)\s*(?:hours?|hrs?)\b", low)
    if m and int(m.group(1)) < 24:  # >=24h is days territory (-mtime), not -mmin
        return int(m.group(1)) * 60
    if re.search(r"\b(?:last|past|within|this)\s+(?:the\s+)?(?:an?\s+)?hour\b", low):
        return 60
    if re.search(r"\blast\s+half\s+hour\b|\bpast\s+half\s+hour\b", low):
        return 30
    return None


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
    # Task 23 (E016): a bare recency cue with no number → a sensible default
    # window (7 days), so "recently modified logs" keeps its -mtime instead of
    # dropping the time part and degrading to a plain find-by-type.
    if re.search(r"\b(recently|lately|recent)\b", text):
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

# Plural / possessive file-type words that do not singularize cleanly by just
# dropping a trailing "s" (Task 05, bug 2). Explicit and small on purpose —
# this is a lookup, not a stemmer. "images" is deliberately absent: it is
# ambiguous (png? jpg? all of them?) and must NOT map to an extension.
_PLURAL_EXT = {
    "csvs": "csv",
    "logs": "log",
    "pys": "py",
    "jsons": "json",
    "notebooks": "ipynb",
    "scripts": "sh",
}


def _normalize_ext(word: str) -> str | None:
    w = word.lower()
    if w in _LANG_TO_EXT:
        return _LANG_TO_EXT[w]
    if w in _KNOWN_EXTS:
        return w
    if w in _PLURAL_EXT:
        return _PLURAL_EXT[w]
    # Trailing-s fallback: singularize once and retry the known maps. This
    # catches "tsvs" -> tsv, "pdfs" -> pdf without an entry each. It stays a
    # single-character strip, never a real stemmer.
    if len(w) > 1 and w.endswith("s"):
        singular = w[:-1]
        if singular in _LANG_TO_EXT:
            return _LANG_TO_EXT[singular]
        if singular in _KNOWN_EXTS:
            return singular
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
# Task 23 (E018): a concrete "name.ext" in the request is an EXACT filename, not
# a type glob. The extension must start with a letter so a version like "3.11"
# isn't mistaken for a file.
_BARE_FILE_RE = re.compile(r"\b([\w-]+\.[a-z][a-z0-9]{0,7})\b", re.IGNORECASE)


def _detect_name(text: str) -> str | None:
    m = _QUOTED_RE.search(text)
    if m:
        return m.group(1)
    m = _CALLED_RE.search(text)
    if m:
        return m.group(1).strip(".,!?;:")
    m = _BARE_FILE_RE.search(text)
    if m:
        return m.group(1)
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


# find_largest (Task 19): superlative size, no threshold. "biggest/largest/top
# N files / most space / by size". The large-direction size cues (big/huge/...)
# with no numeric threshold are superlatives too → find_largest, not an abstain.
_FLARGE_RE = re.compile(
    r"\btop\s+\d+\b|\b\d+\s+(?:largest|biggest)\b|\bmost\s+space\b"
    r"|\btaking\s+up\s+(?:the\s+)?most\b|\bmost\s+disk\b|\bby\s+size\b",
    re.IGNORECASE,
)
_LARGE_DIR_RE = re.compile(
    r"\b(?:big|bigger|biggest|large|larger|largest|huge|enormous|massive)\b",
    re.IGNORECASE,
)
_SMALL_DIR_RE = re.compile(
    r"\b(?:small|smaller|smallest|tiny|tiniest|littlest)\b", re.IGNORECASE,
)
_FLARGE_COUNT_RE = re.compile(
    r"\btop\s+(\d+)\b|\bbiggest\s+(\d+)\b|\blargest\s+(\d+)\b"
    r"|\b(\d+)\s+(?:largest|biggest)\b", re.IGNORECASE,
)
_COMMON_DIRS = {
    "data", "src", "source", "logs", "log", "downloads", "documents", "desktop",
    "exports", "results", "configs", "config", "tests", "scripts", "build",
    "backups", "archives", "project", "runs", "notebooks", "tmp", "home",
}


def _flarge_count(low: str) -> int:
    m = _FLARGE_COUNT_RE.search(low)
    if m:
        return int(next(g for g in m.groups() if g))
    return 10


def _largest_path(text: str, low: str) -> str:
    m = re.search(r"\b([\w.-]+)\s+(?:folder|directory|dir)\b", low)
    if m and m.group(1).lower() not in _ARTICLES:
        return m.group(1)
    p = _detect_path_arg(text, low)
    if p is not None:
        return p
    m = re.search(r"\b(?:in|under|inside|within)\s+(?:the\s+)?([\w./-]+)", low)
    if m and m.group(1).lower() in _COMMON_DIRS:
        return m.group(1)
    return "."


# --------------------------------------------------------------------------
# Coverage-check (Task 42, workstream #1a). A bare filename must NOT hijack the
# request into a `find -name <file>` when the user actually asked for some other
# operation the rules can't route (stat/delete/sort/run/…). Require positive
# evidence that discovery/search was asked; otherwise abstain, so the encoder
# fallback (cli seam) gets the request instead of a confident wrong `find`.
# Pure wording signal — independent of what was extractable.
# --------------------------------------------------------------------------
_DISCOVERY_CUE_RE = re.compile(
    r"\b(?:find|finding|locate|locating|search(?:ing)?|grep|list(?:ing)?|where|"
    r"which|look\s+for|look\s+up|how\s+many|named|called|files)\b",
    re.IGNORECASE,
)


def _discovery_requested(text: str, low: str) -> bool:
    """True when the request actually asked to find/search/list: a discovery
    verb/phrase, the plural 'files', a glob, or a size/time constraint."""
    if _DISCOVERY_CUE_RE.search(low):
        return True
    if "*" in text:
        return True
    _, size_cue = _detect_size(low)
    return bool(size_cue or _TIME_CUE_RE.search(low))


def _parse_file_discovery(text: str, low: str) -> Frame | None:
    ext = _detect_ext(low)
    size_bytes, size_cue = _detect_size(low)
    minutes = _detect_minutes(low)
    days = _detect_time(low)
    pattern = _detect_name(text)
    path = _detect_path(text, low)

    slots: dict = {"path": path}
    if ext is not None:
        slots["ext"] = ext

    # find_largest: an explicit superlative cue, OR a large-direction size cue
    # with no numeric threshold ("biggest files", "which files are huge").
    # A real threshold ("over 100mb") sets size_bytes → stays find_by_size.
    # Superlatives need NO numeric threshold (that's the point). Gate on the
    # direction cue + a plural/space context, and only when no explicit
    # threshold was given (a real "over 100mb" stays find_by_size below).
    if _FLARGE_RE.search(low) or (
        size_bytes is None and _LARGE_DIR_RE.search(low)
        and re.search(r"\bfiles\b|\bspace\b|\bdisk\b", low)
    ):
        return Frame("find_largest",
                     {"path": _largest_path(text, low), "count": _flarge_count(low)})
    # Task 20: the smallest-direction twin → find_smallest (ascending sort).
    if size_bytes is None and _SMALL_DIR_RE.search(low) and "files" in low:
        return Frame("find_smallest",
                     {"path": _largest_path(text, low), "count": _flarge_count(low)})
    # Task 20: "open <file>" used to mis-route to a find-by-name/type (searched
    # instead of acting on the named file). "open" is ambiguous on WSL and a
    # reliable action needs nested $() (deferred), so abstain cleanly rather than
    # emit a wrong command.
    if re.search(r"\bopen\b", low):
        return None

    # Task 27 (E045/E046): "how many csv files" / "count the python files" → a
    # file-count (find … | wc -l), not a per-file line-count. Needs a count cue
    # plus a file-type or a bare "files"; a count of log WORDS was already taken
    # by text_and_logs, and a per-file line-count by file_inspection.
    if re.search(r"\bhow many\b|\bcount\b", low) and (
        ext is not None or re.search(r"\bfiles\b", low)
    ):
        cslots: dict = {"path": path}
        if ext is not None:
            cslots["ext"] = ext
        return Frame("count_files", cslots)

    # Task 27 (E039): a sub-day recency window → `find -mmin -N` (minutes).
    # Checked before days so "last 2 hours" uses -mmin, not a coarse -mtime.
    if minutes is not None:
        mslots: dict = {"path": path, "minutes": str(minutes)}
        if ext is not None:
            mslots["ext"] = ext
        return Frame("find_recent", mslots)

    # Intent precedence: size -> time -> name -> type -> abstain.
    #
    # Abstention gate (Task 05, CLAUDE.md invariant #6): an intent is only
    # emitted when its DEFINING slot is present. A size cue with no numeric
    # threshold ("biggest files") would compile to a match-everything
    # `find . -type f`, so we abstain instead of dropping the slot silently.
    if size_cue:
        if size_bytes is None:
            return None  # size intent, no threshold -> abstain (see hint)
        # E042: sign the threshold by direction ("under 1kb" → -1024c).
        slots["size_bytes"] = f"{_size_sign(low)}{size_bytes}"
        return Frame("find_by_size", slots)
    if days is not None:
        slots["days"] = days
        return Frame("find_by_time", slots)
    if pattern is not None:
        # Coverage-check (Task 42, #1a): a bare filename alone is NOT a find
        # request. Emit find_by_name only when discovery/search was actually asked
        # for; otherwise abstain, so the encoder fallback (cli seam) gets the real
        # intent (stat/delete/run/…) instead of a confident wrong `find -name`.
        if not _discovery_requested(text, low):
            return None
        slots["pattern"] = pattern
        return Frame("find_by_name", slots)
    if ext is not None:
        return Frame("find_by_type", slots)
    return None


# --------------------------------------------------------------------------
# Router (Phase 2) — pick the domain/intent, then the right slot extractor.
#
# Each domain parser returns a Frame (matched), ``None`` (not my domain, try
# the next), or the ``_ABSTAIN`` sentinel (this IS my domain but the request
# is compound / underspecified — stop and abstain, do NOT let a later domain
# guess at one fragment of it). file_discovery stays LAST so a bare extension
# ("json") still routes to find_by_type.
# --------------------------------------------------------------------------

_ABSTAIN = object()


def parse(text: str) -> Frame | None:
    if not text or not text.strip():
        return None
    low = text.lower()
    for domain_parser in _ROUTER:
        result = domain_parser(text, low)
        if result is _ABSTAIN:
            return None
        if result is not None:
            return result
    return None


# --------------------------------------------------------------------------
# Shared: a concrete file/path argument (quoted, slash-path, or bare NAME.ext)
# --------------------------------------------------------------------------

# A bare filename with an extension: train.log, config.yaml, data.bin,
# model.pt, access.log, src/app.py. The extension must start with a letter so
# a decimal like "3.14" is not mistaken for a file.
_FILE_TOKEN_RE = re.compile(r"\b([\w./+-]*\w\.[A-Za-z][A-Za-z0-9]{0,7})\b")


# --------------------------------------------------------------------------
# Definite-reference resolution (Task 22) — the #1 eval fix.
#
# Users say "the log", "the backup", "the config" — a definite reference, not a
# filename. The intent is recognised but there's no path, so the planner used to
# abstain. When the reference implies a FILE TYPE, resolve it to a GLOB
# (returned as render.Raw so it's emitted UNQUOTED and the user's shell expands
# it): "show errors in the log" → grep -niF -- error *.log.
#
# Subdirectory choice (documented): a bare glob matches the CWD only. In the
# maze, logs live in logs/, so `*.log` from the project root may match nothing —
# that's accepted: a command the user can edit beats an abstain (per Task 22 and
# invariant #6). We do NOT force every search recursive.
#
# GENERIC references with no implied type ("this file", "the file", "this list",
# "these names") have no glob to resolve to → they KEEP abstaining. That ~10-row
# residual is the documented motivation for the v2 attention model.
# --------------------------------------------------------------------------

_DEFINITE_GLOBS = [
    # Task 32: allow an adjective before "logs" ("the OLD logs" → *.log) so a
    # delete/move of them resolves instead of abstaining.
    (re.compile(r"\bthe\s+log\s+file\b|\bthe\s+(?:old\s+)?logs?\b|\bthis\s+log\b|\bmy\s+logs?\b"), "*.log"),
    # Task 32: "the image/picture/photo" → an image glob. The brace list is a
    # trusted Raw (safe charset), emitted unquoted so the shell expands it.
    (re.compile(r"\bthe\s+(?:image|picture|photo)\b|\bthis\s+(?:image|picture|photo)\b"), "*.{jpg,png}"),
    (re.compile(r"\bgzipp?ed\s+(?:archive|file)\b|\bthe\s+gzip\b|\bthe\s+gz\b"), "*.gz"),
    (re.compile(r"\bthe\s+(?:backup|tarball)\b|\bthis\s+(?:backup|tarball)\b|\bmy\s+(?:backup|tarball)\b"), "*.tar.gz"),
    (re.compile(r"\bthe\s+archive\b|\bthis\s+archive\b"), "*.tar.gz"),
    (re.compile(r"\bthe\s+zip\b|\bthis\s+zip\b"), "*.zip"),
    (re.compile(r"\bthe\s+config(?:\s+file)?\b|\bthis\s+config\b|\bmy\s+config\b"), "config.*"),
    (re.compile(r"\bthe\s+csv(?:\s+file)?\b|\bthis\s+csv\b"), "*.csv"),
    # Task 28 (E048): "the readme" / a bare "readme" → the README glob, so
    # "print the readme" previews it instead of abstaining.
    (re.compile(r"\bthe\s+readme\b|\breadme\b"), "README*"),
]
_ARCHIVE_GLOBS = {"*.tar.gz", "*.gz", "*.zip"}


def _definite_glob(low: str):
    """A typed definite reference → a shell glob (render.Raw), or None."""
    for rx, g in _DEFINITE_GLOBS:
        if rx.search(low):
            return Raw(g)
    return None


def _detect_path_arg(text: str, low: str) -> str | None:
    """A concrete file/dir the request names, or a typed definite-reference glob
    (Task 22), or None. Prefers an explicit quote, then a slash path, then a
    bare ``name.ext``, then a definite-reference glob."""
    m = _QUOTED_RE.search(text)
    if m:
        return m.group(1)
    m = _PATH_TOKEN_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _FILE_TOKEN_RE.search(text)
    if m:
        return m.group(1)
    return _definite_glob(low)


# --------------------------------------------------------------------------
# Domain: file_inspection (Task 08) — single-command intents only.
# --------------------------------------------------------------------------

_COUNT_LINES_RE = re.compile(
    r"\b(?:how many lines|line count|number of lines|count .* lines)\b"
)
_HEAD_RE = re.compile(
    r"\b(?:head\b|first\s+(?:\d+\s+)?\w*\s*lines?"
    r"|top of|beginning of|column (?:names|headers)|header row)\b"
)
# E054: "last lines of the log" (no number) is a tail cue too.
_TAIL_RE = re.compile(r"\b(?:tail\b|last\s+(?:\d+\s+)?\w*\s*lines?|end of|bottom of)\b")
_SIZE_BYTES_RE = re.compile(
    r"\b(?:in bytes|byte size|size in bytes|how many bytes"
    r"|how big is (?:this|the) file|file size|size of [^?]* in bytes)\b"
)
_TYPE_RE = re.compile(
    r"\b(?:what (?:kind|type) of file|what format|file ?type"
    r"|what (?:kind|type) is|is this (?:a )?(?:text|binary))\b"
)
_STAT_RE = re.compile(
    r"\b(?:when (?:was|were)\b|last (?:modified|changed|changed\?)"
    r"|modification time|timestamp|time stamp|metadata|mod time"
    r"|show (?:the )?stat\b)\b"
)
# a plain "size of X" (no folder) when "in bytes" is not literally present
_SIZE_WORD_RE = re.compile(r"\bsize of\b|\bhow big is\b|\bbyte")
_FOLDER_RE = re.compile(r"\b(?:folder|directory|dir|disk|space)\b")

# count: "first 20", "last 50", "20 lines", "top 5"
_INSPECT_COUNT_RE = re.compile(
    r"\b(?:first|last|top|head|tail)\s+(\d+)\b|\b(\d+)\s+lines?\b", re.IGNORECASE
)


def _inspect_count(low: str) -> int:
    m = _INSPECT_COUNT_RE.search(low)
    if m:
        return int(m.group(1) or m.group(2))
    return 10


def _stat_fmt(low: str) -> str:
    """Pick a stat -c format. Time-focused => %y; permission-focused => %A;
    otherwise a compact metadata line."""
    if re.search(r"\b(permission|perms|mode|access bits)\b", low):
        return "%A %n"
    if re.search(r"\b(when|time|modified|changed|timestamp|mod time)\b", low):
        return "%y %n"
    return "%y %A %s %n"


# Task 25 (E047/E050/E052): "view" cues that mean "show me this file". Broader
# than the Task-23 set, but gated by _VIEW_DEFER_RE below so it can't steal a
# unique/sort/grep/permission/navigation request. "open" stays excluded (Task-20
# abstain); "read" stays excluded (collides with the chmod privacy cue).
_VIEW_CUE_RE = re.compile(
    r"\b(?:print|cat|display|dump|peek(?:\s+at)?|show(?:\s+me)?|view"
    r"|look\s+at|what'?s\s+in\b|what\s+is\s+in\b|contents\s+of)", re.IGNORECASE)
# When any of these is present, the "view" cue defers to the domain that owns it
# (unique/sort → text; perms/owner → filesystem; folder/process → navigation/
# processes; an archive extension → archives list-contents).
_VIEW_DEFER_RE = re.compile(
    r"\b(?:distinct|unique|dedupe|duplicate|sort|alphabetical"
    r"|folder|directory|dir\b|who\s+(?:owns|can)|permission|owner|private"
    r"|processes?|running)\b|\.(?:zip|tar|gz|tgz|tbz2?|bz2|xz)\b", re.IGNORECASE)


def _parse_file_inspection(text: str, low: str):
    # A superlative "top N … by size" belongs to find_largest, not show_size.
    if _FLARGE_RE.search(low):
        return None
    folder = bool(_FOLDER_RE.search(low))
    logword = bool(_LOG_WORD_RE.search(low))
    # E069: "count the warnings" is a grep-count of a log word, not wc -l of all
    # lines — defer the line-count to text_and_logs when a log word is present.
    is_count = bool(_COUNT_LINES_RE.search(low)) and not logword
    is_head = bool(_HEAD_RE.search(low))
    is_tail = bool(_TAIL_RE.search(low))
    is_type = bool(_TYPE_RE.search(low)) or bool(re.search(r"\bformat\b", low))
    is_stat = bool(_STAT_RE.search(low))
    # size of a FILE (in bytes); a folder/disk "size" belongs to filesystem.
    # Word-boundaried so "account", "resize" etc. don't false-trigger.
    is_size = (bool(re.search(r"\b(?:size|bytes)\b", low)) and not folder)

    # Broad action categories, used ONLY to spot a compound request. The
    # literal nouns catch "preview, count and size ..." even though no single
    # precise intent cue fires for all three. Word-boundaried — "account" must
    # not read as "count".
    broad = set()
    if re.search(r"\bpreview\b", low) or is_head or is_tail:
        broad.add("preview")
    # A count of "files" (plural) is a file-DISCOVERY count (find | wc -l),
    # owned by file_discovery (Task 27) — not a per-file line-count. Defer it.
    files_count = bool(re.search(r"\bfiles\b", low))
    if ((re.search(r"\bcount\b", low) and not logword) or is_count) and not files_count:
        broad.add("count")
    if is_size:
        broad.add("size")
    if is_type:
        broad.add("type")
    if is_stat:
        broad.add("stat")

    # Task 25 (E047/E050/E052): a "view" cue ("show me config.yaml", "peek at
    # data.csv", "what's in the log") naming a file → preview it (head/cat),
    # instead of falling through to file_discovery's find. Only when nothing else
    # matched, no log/grep cue, and _VIEW_DEFER_RE (unique/sort/perms/folder/
    # process) does not claim it. "open X" stays a Task-20 abstain.
    vpath = _detect_path_arg(text, low)
    if (not broad and _VIEW_CUE_RE.search(low)
            and not logword
            and not _VIEW_DEFER_RE.search(low)
            and vpath is not None
            # "… files" (plural) is a listing → file_discovery, not a preview (E027).
            and not re.search(r"\bfiles\b", low)
            # an archive definite-ref ("the zip/tarball") → archives list (E126).
            and str(vpath) not in _ARCHIVE_GLOBS):
        broad.add("preview")

    if not broad:
        return None  # not a file_inspection request — let the next domain try

    # Compound: several distinct asks → abstain rather than answering one of
    # them silently (CLAUDE.md invariant #6). "multi-step" is later work.
    if len(broad) >= 2:
        return _ABSTAIN

    (category,) = tuple(broad)
    path = _detect_path_arg(text, low)
    slots: dict = {}
    if path is not None:
        slots["path"] = path

    if category == "count":
        return Frame("count_lines", slots)
    if category == "size":
        return Frame("show_size", slots)
    if category == "type":
        return Frame("detect_type", slots)
    if category == "stat":
        slots["fmt"] = _stat_fmt(low)
        return Frame("show_stat", slots)
    # preview: tail if an "end/last" cue, else head
    slots["count"] = _inspect_count(low)
    return Frame("preview_tail" if is_tail and not is_head else "preview_head", slots)


# --------------------------------------------------------------------------
# Domain: text_and_logs (Task 09) — grep + sort, read-only.
# --------------------------------------------------------------------------

# Log-level / marker words; a bare mention implies a case-insensitive search
# for the canonical form. "errors" -> "error", "warnings" -> "warning".
_LOG_WORD_RE = re.compile(
    r"\b(errors?|warnings?|exceptions?|traceback|failed|failure|timeouts?"
    r"|critical|deprecated)\b", re.IGNORECASE,
)
_LOG_CANON = {
    "error": "error", "errors": "error", "warning": "warning",
    "warnings": "warning", "exception": "exception", "exceptions": "exception",
    "traceback": "Traceback", "failed": "failed", "failure": "failed",
    "timeout": "timeout", "timeouts": "timeout", "critical": "critical",
    "deprecated": "deprecated",
}
_CASE_WORDS = {"error", "warning", "exception", "failed", "timeout", "critical"}

_IGNORE_CASE_RE = re.compile(
    r"\b(?:ignore case|case[- ]insensitive|regardless of (?:capitalization|case)"
    r"|any case|whatever the case)\b", re.IGNORECASE,
)
_DISTINCT_RE = re.compile(
    r"\b(?:distinct|unique|dedupe|deduplicate|duplicates removed|without duplicates"
    r"|remove\s+duplicates?|duplicate\s+lines|drop\s+duplicates?)\b",
    re.IGNORECASE,
)
# A grep term in quotes must be WHITESPACE-bounded, so a contraction apostrophe
# ("what's today's date" — E088) is not mistaken for a 'quoted' search term the
# way a real one is ("find 'deprecated'").
_GREP_QUOTE_RE = re.compile(r"""(?:^|\s)(['"])([^'"]+)\1(?=\s|[.,!?;:]|$)""")
_SORT_RE = re.compile(r"\b(?:sort|alphabetical(?:ly)?|in order|ascending)\b", re.IGNORECASE)
_RECURSIVE_RE = re.compile(
    r"\b(?:across|recursiv\w*|everywhere|throughout|in all|all files|every file"
    r"|(?:in|within|under|through)\s+(?:all\s+(?:the\s+)?)?the\s+"
    r"(?:project|repo|repository|codebase|code|source|src|configs?|files))\b",
    re.IGNORECASE,
)
# cwd-synonyms: "the code", "the project", "everywhere" mean "search here,
# recursively" → path ".", NOT a literal subdir named "code" (E065/E070).
_GREP_CWD_SYNONYMS = {"code", "codebase", "project", "repo", "repository",
                      "source", "everything", "everywhere", "here", "files"}
_COUNT_MATCH_RE = re.compile(r"\b(?:how many|how often|count|number of times)\b", re.IGNORECASE)
# Task 28 (E066): a "which lines mention X" / "lines with X" / "lines mentioning
# X" request is a grep. With no file named it defaults to a recursive grep in
# cwd (like E070/E071), not a pathless grep that hangs on stdin.
_LINES_GREP_RE = re.compile(
    r"\bwhich\s+lines\b|\blines\s+(?:that\s+)?(?:mention(?:ing)?s?|with|containing"
    r"|contain|matching|having)\b", re.IGNORECASE,
)

_ALLCAPS_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
# Env-var names (Task 27): a bare one is an env_var query, not a grep pattern.
_ENVVAR_NAMES = {"PATH", "HOME", "PORT", "USER", "SHELL", "PWD", "LANG",
                 "TERM", "EDITOR", "DISPLAY", "GPU_ID", "PID"}
_WORD_PAT_RE = re.compile(
    r"\b(?:the\s+)?(?:word|string|phrase|token|term)\s+['\"]?([A-Za-z0-9_./+-]+)",
    re.IGNORECASE,
)
# NB: "locate" is a DISCOVERY verb (find a file), NOT grep (E035) — kept out.
_SEARCHVERB_RE = re.compile(
    r"\b(?:search for|grep(?:\s+for)?|look for)\s+['\"]?([A-Za-z0-9_./+-]+)",
    re.IGNORECASE,
)
_VAGUE_PAT = {"stuff", "things", "thing", "something", "anything", "it", "them", "that"}
# Task 42: articles/"file" captured by a search verb mean the request is actually
# file-discovery ("look for a file named X"), not a grep for the literal article.
_ARTICLE_WORDS = {"a", "an", "the", "file", "files"}

_DIR_NOUN_RE = re.compile(r"\b([\w./-]+)\s+(?:folder|directory|dir|tree)\b", re.IGNORECASE)
_PREP_DIR_RE = re.compile(
    r"\b(?:across|in|within|under|throughout)\s+(?:the\s+|all\s+(?:the\s+)?)?([\w./-]+)",
    re.IGNORECASE,
)
_KNOWN_DIRS = {
    "src", "source", "configs", "config", "logs", "project", "tests",
    "data", "scripts", "exports", "runs", "repo", "codebase",
}


def _grep_pattern(text: str, low: str) -> str | None:
    m = _GREP_QUOTE_RE.search(text)
    if m:
        return m.group(2)
    m = _WORD_PAT_RE.search(text)
    if m:
        return m.group(1).strip(".,!?;:")
    m = _SEARCHVERB_RE.search(text)
    if m:
        tok = m.group(1).strip(".,!?;:")
        # Task 42: "look for a file named X" is file-discovery, not a grep for the
        # article "a"/"the"/"file" — skip those so the discovery parser handles it.
        if tok.lower() not in _VAGUE_PAT and tok.lower() not in _ARTICLE_WORDS:
            return tok
    m = _ALLCAPS_RE.search(text)   # TODO, FIXME, API_URL, SUCCESS
    if m and m.group(1) not in _ENVVAR_NAMES and text[m.end():m.end() + 1] != ".":
        # A bare env-var name ("what's my PATH") is an env_var query, not a grep
        # for the literal word — leave it for workspace (Task 27). An intentional
        # grep for PATH uses a verb/quote, caught by the branches above.
        # Task 42: an all-caps token that is part of a FILENAME (README.md, API.py)
        # is a file, not a grep pattern — the "." guard above excludes it, so
        # "is there a README.md" no longer hijacks into `grep README`.
        return m.group(1)
    m = _LOG_WORD_RE.search(low)
    # Task 42: a log WORD inside a filename ("error.log", "debug.log") is a file,
    # not a grep pattern — the "." guard stops "delete error.log" → `grep error`.
    if m and low[m.end():m.end() + 1] != ".":
        return _LOG_CANON[m.group(1).lower()]
    return None


def _grep_dir(text: str, low: str) -> str | None:
    m = _DIR_NOUN_RE.search(text)
    if m and m.group(1).lower() not in _GREP_CWD_SYNONYMS:
        return m.group(1)
    m = _PREP_DIR_RE.search(text)
    if m:
        cand = m.group(1)
        if cand.lower() in _GREP_CWD_SYNONYMS:
            return None  # a cwd-synonym → recurse from "." (set by caller)
        if cand.lower() in _KNOWN_DIRS or "." not in cand:
            return cand
    return None


def _parse_text_and_logs(text: str, low: str):
    is_distinct = bool(_DISTINCT_RE.search(low))
    is_sort = bool(_SORT_RE.search(low))
    pattern = _grep_pattern(text, low)

    # sort / unique family (no grep pattern dominating)
    if is_distinct:
        slots: dict = {}
        p = _detect_path_arg(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("unique_lines", slots)
    if is_sort and pattern is None:
        slots = {}
        p = _detect_path_arg(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("sort_lines", slots)

    if pattern is None:
        return None  # not a text-search request — let the next domain try

    # Task 34: a file-copy request can still produce a spurious grep pattern via
    # the all-caps/filename heuristic ("create a copy of MANIFEST.txt" → pattern
    # "MANIFEST"). Checked AFTER distinct/sort (so "remove duplicate lines" stays
    # unique_lines) and only when a pattern exists — defer to the file-copy
    # parser. Mirror its clipboard/windows/mnt guard so a genuine wsl "copy … to
    # clipboard" is left for its own domain.
    if ("clipboard" not in low and "windows" not in low and "/mnt/" not in low
            and _ARC_COPY_RE.search(text)):
        return None

    ic = bool(_IGNORE_CASE_RE.search(low)) or (pattern.lower() in _CASE_WORDS)
    i = "i" if ic else ""

    if _RECURSIVE_RE.search(low):
        slots = {"gflags": "-Rn" + i + "F", "pattern": pattern}
        # E071: a recursive grep with no explicit dir uses cwd ".", NEVER the
        # pattern (the old _detect_path_arg fallback grabbed the quoted pattern).
        d = _grep_dir(text, low)
        slots["path"] = d if d is not None else "."
        return Frame("search_recursive", slots)

    if _COUNT_MATCH_RE.search(low):
        slots = {"gflags": "-c" + i + "F", "pattern": pattern}
        p = _detect_path_arg(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("count_matches", slots)

    slots = {"gflags": "-n" + i + "F", "pattern": pattern}
    p = _detect_path_arg(text, low)
    if p is not None:
        slots["path"] = p
        return Frame("search_in_file", slots)
    # Task 28 (E066): "which lines mention warning" names no file → recursive
    # grep in cwd, consistent with the no-target grep behaviour (E070/E071),
    # instead of a pathless search_in_file that leaves {path} unresolved.
    if _LINES_GREP_RE.search(low):
        return Frame("search_recursive",
                     {"gflags": "-Rn" + i + "F", "pattern": pattern, "path": "."})
    return Frame("search_in_file", slots)


# --------------------------------------------------------------------------
# Domain: processes (Task 10) — read-only intents. kill/pkill abstain.
# --------------------------------------------------------------------------

_KILL_RE = re.compile(r"\b(?:kill|pkill|killall)\b", re.IGNORECASE)
# Task 23 (E060/E062): "stop"/"terminate"/"end" are kill synonyms, but only when
# "process" is in the phrase — so "stop the X process" kills while "stop the
# server" (a different intent) does not get swept in.
_KILL_TRIGGER_RE = re.compile(
    r"\b(?:kill|pkill|killall)\b"
    r"|\b(?:stop|terminate|end)\s+(?:the\s+|this\s+|that\s+)?[\w.+-]+\s+process\b"
    r"|\b(?:stop|terminate|end)\s+(?:the\s+)?process\b",
    re.IGNORECASE,
)
_PORT_RE = re.compile(r"\bport\s+#?(\d{1,5})\b", re.IGNORECASE)
# Task 23 (E056/E058): a port/listening query with NO specific number → list all
# listening sockets rather than abstain.
_LISTENING_RE = re.compile(
    r"\bwhat'?s?\s+(?:on\s+)?(?:my\s+)?ports?\b|\bon\s+(?:my\s+)?ports?\b"
    r"|\bwhat'?s?\s+listening\b|\blistening\s+(?:ports?|sockets?)\b"
    r"|\b(?:open|used)\s+ports?\b|\bports?\s+(?:are\s+)?(?:open|in\s+use|listening)\b",
    re.IGNORECASE,
)
_PID_RE = re.compile(r"\b(?:pid|process id|process)\s+#?(\d{1,7})\b", re.IGNORECASE)
_TOPN_RE = re.compile(
    r"\btop\s+(\d+)\b|\b(\d+)\s+(?:processes|consumers|results)\b", re.IGNORECASE
)
_CPU_RE = re.compile(r"\b(?:cpu|processor)\b", re.IGNORECASE)
_MEM_RE = re.compile(r"\b(?:memory|ram|rss|mem)\b", re.IGNORECASE)
_MOST_RE = re.compile(
    r"\b(?:most|highest|biggest|top|heaviest|eating|hog|hogs|consumers?|heavy)\b",
    re.IGNORECASE,
)
_RUNNING_RE = re.compile(
    r"\b(?:what'?s running|whats running|what is running|everything running"
    r"|all (?:the )?processes|running processes|list (?:the )?processes"
    r"|my processes|show (?:me )?(?:all )?(?:the )?(?:running |my )?processes)\b",
    re.IGNORECASE,
)
_FIND_PROC_RE = re.compile(
    r"\bis\s+(?:the\s+)?([\w.+-]+)\s+(?:process\s+)?(?:running|up|alive|active)\b"
    r"|\bfind\s+(?:the\s+)?([\w.+-]+)\s+process\b"
    r"|\b(?:process|pgrep)\s+(?:named|called|matching|for)\s+([\w.+-]+)\b",
    re.IGNORECASE,
)
# Task 25 (E101): "list/show the <name> processes" → find that process by name
# (pgrep), NOT a file-discovery find. A bare "list the processes" (no name) stays
# list_processes via _RUNNING_RE below.
_PROC_NAMED_LIST_RE = re.compile(
    r"\b(?:list|show)\s+(?:me\s+)?(?:the\s+|all\s+(?:the\s+)?|my\s+)?"
    r"([\w.+-]+)\s+process(?:es)?\b", re.IGNORECASE,
)
_PROC_NAME_STOP = {"running", "all", "my", "background", "these", "those",
                   "the", "active", "live", "other"}


# kill (Task 15): a PID directly after a kill/process word → kill_pid; else a
# process name (named/called/matching X, "kill the X process", "kill X").
_KILL_PID_RE = re.compile(
    r"\b(?:kill|pid|process(?:\s+id)?|proc)\s+#?(\d{1,7})\b", re.IGNORECASE
)
_KILL_PAT_RE = re.compile(
    r"(?:named|called|matching)\s+([\w.+-]+)"
    r"|(?:kill|pkill|killall|stop|terminate|end)\s+(?:the\s+)?([\w.+-]+?)\s+process\b"
    r"|(?:kill|pkill|killall|stop|terminate|end)\s+(?:the\s+|process\s+)?([\w.+-]+)",
    re.IGNORECASE,
)
# generic words that must not become a pkill pattern (would match too much)
_KILL_STOP = {"process", "processes", "the", "it", "this", "that", "them", "task"}


def _top_count(low: str) -> int:
    m = _TOPN_RE.search(low)
    if m:
        return int(m.group(1) or m.group(2))
    return 10


def _kill_pattern(text: str, low: str) -> str | None:
    m = _KILL_PAT_RE.search(text)
    if not m:
        return None
    pat = next(g for g in m.groups() if g)
    if pat.lower() in _KILL_STOP:
        return None
    return pat


def _parse_processes(text: str, low: str):
    # kill / pkill / stop / terminate (Task 15 + 23): destructive, gated to the
    # maze by the P2.0 gate.
    if _KILL_TRIGGER_RE.search(low):
        m = _KILL_PID_RE.search(low)
        if m:
            return Frame("kill_pid", {"pid": int(m.group(1))})
        pat = _kill_pattern(text, low)
        if pat is not None:
            return Frame("kill_process", {"pattern": pat})
        return _ABSTAIN  # "kill the process" with no name/pid → abstain

    m = _PORT_RE.search(low)
    if m:
        return Frame("process_on_port", {"port": int(m.group(1))})

    # Task 23 (E056/E058): port/listening query with no number → list sockets.
    if _LISTENING_RE.search(low):
        return Frame("list_listening", {})

    m = _PID_RE.search(low)
    if m:
        return Frame("show_pid", {"pid": int(m.group(1))})

    if _MOST_RE.search(low) and _CPU_RE.search(low):
        return Frame("top_by_cpu", {"count": _top_count(low)})
    if _MOST_RE.search(low) and _MEM_RE.search(low):
        return Frame("top_by_mem", {"count": _top_count(low)})

    m = _FIND_PROC_RE.search(text)
    if m:
        pat = next(g for g in m.groups() if g)
        return Frame("find_process", {"pattern": pat})

    m = _PROC_NAMED_LIST_RE.search(text)  # E101: "list the python processes"
    if m and m.group(1).lower() not in _PROC_NAME_STOP:
        return Frame("find_process", {"pattern": m.group(1)})

    if _RUNNING_RE.search(low):
        return Frame("list_processes", {})

    return None


# --------------------------------------------------------------------------
# Domain: filesystem_permissions (Task 11) — read-only intents.
# chmod abstains (destructive); dir_empty is deferred (command substitution).
# --------------------------------------------------------------------------

# chmod (Task 15): executable toggle, octal/intent mode. All gated writes.
_EXEC_CUE_RE = re.compile(
    r"\b(?:executable|runnable|chmod\s*\+?x|u\+x)\b", re.IGNORECASE
)
_NONEXEC_CUE_RE = re.compile(
    r"\bnot\s+(?:be\s+)?(?:executable|runnable)\b|\bnon-?executable\b"
    r"|\bremove\s+(?:the\s+)?execut\w+\b|\ba-x\b", re.IGNORECASE
)
_SETPERM_CUE_RE = re.compile(
    r"\bchmod\b|\b(?:set|change)\s+(?:the\s+)?permissions?\b"
    r"|\bpermissions?\s+to\b|\bset\s+\S+\s+to\s+[0-7]{3,4}\b", re.IGNORECASE
)
_OCTAL_RE = re.compile(r"\b([0-7]{3,4})\b")
_PRIV_READ_RE = re.compile(
    r"\bonly\s+i\s+(?:can|should)(?:\s+be\s+able\s+to)?\s+(?:read|edit|see|access|open)\b"
    r"|\bprivate\b|\bonly\s+me\b|\bonly\s+my(?:self)?\b"
    r"|\block(?:\s+it)?\s*down\b|\block\s+down\b|\bsecure\s+(?:the|this|my)\b",  # Task 27 (E094)
    re.IGNORECASE
)
_PRIV_ENTER_RE = re.compile(r"\bonly\s+i\s+(?:can|should)\s+enter\b", re.IGNORECASE)
_CHMOD_OBJ_RE = re.compile(
    r"\b(?:set|chmod|make)\s+(?:the\s+)?([\w.+-]+)"
    r"|\b(?:read|edit|see|access)\s+(?:this|the|my)\s+([\w.+-]+)", re.IGNORECASE
)
_CHMOD_OBJ_STOP = {"the", "this", "that", "it", "permission", "permissions",
                   "mode", "executable", "runnable", "to", "a", "an", "my"}
_EMPTY_RE = re.compile(r"\bempty\b", re.IGNORECASE)
_FS_WRITABLE_RE = re.compile(
    r"\b(?:can i write|writable|write to|write access|able to write|i can write)\b",
    re.IGNORECASE,
)
_FS_READABLE_RE = re.compile(
    r"\b(?:can i read|readable|read access|able to read|i can read)\b", re.IGNORECASE
)
# "do i have" is intentionally NOT here — it belongs to workspace's
# check_installed ("do I have git"). File existence is "does X exist" / "is
# there a X" / "is X present".
_FS_EXISTS_RE = re.compile(
    r"\b(?:exists?|is there|is it there|does .* exist|is present)\b",
    re.IGNORECASE,
)
_FS_PERMS_RE = re.compile(
    r"\b(?:permissions?|perms|file mode|access bits|mode of)\b", re.IGNORECASE
)
_FS_OWNER_RE = re.compile(
    r"\b(?:who owns|owner of|owns (?:this|the|it)|what account owns|ownership)\b",
    re.IGNORECASE,
)
# Task 25 (E096): "who can read/write/access X" is a permission question → show
# the file's mode (ls -ld), not a find.
_FS_WHOCAN_RE = re.compile(
    r"\bwho\s+can\s+(?:read|write|access|see|edit|execute|run)\b", re.IGNORECASE,
)
_FS_DISK_RE = re.compile(
    r"\b(?:how big|disk usage|how much space|using space|take[sn]? up|du\b"
    r"|size of .* (?:folder|dir|directory))\b",
    re.IGNORECASE,
)
# Task 27 (E079/E081): a WHOLE-SYSTEM disk query → `df -h`, not a targetless
# `du` (which would abstain). Only fires when no specific folder is named.
_FS_DISKFREE_RE = re.compile(
    r"\b(?:running\s+out\s+of\s+(?:disk|space)|out\s+of\s+(?:disk\s+)?space"
    r"|how\s+much\s+(?:free\s+)?space(?:\s+is\s+left)?|space\s+left|space\s+is\s+left"
    r"|disk\s+free|free\s+space|disk\s+space(?:\s+left)?|low\s+on\s+(?:disk|space))\b",
    re.IGNORECASE,
)
# Task 27 (E043/E044): "find empty files/folders" is a DISCOVERY (find -empty),
# distinct from "is the output folder empty" (a check, still deferred).
_FS_FINDEMPTY_RE = re.compile(
    r"\bempty\s+(?:files?|folders?|dirs?|directories)\b"
    r"|\b(?:files?|folders?|dirs?|directories)\s+that\s+are\s+empty\b",
    re.IGNORECASE,
)
# Task 27 (E097/E098): permission-bit discovery → `find . -perm <mode>`.
_FS_FINDPERM_RE = re.compile(
    r"\bworld[-\s]?(writable|readable|executable)\b"
    r"|\b(writable|readable|executable|writeable)\s+by\s+(?:everyone|all|anyone|others?)\b"
    r"|\b(?:everyone|anyone|the\s+world|others?)\s+can\s+(write|read|execute)\b",
    re.IGNORECASE,
)

_FOLDER_NAME_RE = re.compile(r"\b([\w.-]+)\s+(?:folder|directory|dir)\b", re.IGNORECASE)
_ARTICLES = {"the", "this", "that", "a", "an", "my", "current", "same"}


def _detect_fs_target(text: str, low: str) -> str | None:
    m = _FOLDER_NAME_RE.search(low)
    if m and m.group(1).lower() not in _ARTICLES:
        return m.group(1)
    p = _detect_path_arg(text, low)
    if p is not None:
        return p
    if re.search(r"\b(?:here|this (?:folder|directory))\b", low):
        return "."
    return None


def _fs_frame(intent: str, text: str, low: str):
    slots: dict = {}
    target = _detect_fs_target(text, low)
    if target is not None:
        slots["path"] = target
    return Frame(intent, slots)


def _chmod_target(text: str, low: str) -> str | None:
    t = _detect_fs_target(text, low)
    if t is not None:
        return t
    m = _CHMOD_OBJ_RE.search(text)
    if m:
        obj = next((g for g in m.groups() if g), None)
        if obj and obj.lower() not in _CHMOD_OBJ_STOP:
            return obj
    # Task 23: a definite "script" reference → a shell-script glob (E075).
    if re.search(r"\b(?:the|this|my)\s+script\b", low):
        return Raw("*.sh")
    # Task 23 (E077/E078): a chmod intent clearly aimed at "this file" / "this" —
    # the mode is unambiguous from the intent words but the file is a generic
    # reference. Emit a FILE placeholder the user fills, rather than abstain; the
    # destructive gate still contains it to the maze. A bare "make this
    # executable" (no file noun / privacy cue) still abstains — see Task 20.
    if re.search(r"\b(?:this|the|my)\s+file\b|\bread\s+this\b|\bedit\s+this\b"
                 r"|\bprivate\b|\bonly\s+i\b", low):
        return "FILE"
    # Task 27 (E094): "lock down the key file" / "the secrets file" — a definite
    # "the <word> file" reference with no concrete name → a FILE placeholder the
    # user fills (exit 3 keeps it gated to the maze).
    if re.search(r"\b(?:the|this|my)\s+\w+\s+file\b", low):
        return "FILE"
    return None


def _parse_fs_chmod(text: str, low: str):
    """chmod intents (Task 15), gated writes. Returns a Frame, ``_ABSTAIN``
    (chmod intent but target/mode undeterminable), or ``None`` (not chmod)."""
    nonexec = bool(_NONEXEC_CUE_RE.search(low))
    execc = bool(_EXEC_CUE_RE.search(low)) and not nonexec
    setperm = bool(_SETPERM_CUE_RE.search(low))
    priv_read = bool(_PRIV_READ_RE.search(low))
    priv_enter = bool(_PRIV_ENTER_RE.search(low))
    if not (execc or nonexec or setperm or priv_read or priv_enter):
        return None  # not a chmod request — let the read checks run

    target = _chmod_target(text, low)
    if execc or nonexec:
        if target is None:
            return _ABSTAIN  # "make this executable" — no file named
        return Frame("make_executable" if execc else "remove_executable",
                     {"path": target})

    # set_permission: octal directly, else map an intent phrase to a mode.
    mode = None
    m = _OCTAL_RE.search(low)
    if m:
        mode = m.group(1)
    elif priv_enter:
        mode = "700"
    elif priv_read:
        mode = "600"
    if mode is None or target is None:
        return _ABSTAIN  # can't tell the mode or the file → abstain (hint)
    return Frame("set_permission", {"mode": mode, "path": target})


def _parse_filesystem(text: str, low: str):
    # chmod now builds real (gated) intents (Task 15); abstains only if the
    # target/mode can't be determined.
    chmod = _parse_fs_chmod(text, low)
    if chmod is not None:
        return chmod

    # Task 27 (E097/E098): permission-bit discovery. Before _FS_READABLE so
    # "readable by everyone" is a find_perms, not a check_readable on a target.
    m = _FS_FINDPERM_RE.search(low)
    if m:
        verb = (" ".join(g for g in m.groups() if g)).lower()
        if "writ" in verb:
            perm = "-002"
        elif "exec" in verb:
            perm = "-001"
        else:
            perm = "-004"
        return Frame("find_perms", {"perm": perm})

    # Task 27 (E043/E044): "find empty files/folders" → find -empty (discovery),
    # before the generic "empty" abstain (a dir-emptiness CHECK stays deferred).
    m = _FS_FINDEMPTY_RE.search(low)
    if m:
        ftype = "d" if re.search(r"\b(?:folders?|dirs?|directories)\b", low) else "f"
        return Frame("find_empty", {"ftype": ftype})
    if _EMPTY_RE.search(low):
        return _ABSTAIN  # dir_empty deferred (needs $(...) command substitution)

    # Task 27 (E079/E081): a whole-system disk query with no named folder → df -h.
    if _FS_DISKFREE_RE.search(low) and _detect_fs_target(text, low) is None:
        return Frame("disk_free", {})

    if _FS_WRITABLE_RE.search(low):
        return _fs_frame("check_writable", text, low)
    if _FS_READABLE_RE.search(low):
        return _fs_frame("check_readable", text, low)
    if _FS_WHOCAN_RE.search(low):
        return _fs_frame("show_permissions", text, low)
    if _FS_OWNER_RE.search(low):
        return _fs_frame("show_owner", text, low)
    if _FS_PERMS_RE.search(low):
        return _fs_frame("show_permissions", text, low)
    if _FS_DISK_RE.search(low):
        return _fs_frame("disk_usage", text, low)
    if _FS_EXISTS_RE.search(low):
        return _fs_frame("check_exists", text, low)
    return None


# --------------------------------------------------------------------------
# Domain: archives_backup (Task 13). Read intents (list/integrity/size) work
# anywhere; write intents (create/extract/compress) are gated to the maze.
# Single-command only — compound audits / redirects are deferred.
# --------------------------------------------------------------------------

# A named archive file: backup.tar.gz, data.gz, release.zip, src.tar.bz2.
# Longest extensions first so the whole "name.tar.gz" is captured.
_ARCHIVE_FILE_RE = re.compile(
    r"\b([\w][\w./-]*\.(?:tar\.gz|tar\.bz2|tgz|tbz2|tbz|tar|zip|gz|bz2|xz))\b",
    re.IGNORECASE,
)
# Verb cues. extract is checked before create; create before a bare "compress".
_ARC_EXTRACT_RE = re.compile(
    r"\b(?:unpack|unzip|untar|extract|decompress)\b", re.IGNORECASE
)
_ARC_CREATE_RE = re.compile(
    r"\b(?:package|tar up|zip up|bundle|make (?:a |an )?(?:archive|tarball|backup)"
    r"|create (?:a |an )?(?:archive|tarball|backup)|archive (?:the|this|my|up)"
    r"|make\s+a\s+backup\s+of\b|back\s+up\s+(?:the|this|my)\s+[\w./-]+"  # E120
    r"|compress\s+(?:the\s+|this\s+|my\s+)[\w-]+"  # E122 "compress the results"
    r"|compress\b[^.]*\binto\b)\b",
    re.IGNORECASE,
)
_ARC_LIST_RE = re.compile(
    r"\b(?:what'?s (?:inside|in)|list(?:\s+the)?\s+contents|show (?:me )?(?:the )?"
    r"(?:files|contents)|what(?:'s| is| files are)\s+(?:inside|in|packed)"
    r"|members of|contents of)\b",
    re.IGNORECASE,
)
_ARC_INTEGRITY_RE = re.compile(
    r"\b(?:integrity|intact|corrupt\w*|pass(?:es)?[^.]{0,20}check|verify|not damaged)\b",
    re.IGNORECASE,
)
_ARC_COMPRESS_RE = re.compile(r"\b(?:compress|gzip)\b", re.IGNORECASE)
# Task 25 (E127): "make a copy of X" / "duplicate X" → cp (a WRITE). NOT "copy to
# clipboard" (wsl) and NOT "copy … to windows" (wsl) — guarded at the call site.
# Task 34 (last manual synonym patch): also "create a copy of X", "make/create a
# duplicate of X", and "back up X.ext" (a single file → cp; a folder/project has
# no extension and still falls through to create_archive below).
_ARC_COPY_RE = re.compile(
    r"\b(?:make|create)\s+(?:a\s+|an\s+)?(?:copy|duplicate)\s+of\s+(?:the\s+)?([\w./-]+)"
    r"|\bduplicate\s+(?:the\s+)?([\w./-]+)"
    r"|\bback\s+up\s+(?:the\s+)?([\w./-]+\.\w+)"
    r"|\bcopy\s+(?:the\s+)?([\w./-]+\.\w+)", re.IGNORECASE,
)
# Task 23 (E084): the thing being archived, e.g. "zip up the project" → project.
_ARC_CREATE_OBJ_RE = re.compile(
    r"\bmake\s+a\s+backup\s+of\s+(?:the\s+|this\s+|my\s+)?([\w./-]+)"      # E120
    r"|\bback\s+up\s+(?:the\s+|this\s+|my\s+)?([\w./-]+)"
    r"|\b(?:package|tar\s+up|zip\s+up|bundle|archive|compress)\s+(?:up\s+)?"
    r"(?:the\s+|this\s+|my\s+)?([\w./-]+)",
    re.IGNORECASE,
)
_ARC_CREATE_STOP = {"the", "this", "my", "a", "an", "it", "up", "into", "folder",
                    "directory", "dir", "everything"}
_ARC_SIZE_RE = re.compile(r"\bhow big\b|\bsize of\b", re.IGNORECASE)
_ARC_INTO_RE = re.compile(
    r"\binto\s+(?:the\s+)?([\w./-]+)|\bto\s+(?:the\s+)?([\w./-]+)\s+(?:folder|dir)\b",
    re.IGNORECASE,
)


def _arc_is_zip(archive: str) -> bool:
    return archive.lower().endswith(".zip")


def _parse_archives(text: str, low: str):
    m = _ARCHIVE_FILE_RE.search(text)
    archive = m.group(1) if m else None
    # Task 22: "the backup/tarball/archive/gz/zip" → an archive-type glob, so
    # read intents (and extract) can fire without a concrete filename. create
    # does NOT use the glob — a glob as an OUTPUT name is nonsense, so it still
    # needs a real name or abstains.
    g = _definite_glob(low)
    arc_glob = g if g is not None and str(g) in _ARCHIVE_GLOBS else None
    arc = archive if archive is not None else arc_glob

    # 0. copy a file (E127): "make a copy of config.yaml" → cp (WRITE → exit 3).
    # Task 32: generalize to a destination — "copy X to Y" → cp -- X Y. With no
    # destination, fall back to the X.bak duplicate.
    if "clipboard" not in low and "windows" not in low and "/mnt/" not in low:
        mc = _ARC_COPY_RE.search(text)
        if mc:
            src = next(g for g in mc.groups() if g)
            dest = _dest_after(text)
            return Frame("copy_file", {"path": src, "dest": dest or (src + ".bak")})

    # 1. extract: unpack <archive> into <dir> → mkdir && tar (2-stage). With NO
    # destination (E123/E124 "extract the tarball"), extract into the cwd with a
    # single command — tar for a tarball, unzip for a zip (both WRITE → exit 3).
    if _ARC_EXTRACT_RE.search(low) and arc is not None:
        archive = arc
        m = _ARC_INTO_RE.search(text)
        dest = (m.group(1) or m.group(2)) if m else None
        if dest is not None:
            return Frame("extract_archive", {"archive": archive, "path": dest})
        if "unzip" in low or _arc_is_zip(str(archive)):
            # a "zip" request with only a definite tar-glob → use the .zip glob
            if not _arc_is_zip(str(archive)) and str(archive) in _ARCHIVE_GLOBS:
                archive = Raw("*.zip")
            return Frame("extract_zip", {"archive": archive})
        return Frame("extract_tar", {"archive": archive})

    # 2. create: package the <name> folder into <archive> (output is .tar.gz).
    if _ARC_CREATE_RE.search(low):
        slots = {"parent": "."}
        name = None
        m = _FOLDER_NAME_RE.search(low)
        if m and m.group(1).lower() not in _ARTICLES:
            name = m.group(1)
        if name is None:  # Task 23 (E084): "zip up the project" → name=project
            m = _ARC_CREATE_OBJ_RE.search(low)
            if m:
                obj = next((g for g in m.groups() if g), None)
                if obj and obj.lower() not in _ARC_CREATE_STOP:
                    name = obj
        if name is not None:
            slots["name"] = name
        if archive is not None:
            slots["archive"] = archive
        elif name is not None:  # default the output name from the source name
            slots["archive"] = name + ".tar.gz"
        return Frame("create_archive", slots)

    # 3. list contents: tar -tf (or zipfile -l for .zip). (arc = concrete or glob)
    if _ARC_LIST_RE.search(low) and arc is not None:
        intent = "list_zip" if _arc_is_zip(arc) else "list_archive"
        return Frame(intent, {"archive": arc})

    # 4. integrity check: gzip -t.
    if _ARC_INTEGRITY_RE.search(low) and arc is not None:
        return Frame("archive_integrity", {"archive": arc})

    # 5. single-file compress: gzip -k (no "into <archive>" — that was create).
    if _ARC_COMPRESS_RE.search(low):
        slots = {}
        p = _detect_path_arg(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("compress_file", slots)

    # 6. size of a named archive: du -h.
    if _ARC_SIZE_RE.search(low) and arc is not None:
        return Frame("archive_size", {"archive": arc})

    return None


# --------------------------------------------------------------------------
# Domain: python_environments (Task 14). Few clean single-command intents;
# most of the domain (venv/pip/activate/server) is deferred — see the abstains.
# Read intents work anywhere; run_script/check_syntax write and are gated.
# --------------------------------------------------------------------------

# Deferred families → abstain (do NOT let a fragment fall to another domain).
_PY_INSTALL_RE = re.compile(
    r"\b(?:pip3?\b|install\s+(?:the\s+)?(?:requirements?|packages?|dependenc\w+|deps|modules?)"
    r"|upgrade\s+\S+\s+package|pip\s+install|download\s+\S+\s+package)\b",
    re.IGNORECASE,
)
_PY_VENV_RE = re.compile(
    r"\b(?:activate|deactivate|virtual\s*env\w*|\bvenv\b|create\s+(?:a\s+)?(?:venv|virtualenv))\b",
    re.IGNORECASE,
)
_PY_SERVER_RE = re.compile(
    r"\bhttp\.server\b|\b(?:start|spin up|serve|launch)\b[^.]*\b(?:server|http)\b",
    re.IGNORECASE,
)

# Built intents.
_PY_SYNTAX_RE = re.compile(
    r"\b(?:syntax\s+errors?|syntax\s+check|py_?compile"
    r"|check\s+\S+\s+for\s+(?:syntax\s+)?errors?"
    r"|does\s+\S+\s+compile|compile\s+check)\b",
    re.IGNORECASE,
)
_PY_RUN_RE = re.compile(
    r"\brun\s+(?:this\s+|the\s+|my\s+)?(?:script\b|analysis\b|training\b|pipeline\b"
    r"|[\w./-]+\.py\b)|\brun\b[^.]*\.py\b",
    re.IGNORECASE,
)
# "installed" is intentionally NOT here — it belongs to workspace's
# check_installed (a system tool: `command -v`), while a *package* is
# "available/importable". This keeps "is docker installed" (tool) distinct from
# "is pandas available" (package).
_PY_PKG_RE = re.compile(
    r"\bis\s+([\w.-]+)\s+(?:available|importable|a\s+(?:module|package))\b"
    r"|\bdoes\s+([\w.-]+)\s+(?:import|load)\b"
    r"|\bcan\s+i\s+import\s+([\w.-]+)\b"
    r"|\bcheck\s+(?:if|whether)\s+([\w.-]+)\s+(?:is\s+)?(?:available|imports?)\b",
    re.IGNORECASE,
)
_PY_VERSION_RE = re.compile(
    r"\bpython\s*(?:--?)?version\b|\bversion\s+of\s+python\b"
    r"|\bwhat\s+python\s+version\b|\bpython\b[^.]*\bversion\b",
    re.IGNORECASE,
)
_PY_WHERE_RE = re.compile(
    r"\bwhere\b[^.]*\bpython\b|\bwhich\s+python\b"
    r"|\bpython\b[^.]*\b(?:located|live|lives|installed)\b|\blocation\s+of\s+python\b",
    re.IGNORECASE,
)
# Task 23 (E090): "is numpy installed" is about a PYTHON PACKAGE, not a CLI
# binary — `command -v numpy` always fails. A small known-package hint set routes
# the install-check to the importlib test; an unknown token ("is docker
# installed") falls through to workspace's `command -v`.
_KNOWN_PY_PKGS = {
    "numpy", "pandas", "scipy", "torch", "pytorch", "sklearn", "scikit-learn",
    "matplotlib", "seaborn", "requests", "flask", "django", "tensorflow",
    "keras", "transformers", "pytest", "jupyter", "notebook", "plotly",
    "statsmodels", "xgboost", "lightgbm", "polars", "pydantic", "fastapi",
}
_PY_INSTALLED_PKG_RE = re.compile(
    r"\bis\s+([\w.-]+)\s+(?:installed|there|available|around)\b"
    r"|\bdo\s+i\s+have\s+([\w.-]+)(?:\s+installed)?\b"
    r"|\bcheck\s+(?:if|whether)\s+([\w.-]+)\s+(?:is\s+)?(?:installed|there|available|around)\b"
    r"|\b([\w.-]+)\s+is\s+installed\b",
    re.IGNORECASE,
)
# Task 27 (E134/E135): list installed packages → `pip list`.
_PY_PIPLIST_RE = re.compile(
    r"\bpip\s+list\b|\blist\s+(?:my\s+|all\s+)?(?:pip\s+|installed\s+|python\s+)?packages\b"
    r"|\bwhat\s+packages\s+are\s+installed\b|\b(?:show|list)\s+(?:me\s+)?(?:my\s+)?"
    r"installed\s+(?:python\s+)?packages\b|\binstalled\s+(?:python\s+)?packages\b",
    re.IGNORECASE,
)


def _py_script_path(text: str, low: str):
    """A concrete script path / definite-ref glob, or "*.py" for "the script"
    (Task 22 — script is py in the python domain)."""
    p = _detect_path_arg(text, low)
    if p is not None:
        return p
    if re.search(r"\b(?:the|this|my)\s+script\b", low):
        return Raw("*.py")
    return None


def _parse_python(text: str, low: str):
    # Task 27 (E134/E135): list installed packages → `pip list`. Checked before
    # the deferred "pip install" family (so "what packages are installed" isn't
    # swept into the network abstain).
    if _PY_PIPLIST_RE.search(low):
        return Frame("pip_list", {})

    # Task 27 (E085): "which pip am i using" / "where is pip" → command -v pip.
    # Checked before the install-abstain (which matches a bare "pip").
    if re.search(r"\bwhich\s+pip\b|\bwhere(?:'s| is)?\s+(?:my\s+)?pip\b", low):
        return Frame("check_installed", {"tool": "pip"})

    # Deferred families abstain (network / shell-state / long-running). Checked
    # first so "run setup in the venv" doesn't slip through as run_script.
    if _PY_INSTALL_RE.search(low) or _PY_VENV_RE.search(low) or _PY_SERVER_RE.search(low):
        return _ABSTAIN

    if _PY_SYNTAX_RE.search(low):
        slots: dict = {}
        p = _py_script_path(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("check_syntax", slots)

    if _PY_RUN_RE.search(low):
        slots = {}
        p = _py_script_path(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("run_script", slots)

    m = _PY_PKG_RE.search(text)
    if m:
        pkg = next(g for g in m.groups() if g)
        return Frame("check_package", {"pkg": pkg})

    # Task 23 (E090): "is <pkg> installed" for a KNOWN Python package → importlib
    # check. Unknown token → not ours (workspace's command -v handles CLI tools).
    m = _PY_INSTALLED_PKG_RE.search(text)
    if m:
        pkg = next(g for g in m.groups() if g)
        if pkg.lower() in _KNOWN_PY_PKGS:
            return Frame("check_package", {"pkg": pkg})
        # Task 27 (E132): a non-package name ("check if docker is there") is a
        # CLI-tool check → command -v. Claimed here (before filesystem's
        # "is there" → check_exists would steal it). Vague tokens still defer.
        if pkg.lower() not in _NOT_A_TOOL:
            return Frame("check_installed", {"tool": pkg})

    if _PY_VERSION_RE.search(low):
        return Frame("python_version", {})
    if _PY_WHERE_RE.search(low):
        return Frame("where_python", {})

    return None


# --------------------------------------------------------------------------
# Domain: workspace_and_shell (Task 16). Navigation + shell reads (anywhere);
# make_dir + the scoped setup_project recipe write (gated). setup_project is
# ONE fixed recipe, not arbitrary compound decomposition (that is V1.1).
# --------------------------------------------------------------------------

_WS_COMPOUND_RE = re.compile(r"\bthen\b|\band then\b|\bafter that\b|&&", re.IGNORECASE)
_WS_SETUP_RE = re.compile(
    r"\b(?:set\s*up|setup|create|make|start)\s+(?:a\s+|an\s+|my\s+)?(?:new\s+)?"
    r"(?:project|workspace)\b", re.IGNORECASE,
)
_WS_ENVVAR_RE = re.compile(
    r"\b(?:what'?s|what\s+is|show|print|echo|display|value\s+of)\b[^.]*?"
    r"\b(PATH|HOME|PORT|USER|SHELL|PWD|LANG|TERM|EDITOR|DISPLAY|GPU_ID|PID)\b",
    re.IGNORECASE,
)
_WS_NAME_CALLED_RE = re.compile(r"\b(?:called|named)\s+([\w.-]+)", re.IGNORECASE)
_WS_NAME_FALLBACK_RE = re.compile(
    r"\b(?:project|workspace)\s+(?:folder\s+|dir\s+|directory\s+)?([\w.-]+)\b",
    re.IGNORECASE,
)
_WS_NAME_STOP = {"folder", "dir", "directory", "called", "named", "with", "and"}
_WS_MKDIR_RE = re.compile(
    r"\b(?:make|create|new|add)\s+(?:a\s+|an\s+|the\s+)?([\w./-]+?)\s+(?:folder|dir|directory)\b"
    r"|\bmkdir\s+(?:-p\s+)?([\w./-]+)",
    re.IGNORECASE,
)
_WS_WHICH_SHELL_RE = re.compile(
    r"\bwhich\s+shell\b|\bwhat\s+shell\b|\bcurrent\s+shell\b|\bmy\s+shell\b"
    r"|\bwhat(?:'s| is)\s+my\s+shell\b", re.IGNORECASE,
)
# Task 25 (E088): date / time → `date`. (A grep fallback used to swallow
# "what's today's date" via the contraction apostrophe — now fixed in grep too.)
_WS_DATE_RE = re.compile(
    r"\bwhat\s+time\s+is\s+it\b|\btoday'?s\s+date\b|\bcurrent\s+(?:date|time)\b"
    r"|\bwhat(?:'s| is)\s+the\s+(?:date|time)\b|\bwhat\s+day\s+is\s+it\b"
    r"|\bdate\s+and\s+time\b", re.IGNORECASE,
)
_WS_INSTALLED_RE = re.compile(
    r"\bdo\s+i\s+have\s+([\w.+-]+)(?:\s+installed)?\b"
    r"|\bis\s+([\w.+-]+)\s+(?:installed|there|available)\b"
    r"|\bcheck\s+(?:if|whether)\s+([\w.+-]+)\s+is\s+(?:installed|there|available)\b"
    r"|\b([\w.+-]+)\s+is\s+installed\b"
    r"|\b(?:command\s+-v|which)\s+([\w.+-]+)\b",
    re.IGNORECASE,
)
# Tokens that are ordinary English, never a tool name — so "which files are huge"
# (Task 23 E004) can't become `command -v files`.
_NOT_A_TOOL = {
    "files", "file", "one", "ones", "way", "version", "it", "that", "this",
    "any", "directory", "folder", "command", "something", "anything", "them",
}
_WS_GO_HOME_RE = re.compile(
    r"\bgo\s+home\b|\btake\s+me\s+home\b|\bback\s+to\s+(?:my\s+)?home\b"
    r"|\bhome\s+(?:folder|directory)\b|\bcd\s+~\b|\bto\s+my\s+home\b", re.IGNORECASE,
)
_WS_GO_BACK_RE = re.compile(
    r"\bgo\s+back\b|\bcd\s+-\b|\b(?:previous|last)\s+(?:folder|directory|dir)\b"
    r"|\bfolder\s+i\s+was\s+in\b|\bwhere\s+i\s+was\b", re.IGNORECASE,
)
_WS_GOTO_RE = re.compile(
    r"\b(?:go\s+to|goto|take\s+me\s+(?:to|into)|navigate\s+to|move\s+to"
    r"|change\s+to|cd\s+(?:to|into))\s+(?:the\s+)?([\w./-]+?)(?:\s+(?:folder|dir|directory))?\b",
    re.IGNORECASE,
)
_WS_WHERE_RE = re.compile(
    r"\bwhere\s+am\s+i\b|\bwhat\s+(?:folder|directory|dir)\s+am\s+i\s+in\b"
    r"|\bcurrent\s+(?:folder|directory|path|working\s+directory)\b"
    r"|\b(?:present|print)\s+working\s+directory\b|\bpwd\b", re.IGNORECASE,
)
_WS_LIST_ALL_RE = re.compile(
    r"\blist\s+all\b|\ball\s+files\s+including\s+hidden\b|\bincluding\s+hidden\b"
    r"|\bshow\s+(?:all\s+)?hidden\b|\bshow\s+all\s+files\b|\bls\s+-l?al?\b", re.IGNORECASE,
)
_WS_WHO_RE = re.compile(
    r"\bwho\s+am\s+i\b|\bwhat\s+(?:account|user)\b|\bwhat(?:'s| is)\s+my\s+(?:user|username|account)\b"
    r"|\bwhoami\b|\bwhat\s+groups\b|\bmy\s+groups\b", re.IGNORECASE,
)
_WS_HISTORY_RE = re.compile(
    r"\bcommand\s+history\b|\bshow\s+(?:me\s+)?(?:the\s+)?history\b|\bhistory\s+of\s+commands\b"
    r"|\bcommands?\s+i\s+(?:used|ran|run|typed)\b|\b(?:earlier|previous|recent)\s+commands?\b"
    # Task 28 (E086): a command-history request must beat find_recent even when
    # "recent/recently" is present. Cue words: command(s) / did i run / i ran.
    r"|\bwhat\s+commands?\s+(?:did\s+i|have\s+i)\b|\bcommands?\s+did\s+i\s+run\b"
    r"|\bwhat\s+have\s+i\s+run\b", re.IGNORECASE,
)
_WS_CLEAR_RE = re.compile(
    r"\bclear\s+(?:the\s+)?(?:screen|terminal)\b|\bclear\s+my\s+screen\b"
    r"|\bwipe\s+the\s+screen\b|\bcls\b", re.IGNORECASE,
)


def _parse_workspace(text: str, low: str):
    # scoped recipe first (it contains "make/create ... project")
    if _WS_SETUP_RE.search(low):
        if _WS_COMPOUND_RE.search(low):
            return _ABSTAIN  # compound beyond the fixed recipe is V1.1
        # Prefer an explicit "called/named X"; else the word after
        # "project/workspace" if it isn't a stopword; else a default name.
        name = None
        m = _WS_NAME_CALLED_RE.search(text)
        if m:
            name = m.group(1)
        else:
            m = _WS_NAME_FALLBACK_RE.search(text)
            if m and m.group(1).lower() not in _WS_NAME_STOP:
                name = m.group(1)
        return Frame("setup_project", {"name": name or "project"})

    if _WS_MKDIR_RE.search(low):
        m = _WS_MKDIR_RE.search(text)
        path = (m.group(1) or m.group(2)) if m else None
        slots = {}
        if path is not None:
            slots["path"] = path
        return Frame("make_dir", slots)

    if _WS_WHICH_SHELL_RE.search(low):
        return Frame("which_shell", {})

    # Task 27 (E076/E077/E078): print an environment variable. The $VAR is a Raw
    # so render emits it unquoted and the shell expands it (`echo $PATH`).
    m = _WS_ENVVAR_RE.search(text)
    if m:
        return Frame("env_var", {"var": Raw("$" + m.group(1).upper())})

    if _WS_DATE_RE.search(low):
        return Frame("date_time", {})

    m = _WS_INSTALLED_RE.search(text)
    if m:
        tool = next((g for g in m.groups() if g), None)
        if tool and tool.lower() not in _NOT_A_TOOL:
            return Frame("check_installed", {"tool": tool})

    # go_home / go_back / goto / where_am_i moved to the navigation domain
    # (Task 26) — it runs before workspace and owns all cd/pwd routing, which
    # also kills the old glob leak (workspace goto used _detect_path_arg).
    if _WS_LIST_ALL_RE.search(low):
        return Frame("list_all", {})
    if _WS_WHO_RE.search(low):
        return Frame("who_am_i", {})
    if _WS_HISTORY_RE.search(low):
        return Frame("show_history", {})
    if _WS_CLEAR_RE.search(low):
        return Frame("clear_screen", {})

    # An "export ... && cd ..." compound names a workspace verb but is beyond
    # V1's scoped recipes → abstain rather than let a fragment leak.
    if _WS_COMPOUND_RE.search(low) and re.search(r"\b(?:cd|export|pwd)\b", low):
        return _ABSTAIN

    return None


# --------------------------------------------------------------------------
# Domain: wsl_interop (Task 17). All read-only. Clean single-level intents are
# built; nested $(...) navigation (windows downloads/desktop/user folder, cp to
# a windows folder) is DEFERRED — abstain. Fires only on WSL/Windows cues so it
# doesn't steal generic navigation.
# --------------------------------------------------------------------------

_WSL_WINPATH_RE = re.compile(r"([A-Za-z]:\\[^\s'\"]*)")
# nested $() — a named Windows special folder / user folder / cp to windows
# Task 27: downloads/desktop/documents/pictures are no longer deferred — they
# resolve to `cd /mnt/c/Users/$USER/<Folder>` (win_folders, no nested $() needed).
# The genuinely-nested cases (windows home/user/profile, "copy X to windows")
# still abstain.
_WSL_NESTED_RE = re.compile(
    r"\bwindows\s+(?:home|user(?:\s+folder)?|profile)\b"
    r"|\bmy\s+windows\s+(?:user|profile|home)\b"
    r"|\bwhere\s+my\s+windows\s+(?:user\s+)?(?:folder|profile)\b"
    r"|\bcopy\b[^.]*\bto\s+(?:my\s+)?windows\b|\bcp\b[^.]*\bwindows\b",
    re.IGNORECASE,
)
_WSL_TO_LINUX_RE = re.compile(
    r"\b(?:to|into)\s+(?:a\s+|an\s+|the\s+)?(?:ubuntu|linux|wsl|unix)\s+path\b"
    r"|\bwslpath\s+-u\b|\b(?:linux|ubuntu|unix)\s+(?:version|equivalent)\b", re.IGNORECASE,
)
_WSL_TO_WINDOWS_RE = re.compile(
    r"\bon\s+windows\b|\blook\s+(?:like\s+)?on\s+windows\b|\bto\s+(?:a\s+)?windows\s+path\b"
    r"|\bwindows\s+(?:version|equivalent|path\s+for)\b|\bwslpath\s+-w\b", re.IGNORECASE,
)
_WSL_CLIP_RE = re.compile(r"\bclip(?:board)?\b", re.IGNORECASE)
# Task 27 (E116): "open this in vs code" → `code .`.
_WSL_VSCODE_RE = re.compile(r"\bvs\s*code\b|\bvscode\b|\bvisual\s+studio\s+code\b", re.IGNORECASE)
# Task 27 (E117/E118): a Windows user folder → cd to /mnt/c/Users/$USER/<F>.
_WSL_WINFOLDER_RE = re.compile(
    r"\bwindows\s+(downloads|documents|desktop|pictures)\b"
    r"|\bmy\s+(downloads|documents|desktop|pictures)\s+(?:on|in)\s+windows\b",
    re.IGNORECASE,
)
_WSL_EXPLORER_RE = re.compile(
    r"\bexplorer\b|\bfile\s+explorer\b|\bopen\b[^.]*\bin\s+windows\b", re.IGNORECASE
)
# Narrowed (Task 26): only the "C drive" WORD request is wsl's. An explicit
# "/mnt/c/Users" path is a plain absolute path → navigation (cd_absolute) owns it
# and captures the WHOLE path (E019), instead of truncating to `cd /mnt/c`.
_WSL_CDRIVE_RE = re.compile(r"\bc\s*:\s*\\?|\bthe\s+c\s+drive\b|\bc\s+drive\b", re.IGNORECASE)
_WSL_SPACE_RE = re.compile(r"\b(?:free\s+space|how\s+much\s+(?:free\s+)?(?:space|room)|disk\s+space|(?:space|room)\s+(?:on|left))\b", re.IGNORECASE)
_WSL_UBUNTU_RE = re.compile(r"\b(?:ubuntu|linux\s+home|linux\s+side|wsl)\b", re.IGNORECASE)
_WSL_HOME_RE = re.compile(r"\b(?:linux|ubuntu)\s+home\b|\bback\s+to\s+my\s+linux\b", re.IGNORECASE)


def _parse_wsl(text: str, low: str):
    # nested command substitution → deferred (abstain), checked first.
    if _WSL_NESTED_RE.search(low):
        return _ABSTAIN

    win = _WSL_WINPATH_RE.search(text)

    # path conversions
    if _WSL_TO_LINUX_RE.search(low) or (win and ("linux" in low or "ubuntu" in low or "unix" in low)):
        if win is not None:
            return Frame("path_to_linux", {"winpath": win.group(1)})
        return _ABSTAIN  # "to a linux path" but no C:\ path given
    if _WSL_TO_WINDOWS_RE.search(low):
        # Task 27 (E113/E114): "the windows path for this folder" names no
        # concrete path → default to "." (the cwd), rather than abstain.
        p = _detect_path_arg(text, low) or "."
        return Frame("path_to_windows", {"path": p})

    # Task 27 (E117/E118): a Windows user folder → cd /mnt/c/Users/*/<F>.
    # Task 28: use a GLOB (`*`), not `$USER`. On WSL the Linux $USER is almost
    # never the Windows account name, so `/mnt/c/Users/$USER/...` usually points
    # at a path that doesn't exist. The `*` is emitted unquoted (Raw) and the
    # shell expands it to the real Windows user dir.
    m = _WSL_WINFOLDER_RE.search(low)
    if m:
        folder = next(g for g in m.groups() if g).capitalize()
        return Frame("goto", {"path": Raw(f"/mnt/c/Users/*/{folder}")})

    if _WSL_VSCODE_RE.search(low):
        return Frame("open_vscode", {})
    if _WSL_CLIP_RE.search(low):
        return Frame("copy_to_clipboard", {})
    if _WSL_EXPLORER_RE.search(low):
        return Frame("open_explorer", {})

    # C drive: space vs navigate
    if _WSL_CDRIVE_RE.search(low):
        if _WSL_SPACE_RE.search(low):
            return Frame("cdrive_space", {})
        return Frame("goto_cdrive", {})

    # Ubuntu/linux side: space vs home
    if _WSL_UBUNTU_RE.search(low):
        if _WSL_SPACE_RE.search(low):
            return Frame("home_space", {})
        if _WSL_HOME_RE.search(low):
            return Frame("goto_home", {})

    return None


# Router order: specific domains first, file_discovery last (see parse()).
# python sits before text so "check X.py for syntax errors" is check_syntax,
# not a grep for "errors". archives sits before filesystem so
# "how big is <archive>.tar.gz" routes to archive_size, not disk_usage.
# wsl sits before filesystem so "how much space does ubuntu have left" is
# home_space, not a targetless disk_usage; it only fires on WSL/Windows/C-drive
# cues. workspace sits after filesystem (file-ish queries stay with filesystem)
# and before file_discovery (it catches navigation/shell verbs file_discovery
# would otherwise abstain on).
# --------------------------------------------------------------------------
# Domain: navigation (Task 26) — a first-class cd/pwd parser. Resolution order
# matters: directional words (up/back/home) are unambiguous and beat name
# matching. cd_ancestor/cd_parent read the live cwd (os.getcwd()), the same
# source the gate uses. A navigation target is a DIRECTORY name — it is NEVER
# run through the Task-22 definite-reference glob resolver (that caused the
# `cd -- *.log` leak). "windows" requests defer to wsl.
# --------------------------------------------------------------------------

_NAV_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                  "six": 6, "a": 1, "an": 1}
_NAV_LEVELS_RE = re.compile(
    r"\bup\s+(\d+|one|two|three|four|five|six)\s+(?:levels?|directories|dirs?|folders?)\b",
    re.IGNORECASE,
)
_NAV_PARENT_RE = re.compile(
    r"\bup\s+(?:\d+|one|two|three|four|five|six|a|an)\s+(?:levels?|directories|dirs?|folders?)\b"
    r"|\b(?:go|move|level)\s+up\b|\bgo\s+up\b|\bup\s+(?:a|one)\s+(?:level|directory|dir|folder)\b"
    r"|\b(?:go\s+)?back\s+up\s+(?:a|one|the)?\s*(?:level|directory|dir|folder)s?\b"
    r"|\btake\s+me\s+back\b|\bgo\s+back\b(?!\s+to\b)|\bparent\b",
    re.IGNORECASE,
)
_NAV_HOME_RE = re.compile(
    r"\btake\s+me\s+home\b|\bgo\s+home\b|\bhome\s+(?:directory|folder|dir)\b"
    r"|\b(?:to|into)\s+(?:my\s+)?home\b|\bcd\s+~|^\s*home\s*$",
    re.IGNORECASE,
)
_NAV_PREV_RE = re.compile(
    r"\bwhere\s+i\s+was\b|\b(?:previous|last)\s+(?:directory|folder|dir)\b"
    r"|\bback\s+to\s+where\s+i\s+was\b|\bcd\s+-\B",
    re.IGNORECASE,
)
_NAV_PWD_RE = re.compile(
    r"\bwhere\s+am\s+i\b|\bwhat\s+(?:folder|directory|dir)\s+am\s+i\s+in\b"
    r"|\bcurrent\s+(?:folder|directory|dir|working\s+directory)\b"
    r"|\b(?:present|print)\s+working\s+directory\b|\bpwd\b",
    re.IGNORECASE,
)
_NAV_GOTO_RE = re.compile(
    r"\b(?:go\s+back\s+to|go\s+to|goto|take\s+me\s+(?:to|into)|navigate\s+to"
    r"|move\s+(?:to|into)|change\s+to|cd\s+(?:to|into)?|go\s+into|enter|open)\s+"
    r"(?:the\s+|my\s+)?([/\w.+-]+)",
    re.IGNORECASE,
)
_NAV_STOP = {"the", "my", "a", "an", "it", "here", "there", "where", "back", "this"}
# Task 32: "<verb> X inside/within/under/in Y" — nested navigation.
_NAV_NESTED_RE = re.compile(
    r"\b(?:go\s+to|goto|take\s+me\s+(?:to|into)|navigate\s+to|cd\s+(?:to|into)?"
    r"|go\s+into|enter|open|change\s+to)\s+"
    r"(?:the\s+|my\s+)?([\w.+-]+)\s+(?:inside|within|under|in)\s+"
    r"(?:the\s+|my\s+)?([\w.+-]+)\b",
    re.IGNORECASE,
)


def _nav_levels(low: str) -> int:
    m = _NAV_LEVELS_RE.search(low)
    if m:
        w = m.group(1).lower()
        return int(w) if w.isdigit() else _NAV_NUM_WORDS.get(w, 1)
    return 1


def _parse_navigation(text: str, low: str):
    # "windows" navigation is wsl's (downloads/documents/C-drive). Defer.
    if "windows" in low:
        return None

    # 1. cd_parent — directional, beats name matching.
    if _NAV_PARENT_RE.search(low):
        n = _nav_levels(low)
        return Frame("cd_parent", {"updots": "/".join([".."] * n)})
    # 2. cd_home
    if _NAV_HOME_RE.search(low):
        return Frame("go_home", {})
    # 3. cd_previous (guarded above so "go up"/"project root" don't reach it)
    if _NAV_PREV_RE.search(low):
        return Frame("go_back", {})
    # 7(early). pwd — a keyword query, no target.
    if _NAV_PWD_RE.search(low):
        return Frame("where_am_i", {})

    # 3b. nested navigation (Task 32): "go to X inside/under/in Y".
    #   * Y an ANCESTOR of cwd → resolve Y's absolute path, append X.
    #   * Y a CHILD dir of cwd and X under it → relative `cd -- Y/X`.
    #   * otherwise → abstain (a fuzzy, elsewhere-on-disk Y is a future
    #     find-based resolver; don't guess).
    m = _NAV_NESTED_RE.search(text)
    if m:
        x, y = m.group(1), m.group(2)
        if x.lower() not in _NAV_STOP and y.lower() not in _NAV_STOP:
            segs = os.getcwd().split(os.sep)
            idxs = [i for i, s in enumerate(segs) if s and s.lower() == y.lower()]
            if idxs:
                # Y is an ancestor. If a segment name repeats (e.g. ~/linuxbuddy
                # with a src/linuxbuddy under it), prefer the occurrence that
                # actually contains X; otherwise the nearest one.
                def _anc(i: int) -> str:
                    return os.sep.join(segs[: i + 1]) or os.sep
                chosen = next((i for i in sorted(idxs, reverse=True)
                               if os.path.isdir(os.path.join(_anc(i), x))), idxs[-1])
                return Frame("goto", {"path": f"{_anc(chosen)}/{x}"})
            if os.path.isdir(y) and os.path.isdir(os.path.join(y, x)):
                return Frame("goto", {"path": f"{y}/{x}"})
            return _ABSTAIN

    # target-based: extract the destination from a goto verb.
    m = _NAV_GOTO_RE.search(text)
    if m:
        target = m.group(1).rstrip("/")
        low_t = target.lower()
        # 6. cd_absolute — an explicit /path, captured WHOLE (E019).
        if target.startswith("/"):
            return Frame("goto", {"path": target})
        # a filename (has an extension) is not a directory → not navigation.
        if "." in target and target not in (".", ".."):
            return None
        if low_t in _NAV_STOP or not target:
            return None
        # 4. cd_ancestor — X is a segment of the cwd → cd to that absolute path.
        segs = os.getcwd().split(os.sep)
        if low_t in [s.lower() for s in segs if s]:
            idx = max(i for i, s in enumerate(segs) if s.lower() == low_t)
            anc = os.sep.join(segs[: idx + 1]) or os.sep
            return Frame("goto", {"path": anc})
        # 5. cd_child — a child directory name.
        return Frame("goto", {"path": target})

    return None


# --------------------------------------------------------------------------
# Domain: file_management (Task 32) — move/rename, copy-to-dest, delete, mkdir.
# ALL destructive (write/delete) → gated to the maze, exit 3, widget warns.
#
# Destructive intents keep the STRICT bar (invariant #6): a move/delete only
# fires on a CONFIDENT target — a quoted/slash/`name.ext` path or a typed
# definite reference ("the old logs" → *.log, "the image" → an image glob). A
# bare, type-less word as a source is NOT confident, so we fall through rather
# than emit a wrong `mv`/`rm`. A delete verb that owns the sentence but names no
# resolvable target ABSTAINS (never a guessed `rm`).
#
# copy stays in _parse_archives (generalized there to take a destination);
# this parser runs just before archives so move/delete/mkdir win first, while
# "make a copy of X" / "copy X to Y" still reach the archives copy branch.
# --------------------------------------------------------------------------

# "<verb> <source> <to|into|in> <dest>" — source and dest captured off the
# ORIGINAL text (IGNORECASE) so filename case is preserved.
_FM_MOVE_RE = re.compile(
    r"\b(?:move|rename|put)\s+(.+?)\s+(?:to|into|in)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_FM_DELETE_RE = re.compile(
    r"\b(?:delete|remove|rm|get\s+rid\s+of|trash)\b", re.IGNORECASE,
)
_FM_MKDIR_RE = re.compile(
    r"\b(?:make|create|new|add)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?"
    r"(?:folder|dir|directory)\s+(?:called\s+|named\s+)?([\w./-]+)",
    re.IGNORECASE,
)
# A destination named after "to"/"into" (for copy X to Y). The dest is a plain
# directory/file token — never a glob.
_DEST_AFTER_RE = re.compile(
    r"\b(?:into|to)\s+(?:the\s+|my\s+)?([\w./+-]+)", re.IGNORECASE,
)


def _dest_after(text: str) -> str | None:
    """The destination after a 'to'/'into' in a copy/move request, or None."""
    m = _DEST_AFTER_RE.search(text)
    return m.group(1) if m else None


def _fm_dest(frag: str) -> str | None:
    """Clean a destination fragment to a single dir/file token: drop a trailing
    folder noun and a leading article, prefer a concrete path/name, else the
    last bare token."""
    d = re.sub(r"\s+(?:folder|dir|directory)\s*$", "", frag.strip(), flags=re.IGNORECASE)
    d = re.sub(r"^(?:the|my|a|an|this)\s+", "", d, flags=re.IGNORECASE)
    p = _detect_path_arg(d, d.lower())
    if p is not None and not isinstance(p, Raw):   # a dest is never a glob
        return p
    m = re.search(r"([\w./+-]+)\s*$", d)
    return m.group(1) if m else None


def _parse_file_management(text: str, low: str):
    # 1. move / rename / put  — needs a confident source AND a destination.
    m = _FM_MOVE_RE.search(text)
    if m:
        src_frag, dest_frag = m.group(1), m.group(2)
        src = _detect_path_arg(src_frag, src_frag.lower())  # path/name.ext/definite
        dest = _fm_dest(dest_frag)
        if src is not None and dest:
            return Frame("move_file", {"path": src, "dest": dest})

    # 2. delete / remove — chmod ("remove the executable bit") and the text-
    #    domain ops ("remove duplicates/blank lines") are NOT deletions.
    if _FM_DELETE_RE.search(low):
        if not any(w in low for w in ("execut", "duplicat", "blank line")):
            tgt = _detect_path_arg(text, low)
            if tgt is not None:
                return Frame("delete_file", {"path": tgt})
            # a delete verb owning the sentence but no resolvable target →
            # refuse (destructive + unclear target = abstain, never a guess).
            return _ABSTAIN

    # 3. make a folder/dir X  (noun-then-name; name-then-noun stays in workspace).
    #    Yield "project/workspace" phrasing to workspace's setup_project.
    if "project" not in low and "workspace" not in low:
        m = _FM_MKDIR_RE.search(text)
        if m:
            return Frame("make_dir", {"path": m.group(1)})

    return None


_ROUTER = (
    _parse_file_inspection,
    _parse_python,
    _parse_text_and_logs,
    _parse_processes,
    _parse_file_management,
    _parse_archives,
    _parse_wsl,
    _parse_navigation,
    _parse_filesystem,
    _parse_workspace,
    _parse_file_discovery,
)


def abstain_hint(text: str) -> str | None:
    """A specific hint for *why* :func:`parse` abstained, or ``None``.

    Called by the CLI only after ``parse`` returned ``None``. When we can see
    the user named a capability but omitted its defining slot (a size or age
    superlative with no number), we say what is missing instead of the
    generic "not sure what you mean". Pure rules, no state.
    """
    if not text or not text.strip():
        return None
    low = text.lower()
    size_bytes, size_cue = _detect_size(low)
    if size_cue and size_bytes is None:
        return 'LinuxBuddy: how big? try "over 100MB"'
    if _TIME_CUE_RE.search(low) and _detect_time(low) is None:
        return 'LinuxBuddy: how recent? try "in the last 7 days"'
    # chmod with no determinable mode (e.g. "change the permissions on X")
    if (_SETPERM_CUE_RE.search(low) and not _OCTAL_RE.search(low)
            and not _PRIV_READ_RE.search(low) and not _PRIV_ENTER_RE.search(low)
            and not _EXEC_CUE_RE.search(low) and not _NONEXEC_CUE_RE.search(low)):
        return 'LinuxBuddy: what permissions? e.g. 600 for private'
    return None
