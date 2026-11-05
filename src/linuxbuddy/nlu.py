"""Rule-based NLU for the file_discovery domain.

Pure rules + regex. No machine learning, no network, no model (CLAUDE.md
invariant). ``parse`` turns a natural-language request into a :class:`Frame`
or returns ``None`` to abstain.

Abstention is a feature: on vague input ("clean up my files") we return
``None`` rather than guess a command.

----------------------------------------------------------------------------
Abstention gate (Task 05, P1.1) — supersedes the old vague-"big" rule
----------------------------------------------------------------------------
An intent is emitted ONLY when its defining slot is present:
  * ``find_by_size`` needs ``size_bytes``,
  * ``find_by_time`` needs ``days``,
  * ``find_by_name`` needs ``pattern``.
A size cue with no number ("biggest files", "big files in downloads") names
a *goal* but no threshold. Emitting ``find_by_size`` without ``size_bytes``
compiles to a bare ``find . -type f`` — a match-everything command that looks
like it worked while ignoring the request. Per CLAUDE.md invariant #6
("abstain over guess"), we return ``None`` instead. :func:`abstain_hint` then
lets the CLI say what was missing (e.g. 'how big? try "over 100MB"').

(An earlier revision resolved "big ..." to a thresholdless ``find_by_size``.
That was the silent-slot-dropping bug this task fixes.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

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


def _parse_file_discovery(text: str, low: str) -> Frame | None:
    ext = _detect_ext(low)
    size_bytes, size_cue = _detect_size(low)
    days = _detect_time(low)
    pattern = _detect_name(text)
    path = _detect_path(text, low)

    slots: dict = {"path": path}
    if ext is not None:
        slots["ext"] = ext

    # Intent precedence: size -> time -> name -> type -> abstain.
    #
    # Abstention gate (Task 05, CLAUDE.md invariant #6): an intent is only
    # emitted when its DEFINING slot is present. A size cue with no numeric
    # threshold ("biggest files") would compile to a match-everything
    # `find . -type f`, so we abstain instead of dropping the slot silently.
    if size_cue:
        if size_bytes is None:
            return None  # size intent, no threshold -> abstain (see hint)
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


def _detect_path_arg(text: str, low: str) -> str | None:
    """A concrete file/dir the request names, or None. Prefers an explicit
    quote, then a slash path, then a bare ``name.ext``."""
    m = _QUOTED_RE.search(text)
    if m:
        return m.group(1)
    m = _PATH_TOKEN_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _FILE_TOKEN_RE.search(text)
    if m:
        return m.group(1)
    return None


# --------------------------------------------------------------------------
# Domain: file_inspection (Task 08) — single-command intents only.
# --------------------------------------------------------------------------

_COUNT_LINES_RE = re.compile(
    r"\b(?:how many lines|line count|number of lines|count .* lines)\b"
)
_HEAD_RE = re.compile(
    r"\b(?:head\b|first\s+\d+\s+\w*\s*lines?|first\s+\d+\s+lines?"
    r"|top of|beginning of|column (?:names|headers)|header row)\b"
)
_TAIL_RE = re.compile(r"\b(?:tail\b|last\s+\d+\s+\w*\s*lines?|end of)\b")
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


def _parse_file_inspection(text: str, low: str):
    folder = bool(_FOLDER_RE.search(low))
    is_count = bool(_COUNT_LINES_RE.search(low))
    is_head = bool(_HEAD_RE.search(low))
    is_tail = bool(_TAIL_RE.search(low))
    is_type = bool(_TYPE_RE.search(low)) or "format" in low
    is_stat = bool(_STAT_RE.search(low))
    # size of a FILE (in bytes); a folder/disk "size" belongs to filesystem.
    is_size = (("size" in low or "bytes" in low) and not folder)

    # Broad action categories, used ONLY to spot a compound request. The
    # literal nouns catch "preview, count and size ..." even though no single
    # precise intent cue fires for all three.
    broad = set()
    if "preview" in low or is_head or is_tail:
        broad.add("preview")
    if "count" in low or is_count:
        broad.add("count")
    if is_size:
        broad.add("size")
    if is_type:
        broad.add("type")
    if is_stat:
        broad.add("stat")

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
    r"\b(?:distinct|unique|dedupe|deduplicate|duplicates removed|without duplicates)\b",
    re.IGNORECASE,
)
_SORT_RE = re.compile(r"\b(?:sort|alphabetical(?:ly)?|in order|ascending)\b", re.IGNORECASE)
_RECURSIVE_RE = re.compile(
    r"\b(?:across|recursiv\w*|everywhere|throughout|in all"
    r"|(?:in|within|under) the (?:project|repo|codebase|source|src|configs?))\b",
    re.IGNORECASE,
)
_COUNT_MATCH_RE = re.compile(r"\b(?:how many|how often|count|number of times)\b", re.IGNORECASE)

_ALLCAPS_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
_WORD_PAT_RE = re.compile(
    r"\b(?:the\s+)?(?:word|string|phrase|token|term)\s+['\"]?([A-Za-z0-9_./+-]+)",
    re.IGNORECASE,
)
_SEARCHVERB_RE = re.compile(
    r"\b(?:search for|grep(?:\s+for)?|look for|locate)\s+['\"]?([A-Za-z0-9_./+-]+)",
    re.IGNORECASE,
)
_VAGUE_PAT = {"stuff", "things", "thing", "something", "anything", "it", "them", "that"}

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
    m = _QUOTED_RE.search(text)
    if m:
        return m.group(1)
    m = _WORD_PAT_RE.search(text)
    if m:
        return m.group(1).strip(".,!?;:")
    m = _SEARCHVERB_RE.search(text)
    if m:
        tok = m.group(1).strip(".,!?;:")
        if tok.lower() not in _VAGUE_PAT:
            return tok
    m = _ALLCAPS_RE.search(text)   # TODO, FIXME, API_URL, SUCCESS
    if m:
        return m.group(1)
    m = _LOG_WORD_RE.search(low)
    if m:
        return _LOG_CANON[m.group(1).lower()]
    return None


def _grep_dir(text: str, low: str) -> str | None:
    m = _DIR_NOUN_RE.search(text)
    if m:
        return m.group(1)
    m = _PREP_DIR_RE.search(text)
    if m:
        cand = m.group(1)
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

    ic = bool(_IGNORE_CASE_RE.search(low)) or (pattern.lower() in _CASE_WORDS)
    i = "i" if ic else ""

    if _RECURSIVE_RE.search(low):
        slots = {"gflags": "-Rn" + i + "F", "pattern": pattern}
        d = _grep_dir(text, low) or _detect_path_arg(text, low)
        if d is not None:
            slots["path"] = d
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


# --------------------------------------------------------------------------
# Domain: processes (Task 10) — read-only intents. kill/pkill abstain.
# --------------------------------------------------------------------------

_KILL_RE = re.compile(r"\b(?:kill|pkill|killall)\b", re.IGNORECASE)
_PORT_RE = re.compile(r"\bport\s+#?(\d{1,5})\b", re.IGNORECASE)
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
    r"|show (?:me )?(?:all )?(?:the )?(?:running )?processes)\b",
    re.IGNORECASE,
)
_FIND_PROC_RE = re.compile(
    r"\bis\s+(?:the\s+)?([\w.+-]+)\s+(?:process\s+)?(?:running|up|alive|active)\b"
    r"|\bfind\s+(?:the\s+)?([\w.+-]+)\s+process\b"
    r"|\b(?:process|pgrep)\s+(?:named|called|matching|for)\s+([\w.+-]+)\b",
    re.IGNORECASE,
)


def _top_count(low: str) -> int:
    m = _TOPN_RE.search(low)
    if m:
        return int(m.group(1) or m.group(2))
    return 10


def _parse_processes(text: str, low: str):
    # Destructive verbs are out of scope for Tier 1 → abstain (and, crucially,
    # do not let "kill python" fall through to file_discovery's python→py).
    if _KILL_RE.search(low):
        return _ABSTAIN

    m = _PORT_RE.search(low)
    if m:
        return Frame("process_on_port", {"port": int(m.group(1))})

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

    if _RUNNING_RE.search(low):
        return Frame("list_processes", {})

    return None


# Router order: specific domains first, file_discovery last (see parse()).
_ROUTER = (
    _parse_file_inspection,
    _parse_text_and_logs,
    _parse_processes,
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
    return None
