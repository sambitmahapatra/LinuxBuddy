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
    if re.search(r"\bcount\b", low) or is_count:
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
    # kill / pkill (Task 15): destructive, gated to the maze by the P2.0 gate.
    if _KILL_RE.search(low):
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
    r"\bonly\s+i\s+(?:can|should)\s+(?:read|edit|see|read or edit)\b"
    r"|\bprivate\b|\bonly\s+me\b|\bonly\s+my(?:self)?\b", re.IGNORECASE
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
_FS_DISK_RE = re.compile(
    r"\b(?:how big|disk usage|how much space|using space|take[sn]? up|du\b"
    r"|size of .* (?:folder|dir|directory))\b",
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
        obj = next(g for g in m.groups() if g)
        if obj.lower() not in _CHMOD_OBJ_STOP:
            return obj
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
    if _EMPTY_RE.search(low):
        return _ABSTAIN  # dir_empty deferred (needs $(...) command substitution)

    if _FS_WRITABLE_RE.search(low):
        return _fs_frame("check_writable", text, low)
    if _FS_READABLE_RE.search(low):
        return _fs_frame("check_readable", text, low)
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
_ARC_SIZE_RE = re.compile(r"\bhow big\b|\bsize of\b", re.IGNORECASE)
_ARC_INTO_RE = re.compile(
    r"\binto\s+(?:the\s+)?([\w./-]+)|\bto\s+(?:the\s+)?([\w./-]+)\s+(?:folder|dir)\b",
    re.IGNORECASE,
)


def _arc_is_zip(archive: str) -> bool:
    return archive.lower().endswith(".zip")


def _parse_archives(text: str, low: str):
    archive = _ARCHIVE_FILE_RE.search(text)
    archive = archive.group(1) if archive else None

    # 1. extract: unpack <archive> into <dir> → mkdir && tar (2-stage).
    if _ARC_EXTRACT_RE.search(low) and archive is not None:
        m = _ARC_INTO_RE.search(text)
        dest = (m.group(1) or m.group(2)) if m else None
        slots = {"archive": archive}
        if dest is not None:
            slots["path"] = dest
        return Frame("extract_archive", slots)

    # 2. create: package the <name> folder into <archive> (output is .tar.gz).
    if _ARC_CREATE_RE.search(low):
        slots = {"parent": "."}
        if archive is not None:
            slots["archive"] = archive
        m = _FOLDER_NAME_RE.search(low)
        if m and m.group(1).lower() not in _ARTICLES:
            slots["name"] = m.group(1)
        return Frame("create_archive", slots)

    # 3. list contents: tar -tf (or zipfile -l for .zip).
    if _ARC_LIST_RE.search(low) and archive is not None:
        intent = "list_zip" if _arc_is_zip(archive) else "list_archive"
        return Frame(intent, {"archive": archive})

    # 4. integrity check: gzip -t.
    if _ARC_INTEGRITY_RE.search(low) and archive is not None:
        return Frame("archive_integrity", {"archive": archive})

    # 5. single-file compress: gzip -k (no "into <archive>" — that was create).
    if _ARC_COMPRESS_RE.search(low):
        slots = {}
        p = _detect_path_arg(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("compress_file", slots)

    # 6. size of a named archive: du -h.
    if _ARC_SIZE_RE.search(low) and archive is not None:
        return Frame("archive_size", {"archive": archive})

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


def _parse_python(text: str, low: str):
    # Deferred families abstain (network / shell-state / long-running). Checked
    # first so "run setup in the venv" doesn't slip through as run_script.
    if _PY_INSTALL_RE.search(low) or _PY_VENV_RE.search(low) or _PY_SERVER_RE.search(low):
        return _ABSTAIN

    if _PY_SYNTAX_RE.search(low):
        slots: dict = {}
        p = _detect_path_arg(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("check_syntax", slots)

    if _PY_RUN_RE.search(low):
        slots = {}
        p = _detect_path_arg(text, low)
        if p is not None:
            slots["path"] = p
        return Frame("run_script", slots)

    m = _PY_PKG_RE.search(text)
    if m:
        pkg = next(g for g in m.groups() if g)
        return Frame("check_package", {"pkg": pkg})

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
_WS_INSTALLED_RE = re.compile(
    r"\bdo\s+i\s+have\s+([\w.+-]+)(?:\s+installed)?\b"
    r"|\bis\s+([\w.+-]+)\s+installed\b"
    r"|\b(?:command\s+-v|which)\s+([\w.+-]+)\b",
    re.IGNORECASE,
)
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
    r"|\bcommands\s+i\s+(?:used|ran|typed)\b|\b(?:earlier|previous)\s+commands\b", re.IGNORECASE,
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

    m = _WS_INSTALLED_RE.search(text)
    if m:
        tool = next(g for g in m.groups() if g)
        return Frame("check_installed", {"tool": tool})

    if _WS_GO_HOME_RE.search(low):
        return Frame("go_home", {})
    if _WS_GO_BACK_RE.search(low):
        return Frame("go_back", {})
    m = _WS_GOTO_RE.search(text)
    if m:
        path = _detect_path_arg(text, low) or m.group(1)
        return Frame("goto", {"path": path})

    if _WS_WHERE_RE.search(low):
        return Frame("where_am_i", {})
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


# Router order: specific domains first, file_discovery last (see parse()).
# python sits before text so "check X.py for syntax errors" is check_syntax,
# not a grep for "errors". archives sits before filesystem so
# "how big is <archive>.tar.gz" routes to archive_size, not disk_usage.
# workspace sits after filesystem (file-ish queries stay with filesystem) and
# before file_discovery (it catches navigation/shell verbs file_discovery
# would otherwise abstain on).
_ROUTER = (
    _parse_file_inspection,
    _parse_python,
    _parse_text_and_logs,
    _parse_processes,
    _parse_archives,
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
