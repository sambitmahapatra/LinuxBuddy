"""Task 45 — context-aware resolution for the multi-turn FALLBACK seam.

The value-add seam (see asbuilt_summary.md / attention_spike_report.md): when
`session.classify()` returns **`fallback`** on an elliptical turn that still has a
live `SessionFrame`, the old behaviour dropped to single-turn and LOST the frame —
"which of those is heaviest" was parsed context-free and abstained. The rules
already handle in-vocab refine/operate (48/49); the gap is exactly the
*novel-phrasing* elliptical operate turns ("the beefiest one", "give me a count of
those") that fall to `fallback` WITH a frame.

This module recovers those, **torch-free**, by reusing the shipped ONNX encoder:
  1. ACT/MODIFIER recovery — embed the **current-turn span** pooled from the
     *contextual* sequence (`history . current`), NOT the current turn alone and
     NOT the whole blended embedding (Finding 3). Match it to the intent
     descriptions; recover an operate modifier (max-by-size / count).
  2. REFERENCE binding — the elided target is the frame's accumulated target; the
     recovered delta merges into the EXISTING `SessionFrame`, so the prior
     name/size/mtime survive. (Single-target frames only — the eval has no
     multi-target chains; we do not over-engineer disambiguation.)

The L4H4 cross-turn ATTENTION stays dev-time (`experiments/task44_spike/`, the
figure + the 98% held-out coreference metric). Runtime imports NO torch — only the
existing onnxruntime/tokenizers/numpy stack, lazily, on the fallback turn.

Guardrails (mirror the single-turn hybrid, Task 39):
  * Additive & fallback-only — returns a merge-delta or None; never a command.
  * SAFETY (invariant #6) — a destructive elliptical turn is NEVER recovered: a
    destructive cue, or a top intent that isn't a READ operate, returns None →
    abstain. We never guess an `rm`/`mv` target from context.
  * Graceful degradation — any missing dep/checkpoint/failure returns None → the
    session path behaves exactly as before (rules → fallback → single-turn).
    `LINUXBUDDY_ENCODER=0` forces it off.
  * Off the fast path — nothing here imports onnxruntime/numpy at module load; the
    ML stack is imported lazily, only on the fallback turn.

Top-level imports are stdlib + pure-stdlib project modules ONLY.
"""
from __future__ import annotations

import re
from pathlib import Path

from .hybrid import _load_config          # reuse the single-turn config loader

__all__ = ["resolve_fallback"]

REPO_ROOT = Path(__file__).resolve().parents[2]

# A top intent -> the SessionFrame operate delta it recovers. Only READ operates
# are here; find_smallest/delete_file/etc. are deliberately absent -> abstain.
_OP_MAP = {
    "find_largest": {"op": "show", "modifier": "max-by-size"},
    "session_find_biggest": {"op": "show", "modifier": "max-by-size"},
    "count_files": {"op": "count", "modifier": "count"},
    "count_lines": {"op": "count", "modifier": "count"},
    "count_matches": {"op": "count", "modifier": "count"},
    "session_count": {"op": "count", "modifier": "count"},
}

# An anaphoric pronoun -> the turn refers back to the running set.
_PRONOUN_RE = re.compile(r"\b(one|ones|them|those|these|it)\b", re.IGNORECASE)

# A destructive cue -> NEVER recover (invariant #6). Superset of the session
# fileop-lead verbs plus destructive synonyms; matched anywhere in the turn.
_DESTRUCTIVE_CUE_RE = re.compile(
    r"\b(delete|remove|erase|wipe|nuke|trash|drop|discard|del|rm|unlink"
    r"|get\s+rid\s+of|throw\s+(?:away|out)|clear\s+out"
    r"|move|mv|rename|chmod|kill)\b",
    re.IGNORECASE,
)


def _is_elliptical(low: str) -> bool:
    """A turn that plausibly continues the running query: it carries an anaphoric
    pronoun, or it is short (a bare superlative/aggregate like 'largest please',
    'which hogs the most room'). We are already past classify -> fallback, so this
    only narrows which fallbacks are worth an encoder call."""
    if _PRONOUN_RE.search(low):
        return True
    return len(low.split()) <= 7


def _history_texts(frame) -> list[str]:
    """The chain so far, from the frame's own history (requests only)."""
    hist = [h.get("request", "") for h in getattr(frame, "history", []) if h.get("request")]
    return hist[-4:]                       # recent context is enough to contextualize


def _span_embedding(encoder, history: list[str], current: str):
    """Mean-pool the CURRENT-TURN token span out of the contextual sequence
    'history . current' (Finding-3 fix), L2-normalized. Uses only the ONNX
    encoder's already-public session/tokenizer — no change to onnx_encoder.py."""
    import numpy as np
    if history:
        prefix = " . ".join(history)
        joined = prefix + " . " + current
        start = len(prefix) + len(" . ")
    else:
        joined, start = current, 0
    e = encoder.tokenizer.encode(joined)
    feeds = {"input_ids": np.array([e.ids], dtype=np.int64),
             "attention_mask": np.array([e.attention_mask], dtype=np.int64)}
    if "token_type_ids" in encoder.input_names:
        feeds["token_type_ids"] = np.zeros((1, len(e.ids)), dtype=np.int64)
    out = encoder.session.run(None, feeds)[0][0]          # (T, 384) token embeddings
    # current-turn tokens: char-offset at/after the current turn, non-special.
    idxs = [k for k, (a, b) in enumerate(e.offsets)
            if a >= start and not (a == 0 and b == 0)]
    if not idxs:
        return None
    pooled = out[idxs].astype(np.float32).mean(0)
    n = float(np.linalg.norm(pooled))
    return pooled / n if n else pooled


def resolve_fallback(text: str, frame):
    """Recover an operate delta for an elliptical fallback turn, or (None, {}).

    Returns (delta, info): `delta` is a `SessionFrame.merge`-compatible operate
    delta; `info` carries the encoder source/intent/score for the review note.
    NEVER raises; any failure degrades to (None, {}) → rules/single-turn."""
    if frame is None or not text or not text.strip():
        return None, {}
    low = text.lower().strip()

    # SAFETY: a destructive elliptical turn is never recovered from context.
    if _DESTRUCTIVE_CUE_RE.search(low):
        return None, {}
    if not _is_elliptical(low):
        return None, {}

    cfg = _load_config()
    if not cfg["enabled"]:
        return None, {}
    model_dir = REPO_ROOT / str(cfg["model_path"])
    if not (model_dir / "onnx" / "encoder.onnx").exists():
        return None, {}

    try:
        from .ml.onnx_encoder import OnnxIntentIndex
        idx = OnnxIntentIndex.cached(model_dir)
        import numpy as np
        emb = _span_embedding(idx.encoder, _history_texts(frame), text)
        if emb is None:
            return None, {}
        sims = idx.matrix @ emb.astype("float32")
        order = np.argsort(-sims)
        top_i, top1 = idx.intent_ids[int(order[0])], float(sims[int(order[0])])
    except Exception:
        return None, {}                      # any failure → pure rules

    delta = _OP_MAP.get(top_i)
    if delta is None:                        # not a READ operate → abstain (safe)
        return None, {}
    if top1 < float(cfg["t_read"]):          # not confident enough → abstain
        return None, {}

    info = {"source": "encoder", "intent": top_i, "score": round(top1, 3),
            "act": "operate", "modifier": delta["modifier"]}
    return dict(delta), info
