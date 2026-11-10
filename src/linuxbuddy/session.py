"""Multi-turn session state for LinuxBuddy v2 (Task 30, Phase 1 spike).

The thin slice: prove the multi-turn *mechanic* with a running query frame, a
disk-backed store (one Ctrl-G = one fresh process, so state must persist), and a
RULES-based dialogue-act + delta detector. **No model here** — the encoder is
Phase 2 (CLAUDE.md / ROADMAP). Everything renders through the existing v1
pipeline: ``to_command_plan()`` returns a plain :class:`~linuxbuddy.nlu.Frame`
that ``planner.compile`` + ``render.to_shell`` + ``gate`` handle unchanged.

Design choices (documented in LOG.md):
  * **Store key** = the per-terminal id the shell widget exports in
    ``$LINUXBUDDY_SESSION`` (Task 31). The widget runs ``lb`` inside a ``$(…)``
    command substitution — a fresh subshell with a *different* PID every Ctrl-G —
    so keying on ``os.getppid()`` gave a new file each turn and nothing
    accumulated. The exported id is stable for the life of the terminal and is
    inherited by every subshell, so all of a terminal's Ctrl-G calls share one
    frame. File: ``<cache>/session_<sanitized-id>.json``, ``<cache>`` =
    ``$LINUXBUDDY_CACHE_DIR`` or ``~/.cache/linuxbuddy``. A direct ``lb`` call
    without the widget (no env id) falls back to ``os.getppid()``.
  * **TTL** = 10 min. A stale frame is treated as absent (fresh parse).
  * **Reset** on the words "start over / reset / never mind / forget it", OR on a
    cwd change since the frame was written (a ``cd`` means a fresh context).
  * **"yesterday"** → ``-daystart -mtime 1`` (the whole previous calendar day),
    **"today"** → ``-daystart -mtime 0``. ``-daystart`` anchors -mtime to
    midnight, which matches the human calendar sense (plain ``-mtime 1`` means
    24–48h ago relative to *now*, which is not what "yesterday" means).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict

from .nlu import Frame, _detect_ext, _SIZE_UNDER_RE

__all__ = [
    "SessionFrame", "classify", "store_key", "cache_dir",
    "load", "save", "clear", "TTL_SECONDS",
]

TTL_SECONDS = 600  # 10 minutes


# --------------------------------------------------------------------------
# The running query frame
# --------------------------------------------------------------------------


@dataclass
class SessionFrame:
    op: str = "find"
    targets: dict = field(default_factory=dict)   # {"path": ".", "name": "*.csv"}
    filters: dict = field(default_factory=dict)   # {"size": "+100M", "mtime": "1"}
    modifier: str | None = None                   # "max-by-size" | "count" | None
    cwd: str = ""
    history: list = field(default_factory=list)   # [{"request":…, "act":…}]
    updated_at: float = 0.0
    shell_id: str = ""

    # ---- lifecycle ----
    def touch(self) -> None:
        self.updated_at = time.time()

    def is_stale(self, ttl: float = TTL_SECONDS) -> bool:
        return (time.time() - self.updated_at) > ttl

    def reset(self) -> None:
        """Clear the running query in place (keep identity: shell_id)."""
        self.op = "find"
        self.targets = {}
        self.filters = {}
        self.modifier = None
        self.history = []

    def record(self, request: str, act: str) -> None:
        self.history.append({"request": request, "act": act})
        self.history = self.history[-10:]

    # ---- the one mutation the detector drives ----
    def merge(self, delta: dict) -> None:
        """Accumulate a delta WITHOUT clobbering unrelated slots. A refine adds
        to targets/filters; an operate sets op/modifier. Existing -name/-size
        survive a later -mtime refine."""
        self.targets.update(delta.get("targets", {}))
        self.filters.update(delta.get("filters", {}))
        if delta.get("op"):
            self.op = delta["op"]
        if "modifier" in delta:
            self.modifier = delta["modifier"]
        self.touch()

    # ---- render bridge: produce the v1 plan object (a Frame) ----
    def to_command_plan(self) -> Frame:
        """Build the plain v1 Frame the existing planner consumes. The KB
        intent is chosen by the modifier; the accumulated targets/filters become
        its slots. No rendering happens here — compile()/to_shell() own that."""
        slots: dict = {"path": self.targets.get("path", ".")}
        if self.targets.get("name"):
            slots["name"] = self.targets["name"]
        if self.filters.get("size"):
            slots["size"] = self.filters["size"]
        if self.filters.get("mtime") is not None:
            slots["mtime"] = str(self.filters["mtime"])

        if self.modifier == "max-by-size":
            slots["printf_fmt"] = r"%s\t%p\n"
            return Frame("session_find_biggest", slots)
        if self.modifier == "count":
            return Frame("session_count", slots)
        return Frame("session_find", slots)

    # ---- (de)serialization ----
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionFrame":
        return cls(
            op=d.get("op", "find"),
            targets=dict(d.get("targets", {})),
            filters=dict(d.get("filters", {})),
            modifier=d.get("modifier"),
            cwd=d.get("cwd", ""),
            history=list(d.get("history", [])),
            updated_at=float(d.get("updated_at", 0.0)),
            shell_id=str(d.get("shell_id", "")),
        )

    # ---- build a fresh frame from a self-contained request ----
    @classmethod
    def from_request(cls, text: str, cwd: str, shell_id: str) -> "SessionFrame | None":
        """A NEW self-contained find request → a fresh frame, or None if the
        request carries nothing this spike can compose (caller falls back to the
        v1 single-turn path)."""
        low = text.lower()
        targets: dict = {"path": "."}
        filters: dict = {}
        name = _ext_glob(low)
        if name:
            targets["name"] = name
        size = _find_size(low)
        if size:
            filters["size"] = size
        day = _day_constraint(low)
        if day:
            filters.update(day)
        if "name" not in targets and not filters:
            return None  # nothing composable — let v1 single-turn handle it
        sf = cls(op="find", targets=targets, filters=filters, cwd=cwd,
                 shell_id=str(shell_id))
        sf.touch()
        return sf


# --------------------------------------------------------------------------
# Constraint extraction (rules; reuses v1 vocabulary where it fits)
# --------------------------------------------------------------------------

# Human find-size units -> find's unit letter. First letter decides the unit.
_SIZE_FIND_RE = re.compile(
    r"(\d+)\s*(gib|gb|gigabytes?|gigs?|g|mib|mb|megabytes?|megs?|m|kib|kb|kilobytes?|k)\b",
    re.IGNORECASE,
)
_UNIT_LETTER = {"g": "G", "m": "M", "k": "k"}


def _find_size(low: str) -> str | None:
    """A find -size value in human units, signed by direction: "larger than
    100MB" → "+100M", "under 10mb" → "-10M". Returns None if no size cue."""
    m = _SIZE_FIND_RE.search(low)
    if not m:
        return None
    n = m.group(1)
    unit = _UNIT_LETTER[m.group(2).lower()[0]]
    sign = "-" if _SIZE_UNDER_RE.search(low) else "+"
    return f"{sign}{n}{unit}"


