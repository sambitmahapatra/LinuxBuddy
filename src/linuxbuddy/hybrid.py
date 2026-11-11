"""Task 39 — the fine-tuned encoder as the rules fallback (single-turn, intent-only).

The ONE seam: `cli._run_single_turn` consults this module ONLY when the rules
return no frame (abstain). The encoder picks an INTENT id; slots are filled by
REUSING the rules' own detectors; the resulting Frame flows through the EXISTING
compile → gate → render pipeline. The encoder never builds a command string, and
the security boundary (shlex round-trip, `--` guard, maze containment) does not
move.

Guardrails honoured here:
  * Rules keep absolute priority — this runs only on abstain (cli seam).
  * Read/destructive asymmetry — two thresholds: a READ intent emits at `t_read`,
    a DESTRUCTIVE (write/delete/chmod/exit-3) intent needs the higher
    `t_destructive` AND a `margin_min`, else it abstains honestly.
  * Graceful degradation — any missing dep / checkpoint / failure returns None, so
    `lb` behaves exactly like v1. `LINUXBUDDY_ENCODER=0` forces pure-rules.
  * Off the fast path — nothing here imports torch/sentence-transformers at module
    load; the ML stack is imported lazily, only when the rules abstain. The 85
    description embeddings are cached to disk (IntentIndex.cached).

This module's top-level imports are stdlib + pure-stdlib project modules ONLY.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from . import gate
from .nlu import (Frame, _detect_ext, _detect_name, _detect_path, _detect_path_arg,
                  _detect_size, _detect_time, _dest_after, _fm_dest, _flarge_count,
                  _inspect_count, _largest_path, _size_sign, _stat_fmt, Raw,
                  _FM_MKDIR_RE, _FM_MOVE_RE)
from .planner import risk_ops

__all__ = ["classify_fallback"]

REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = REPO_ROOT / "ml_config.yaml"
_DEFAULTS = {"enabled": True, "model_path": "models/ft-minilm-l6",
             "t_read": 0.55, "t_destructive": 0.68, "margin_min": 0.05}
_note_shown = False


def _note_once(msg: str) -> None:
    global _note_shown
    if not _note_shown:
        print(f"LinuxBuddy: {msg}", file=sys.stderr)
        _note_shown = True


def _coerce(v: str):
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return float(v)
    except ValueError:
        return v


def _load_config() -> dict:
    """Read ml_config.yaml with a tiny stdlib parser (no PyYAML on this path), env
    override LINUXBUDDY_ENCODER=0 wins. Defaults apply when the file is absent."""
    cfg = dict(_DEFAULTS)
    if _CONFIG_PATH.exists():
        section = None
        for line in _CONFIG_PATH.read_text().splitlines():
            s = line.split("#", 1)[0].rstrip()
            if not s.strip():
                continue
            if not s.startswith(" ") and s.endswith(":"):
                section = s.strip()[:-1]
                continue
            if section == "encoder" and ":" in s:
                k, v = s.strip().split(":", 1)
                k = k.strip()
                if k in cfg:
                    cfg[k] = _coerce(v.strip())
    if os.environ.get("LINUXBUDDY_ENCODER") == "0":
        cfg["enabled"] = False
    return cfg


# --------------------------------------------------------------------------
# Slot filling — REUSE the rules' detectors. Never default a destructive target.
# Return None whenever a required slot can't be filled confidently → abstain.
# --------------------------------------------------------------------------
# Encoder-path-only slot heuristics (the rules' detectors are NOT modified, so no
# rule behaviour changes). These only fire on the abstain path to turn a correct
# encoder intent into a MEANINGFUL, bounded command instead of abstaining.
_ENC_TYPE = [
    (re.compile(r"\bspreadsheets?\b|\bexcel\b"), "csv"),
    (re.compile(r"\bnotebooks?\b"), "ipynb"),
]
_ENC_DAYS_1 = re.compile(r"\b(?:last|past)\s+day\b|\byesterday\b|\btoday\b"
                         r"|\blast\s+24\s*h(?:ours?|rs?)?\b", re.IGNORECASE)
_ENC_DAYS_WK = re.compile(r"\b(?:last|past)\s+week\b", re.IGNORECASE)


def _enc_ext(low: str):
    e = _detect_ext(low)
    if e:
        return e
    for rx, ext in _ENC_TYPE:
        if rx.search(low):
            return ext
    return None


def _enc_days(text: str, low: str):
    d = _detect_time(text)
    if d:
        return d
    if _ENC_DAYS_1.search(low):
        return 1
    if _ENC_DAYS_WK.search(low):
        return 7
    return None


def _optional_keys(intent: str) -> set[str]:
    from .kb import load_kb
    for cap in load_kb().values():
        spec = cap.get("intents", {}).get(intent)
        if spec:
            return set((spec.get("optional_args") or {}).keys())
    return set()

# path defaults to "." (a search ROOT, harmless). NEVER used for a file target.
_SEARCH = {"find_by_type", "find_by_name", "find_by_size", "find_by_time", "count_files"}
# path MUST be a concrete file/glob the user named (no default → no `rm .`).
_FILE_TARGET = {"delete_file", "compress_file", "check_syntax", "check_exists",
                "check_readable", "check_writable", "count_lines", "detect_type",
                "make_executable", "remove_executable", "run_script", "show_owner",
                "show_permissions", "show_size", "sort_lines", "unique_lines",
                "path_to_windows", "disk_usage"}
_ARCHIVE_TARGET = {"list_archive", "list_zip", "archive_integrity", "archive_size",
                   "extract_tar", "extract_zip"}
_PREVIEW = {"preview_head", "preview_tail"}


def fill_slots(intent: str, text: str, low: str) -> dict | None:
    """Slots for an encoder-chosen intent, or None to abstain. Mirrors the rules;
    any intent without a filler here returns None (safe — lb just abstains as v1)."""
    # slotless intents (base_argv has no placeholder) compile with {} directly.
    if not _required_keys(intent):
        return {}

    if intent in _SEARCH:
        opt = _optional_keys(intent)
        slots: dict = {"path": _detect_path(text, low)}
        if "ext" in opt and (e := _enc_ext(low)):
            slots["ext"] = e
        if "days" in opt and (d := _enc_days(text, low)):
            slots["days"] = d
        if "size_bytes" in opt:
            sb, _cue = _detect_size(low)
            if sb is not None:
                slots["size_bytes"] = f"{_size_sign(low)}{sb}"
        if "pattern" in opt and (p := _detect_name(text)):
            slots["pattern"] = p
        # Invariant #6: a find_* whose DEFINING slot wasn't extracted would compile
        # to a match-everything `find .`/`find . -type f` — abstain instead of
        # emitting that. (count_files is bounded by `| wc -l`, so it may count all.)
        defining = {"find_by_type": "ext", "find_by_time": "days",
                    "find_by_size": "size_bytes", "find_by_name": "pattern"}.get(intent)
        if defining and defining not in slots:
            return None
        return slots

    if intent in _FILE_TARGET:
        p = _detect_path_arg(text, low)
        return {"path": p} if p is not None else None

    if intent in _ARCHIVE_TARGET:
        a = _detect_path_arg(text, low)
        return {"archive": a} if a is not None else None

    if intent in _PREVIEW:
        p = _detect_path_arg(text, low)
        return {"path": p, "count": _inspect_count(low)} if p is not None else None

    if intent == "show_stat":
        p = _detect_path_arg(text, low)
        return {"path": p, "fmt": _stat_fmt(low)} if p is not None else None

    if intent in ("find_largest", "find_smallest"):
        return {"path": _largest_path(text, low), "count": _flarge_count(low)}

    if intent == "make_dir":
        m = _FM_MKDIR_RE.search(text)
        return {"path": m.group(1)} if m else None

    if intent == "move_file":
        m = _FM_MOVE_RE.search(text)
        if m:
            src = _detect_path_arg(m.group(1), m.group(1).lower())
            dest = _fm_dest(m.group(2))
            if src is not None and dest:
                return {"path": src, "dest": dest}
        return None

    if intent == "copy_file":
        src = _detect_path_arg(text, low)
        if src is None:
            return None
        dest = _dest_after(text)
        return {"path": src, "dest": dest or (str(src) + ".bak")}

    if intent == "goto":
        p = _detect_path_arg(text, low)
        return {"path": p} if p is not None and not isinstance(p, Raw) else None

    if intent == "process_on_port":
        m = re.search(r"\b(\d{2,5})\b", low)
        return {"port": m.group(1)} if m else None

    return None  # no filler → abstain (safe; equals v1 behaviour)


def _required_keys(intent: str) -> set[str]:
    from .kb import load_kb
    ph = re.compile(r"\{([a-z_]+)\}")
    for cap in load_kb().values():
        spec = cap.get("intents", {}).get(intent)
        if spec:
            keys: set[str] = set()
            for k in ("base_argv", "and_argv", "pipe_argv", "pipe2_argv", "pipe3_argv"):
                for el in spec.get(k, []) or []:
                    keys |= set(ph.findall(el))
            return keys
    return set()


# --------------------------------------------------------------------------
# The seam
# --------------------------------------------------------------------------
def classify_fallback(request: str):
    """Return (Frame, info) when the encoder confidently resolves a rules-abstain
    request, else (None, {}) — meaning fall through to the normal v1 abstain.
    NEVER raises: any failure degrades to pure rules."""
    cfg = _load_config()
    if not cfg["enabled"] or not request.strip():
        return None, {}

    model_dir = REPO_ROOT / str(cfg["model_path"])
    if not (model_dir / "config.json").exists():
        return None, {}  # no checkpoint → pure v1, silently

    try:
        from .ml.zeroshot import ABSTAIN, IntentIndex
    except Exception:
        _note_once("encoder dependencies unavailable; using rules only")
        return None, {}

    try:
        idx = IntentIndex.cached(mode="desc", model_name=str(model_dir),
                                 cache_path=str(model_dir / "index_desc.npz"))
        ranked = idx.rank(request)
    except Exception:
        _note_once("encoder unavailable; using rules only")
        return None, {}

    top1_i, top1 = ranked[0]
    top2 = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = top1 - top2
    if top1_i == ABSTAIN:
        return None, {}

    try:
        destructive = gate.is_destructive(risk_ops(top1_i))
    except Exception:
        return None, {}  # intent not in KB → abstain

    # Read/destructive asymmetry (Guardrail 3).
    T = cfg["t_destructive"] if destructive else cfg["t_read"]
    if top1 < T or (destructive and margin < cfg["margin_min"]):
        return None, {}

    slots = fill_slots(top1_i, request, request.lower())
    if slots is None:
        return None, {}

    info = {"source": "encoder", "intent": top1_i, "score": round(float(top1), 3),
            "margin": round(float(margin), 3), "destructive": destructive}
    return Frame(top1_i, slots), info
