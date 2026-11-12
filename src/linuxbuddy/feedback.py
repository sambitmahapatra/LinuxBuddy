"""Task 46 (B) — offline feedback capture for the continual-learning loop.

When `lb` ABSTAINS (rules + encoder both decline, no command emitted), append the
request to a LOCAL, OFFLINE log: ``<cache>/feedback.jsonl``. Abstains are the clean,
high-signal miss source — a phrasing the model could not place. The log never leaves
the machine (consistent with LinuxBuddy's offline identity): no network, no telemetry.

The user owns it: ``lb --feedback`` prints it, ``lb --feedback-clear`` wipes it, and
the path is ``$LINUXBUDDY_CACHE_DIR/feedback.jsonl`` (default
``~/.cache/linuxbuddy/feedback.jsonl``).

This is the ONE always-on addition the loop needs, and it is deliberately tiny and
defensive: every operation is wrapped so a feedback failure can NEVER break `lb`
(an unwritable cache dir is a silent no-op). Detecting a user's *edit/rejection* of
an emitted command is a harder widget change — noted as future work, not built here.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .session import cache_dir           # reuse the one cache-dir convention

__all__ = ["log_abstain", "feedback_path", "read", "clear"]


def feedback_path() -> Path:
    return Path(cache_dir()) / "feedback.jsonl"


def log_abstain(request: str, path_kind: str) -> None:
    """Append one abstain record. NEVER raises — a feedback failure must not break
    `lb` (unwritable cache dir / full disk → silent no-op)."""
    try:
        if not request or not request.strip():
            return
        p = feedback_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "request": request,
            "cwd": os.getcwd(),
            "ts": round(time.time(), 3),
            "path": path_kind,            # "single" | "session"
            "outcome": "abstain",
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass                              # offline log is best-effort; never fatal


def read() -> list[dict]:
    try:
        return [json.loads(l) for l in feedback_path().read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def clear() -> int:
    """Remove the log; return how many records were discarded (0 if none)."""
    n = len(read())
    try:
        feedback_path().unlink()
    except OSError:
        pass
    return n