def _day_constraint(low: str) -> dict:
    """Calendar-day modified filter → {"mtime": "N"} (used with -daystart)."""
    if re.search(r"\byesterday\b", low):
        return {"mtime": "1"}
    if re.search(r"\btoday\b", low):
        return {"mtime": "0"}
    return {}


def _ext_glob(low: str) -> str | None:
    ext = _detect_ext(low)
    return f"*.{ext}" if ext else None


# --------------------------------------------------------------------------
# Dialogue-act + delta detection (spike-grade rules)
# --------------------------------------------------------------------------

_RESET_RE = re.compile(
    r"\b(start over|reset|never ?mind|forget it|forget that|scratch that)\b",
    re.IGNORECASE,
)
# A clear discovery verb → the request stands on its own (a NEW query), so it is
# never read as a refine/operate on the previous one.
_OP_VERB_RE = re.compile(
    r"\b(find|search|locate|list|grep|show me|get me|give me)\b", re.IGNORECASE,
)
_REFINE_LEAD_RE = re.compile(r"^\s*(only|just|and|also|plus)\b", re.IGNORECASE)

# Task 33: a file-MANAGEMENT verb at the head of the request. These are never
# discovery queries, so the session layer must NOT claim them as a new/refine
# find just because the request happens to carry a filename with an extension
# (the Task-32 regression: "delete old.log" composed `find . -name '*.log'`
# instead of `rm`). When one leads, we hand the whole request to the v1
# single-turn path, whose router already routes move/copy/delete/rename to the
# file_management domain (and "remove the executable bit"/"remove duplicate
# lines" to chmod/text). Discovery verbs (find/list/locate/where/how many/
# recently modified/biggest) are disjoint from this set, so discovery is
# untouched. Anchored at the head so "find files to move" stays a find.
_FILEOP_LEAD_RE = re.compile(
    r"^\s*(?:please\s+|pls\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)?"
    r"(?:mv|cp|rm"
    r"|move|copy|rename|delete|remove|trash|put"
    r"|get\s+rid\s+of"
    r"|(?:make|create)\s+(?:a\s+)?copy"
    # mkdir phrasings: "make a folder logs" would otherwise be hijacked because
    # "logs" reads as a .log type — keep it a mkdir (single-turn make_dir).
    r"|(?:make|create|new|add)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:folder|dir|directory))\b",
    re.IGNORECASE,
)


def _composable(low: str) -> bool:
    """True if this spike can extract a find query (a type glob, a size, or a
    day constraint) from the text. Independent of the v1 router — "find CSV
    files…" routes to grep in v1 (uppercase CSV), but is composable here."""
    return bool(_ext_glob(low) or _find_size(low) or _day_constraint(low))


def _operate_delta(low: str) -> dict | None:
    """An operation on the CURRENT result set → op/modifier, filters kept."""
    if re.search(r"\b(biggest|largest)\b", low) or re.search(r"\bmost (?:space|disk)\b", low):
        return {"op": "show", "modifier": "max-by-size"}
    if (re.search(r"\bcount (?:them|these|those|it)\b", low)
            or re.search(r"\bhow many\b", low)
            or re.match(r"^\s*count\b", low)):
        return {"op": "count", "modifier": "count"}
    return None


def _refine_delta(text: str, low: str) -> dict | None:
    """A constraint that NARROWS the current set → a targets/filters delta.
    Fires on a leading only/just/and/also, or on a bare constraint phrase with
    no new discovery verb. Returns None when nothing narrowable is found."""
    if _OP_VERB_RE.search(low):
        return None  # has its own op → a new query, not a refinement
    delta: dict = {"targets": {}, "filters": {}}
    day = _day_constraint(low)
    if day:
        delta["filters"].update(day)
    size = _find_size(low)
    if size:
        delta["filters"]["size"] = size
    name = _ext_glob(low)
    if name:
        delta["targets"]["name"] = name
    has_constraint = bool(delta["filters"] or delta["targets"])
    if not has_constraint:
        return None
    # A leading only/just/and is a strong refine signal but not required — a bare
    # "modified yesterday" with a constraint is a refine too.
    return delta


def classify(text: str, frame: "SessionFrame | None") -> tuple[str, dict]:
    """Return (act, delta). act ∈ {reset, new, refine, operate, fallback}.

    Order: reset → self-contained-new (beats refine/operate) → operate → refine
    (both need a frame) → new-if-find → fallback. The fallback means "let the v1
    single-turn path handle it" — the safe default, and never a guessed op.
    """
    low = text.lower().strip()

    m = _RESET_RE.search(low)
    if m:
        remainder = (low[:m.start()] + low[m.end():]).strip(" ,.")
        return ("reset", {"remainder": remainder})

    # Task 33: a file-management verb owns the sentence → defer to single-turn
    # (which routes it to the file_management domain). Checked BEFORE the
    # composable-find checks so a filename extension can't hijack it into a find,
    # and before operate/refine so a mid-chain "delete old.log" is a fresh
    # destructive op, not a refinement of the running query.
    if _FILEOP_LEAD_RE.match(low):
        return ("fallback", {})

    # A self-contained find request (explicit verb + a composable query)
    # replaces the frame, even mid-chain — so "find all json files" is NEW, not a
    # refine of the previous query.
    if _OP_VERB_RE.search(low) and _composable(low):
        return ("new", {})

    if frame is not None:
        d = _operate_delta(low)
        if d is not None:
            return ("operate", d)
        d = _refine_delta(text, low)
        if d is not None:
            return ("refine", d)

    # No frame (or nothing to refine/operate on): a composable request starts a
    # fresh query; anything else is for the v1 single-turn path.
    if _composable(low):
        return ("new", {})
    return ("fallback", {})


# --------------------------------------------------------------------------
# Disk-backed store (one Ctrl-G = one process; state must persist to disk)
# --------------------------------------------------------------------------


def cache_dir() -> str:
    return os.environ.get("LINUXBUDDY_CACHE_DIR") or os.path.expanduser(
        "~/.cache/linuxbuddy"
    )


def _sanitize_key(sid: str) -> str:
    """Make an env-supplied id safe as a filename component — no path separators
    or spaces can leak into the store path."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", sid)
    return safe[:128] or "default"


def store_key() -> str:
    """The session key. Prefer the per-terminal id the widget exports in
    ``$LINUXBUDDY_SESSION`` (stable across the ``$(lb …)`` subshells each Ctrl-G
    spawns); fall back to the parent PID only for a direct ``lb`` call with no
    widget. When present, the env id is authoritative (Task 31)."""
    sid = os.environ.get("LINUXBUDDY_SESSION")
    if sid:
        return _sanitize_key(sid)
    return str(os.getppid())


def _store_path(key: str) -> str:
    return os.path.join(cache_dir(), f"session_{key}.json")


def _cleanup_stale(ttl: float = TTL_SECONDS) -> None:
    """Best-effort reaping of session files older than the TTL, so the cache
    doesn't accumulate one dead file per closed terminal. Never raises."""
    cutoff = time.time() - ttl
    try:
        names = os.listdir(cache_dir())
    except OSError:
        return
    for name in names:
        if not (name.startswith("session_") and name.endswith(".json")):
            continue
        p = os.path.join(cache_dir(), name)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


def load(key: str, ttl: float = TTL_SECONDS, cwd: str | None = None) -> "SessionFrame | None":
    """Load the frame for ``key``, or None. Returns None (fresh) when the file
    is missing/corrupt, the frame is past its TTL, or the cwd has changed since
    it was written (a ``cd`` resets context). Never raises on a bad file."""
    cwd = os.getcwd() if cwd is None else cwd
    path = _store_path(key)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    try:
        sf = SessionFrame.from_dict(data)
    except (TypeError, ValueError):
        return None
    if sf.is_stale(ttl):
        return None
    if sf.cwd and sf.cwd != cwd:
        return None  # navigated away → fresh context
    return sf


def save(key: str, frame: SessionFrame) -> None:
    frame.touch()
    frame.shell_id = frame.shell_id or key
    path = _store_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(frame.to_json())
    os.replace(tmp, path)  # atomic
    _cleanup_stale()       # reap dead terminals' files (the fresh one is kept)


def clear(key: str) -> None:
    try:
        os.remove(_store_path(key))
    except OSError:
        pass
