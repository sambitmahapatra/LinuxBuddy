"""Zero-shot intent matcher — a pretrained bi-encoder, NO fine-tuning (Task 37).

The matcher embeds each intent's natural-language description (from
``kb/intent_descriptions.yaml``) and ranks an utterance against all of them by
cosine similarity. Because 27/85 intents have no training data, a softmax
classifier is impossible — but a bi-encoder matches utterances to descriptions,
so every intent (even zero-data ones) is reachable through its description.

This is a LOCAL embedding model (MiniLM), not a generative LLM: no API, no
network at inference after the one-time model cache, and nothing executes — the
matcher only returns a ranking. It is a pure function with no side effects and no
`lb`/router integration (that is a later task).

Abstain is first-class: a bi-encoder ALWAYS returns a nearest neighbour, so we
reject on an absolute similarity threshold ``T`` (top-1 below T → _ABSTAIN) and
also expose the top1−top2 margin as a secondary ambiguity signal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DESCRIPTIONS_PATH = REPO_ROOT / "kb" / "intent_descriptions.yaml"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
ABSTAIN = "_ABSTAIN"

# Per-model input conventions (query = utterance, doc = intent description).
# Using the wrong convention rigs the bake-off, so each follows its model card:
#   e5-*          : REQUIRE "query: " / "passage: " prefixes.
#   bge-*-en-v1.5 : query gets the retrieval instruction; passages get none.
#   gte-*         : no instruction/prefix per the thenlper card (symmetric).
#   all-MiniLM-*  : no prefix.
# Matched by substring of the model name; falls back to no prefix.
_CONVENTIONS = [
    ("e5-", ("query: ", "passage: ")),
    ("bge-", ("Represent this sentence for searching relevant passages: ", "")),
    ("gte-", ("", "")),
    ("minilm", ("", "")),
]


def conventions(model_name: str) -> tuple[str, str]:
    """(query_prefix, doc_prefix) for a model, by its documented convention."""
    low = model_name.lower()
    for key, pair in _CONVENTIONS:
        if key in low:
            return pair
    return ("", "")

# Anchor-text strategies (Part A asks us to try both and report which is better):
#   "desc"     — embed the description only (one vector per intent)
#   "desc+ex"  — embed description AND each example separately, mean-pool them
MODES = ("desc", "desc+ex")


# --------------------------------------------------------------------------
# Descriptions
# --------------------------------------------------------------------------
def load_descriptions(path: Path = DESCRIPTIONS_PATH) -> dict[str, dict]:
    """Parse intent_descriptions.yaml. Uses PyYAML when available (ML env); the
    coverage test uses top_level_keys() instead, which needs no YAML library."""
    import yaml  # available in the ML env; not a runtime dep of `lb`
    data = yaml.safe_load(path.read_text())
    return data or {}


def top_level_keys(path: Path = DESCRIPTIONS_PATH) -> list[str]:
    """Extract the intent ids (column-0 keys) with a stdlib regex, so coverage can
    be checked under the main venv without PyYAML."""
    keys = []
    for line in path.read_text().splitlines():
        m = re.match(r"^([A-Za-z_][\w]*):\s*$", line)
        if m:
            keys.append(m.group(1))
    return keys


def anchor_texts(descs: dict[str, dict], mode: str) -> dict[str, list[str]]:
    """The text(s) to embed per intent, by strategy."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; pick from {MODES}")
    out: dict[str, list[str]] = {}
    for intent, spec in descs.items():
        desc = (spec or {}).get("description", "").strip()
        texts = [desc] if desc else []
        if mode == "desc+ex":
            texts += [e for e in (spec or {}).get("examples", []) if e]
        out[intent] = texts or [intent.replace("_", " ")]
    return out


# --------------------------------------------------------------------------
# Model (cached)
# --------------------------------------------------------------------------
@lru_cache(maxsize=2)
def load_model(name: str = DEFAULT_MODEL):
    import torch
    from sentence_transformers import SentenceTransformer
    torch.manual_seed(0)                 # inference is deterministic anyway
    return SentenceTransformer(name)


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------
@dataclass
class IntentIndex:
    intent_ids: list[str]
    matrix: "any"          # (n_intents, dim) float32, L2-normalized
    model: "any"
    mode: str
    query_prefix: str = ""
    model_name: str = DEFAULT_MODEL

    @classmethod
    def build(cls, mode: str = "desc", model_name: str = DEFAULT_MODEL,
              descs: dict | None = None) -> "IntentIndex":
        import numpy as np
        descs = descs if descs is not None else load_descriptions()
        model = load_model(model_name)
        q_prefix, d_prefix = conventions(model_name)
        texts_by_intent = anchor_texts(descs, mode)
        intent_ids = sorted(texts_by_intent)          # stable order
        vecs = []
        for intent in intent_ids:
            texts = [d_prefix + t for t in texts_by_intent[intent]]
            emb = model.encode(texts, normalize_embeddings=True,
                               show_progress_bar=False)
            emb = np.atleast_2d(np.asarray(emb, dtype="float32"))
            pooled = emb.mean(axis=0)                  # mean-pool anchors
            n = np.linalg.norm(pooled)
            vecs.append(pooled / n if n else pooled)
        return cls(intent_ids=intent_ids,
                   matrix=np.vstack(vecs).astype("float32"),
                   model=model, mode=mode, query_prefix=q_prefix,
                   model_name=model_name)

    @classmethod
    def cached(cls, mode: str = "desc", model_name: str = DEFAULT_MODEL,
               cache_path=None, descs: dict | None = None) -> "IntentIndex":
        """Like build(), but load the 85 description embeddings from disk when a
        valid cache exists (Guardrail 5 — keep the model off re-encoding the fixed
        descriptions on every abstain call). The utterance is still encoded live.
        The cache is invalidated by a fingerprint over model+mode+descriptions."""
        import hashlib
        import json as _json

        import numpy as np
        descs = descs if descs is not None else load_descriptions()
        fp = hashlib.sha256(
            (model_name + "|" + mode + "|"
             + _json.dumps({k: (v or {}) for k, v in descs.items()}, sort_keys=True)
             ).encode()).hexdigest()[:16]
        cache_path = Path(cache_path) if cache_path else None
        if cache_path and cache_path.exists():
            try:
                data = np.load(cache_path, allow_pickle=False)
                if str(data["fp"]) == fp:
                    return cls(intent_ids=[str(x) for x in data["intent_ids"]],
                               matrix=data["matrix"].astype("float32"),
                               model=load_model(model_name), mode=mode,
                               query_prefix=str(data["query_prefix"]),
                               model_name=model_name)
            except Exception:
                pass  # corrupt/old cache → rebuild
        idx = cls.build(mode=mode, model_name=model_name, descs=descs)
        if cache_path:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                np.savez(cache_path, matrix=idx.matrix,
                         intent_ids=np.array(idx.intent_ids),
                         query_prefix=np.array(idx.query_prefix), fp=np.array(fp))
            except Exception:
                pass  # caching is best-effort; never fail the lookup over it
        return idx

    def rank(self, utterance: str) -> list[tuple[str, float]]:
        """All intents ranked by cosine similarity (desc)."""
        import numpy as np
        q = self.model.encode([self.query_prefix + utterance],
                              normalize_embeddings=True, show_progress_bar=False)
        q = np.asarray(q, dtype="float32")[0]
        sims = self.matrix @ q                         # cosine (both normalized)
        order = np.argsort(-sims)
        return [(self.intent_ids[i], float(sims[i])) for i in order]

    def classify(self, utterance: str, T: float, margin_min: float = 0.0):
        """Return (prediction, top1_score, margin, ranked). prediction is a valid
        intent id or _ABSTAIN (top1 < T, or margin < margin_min)."""
        ranked = self.rank(utterance)
        top1_intent, top1 = ranked[0]
        top2 = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top1 - top2
        if top1 < T or margin < margin_min:
            return ABSTAIN, top1, margin, ranked
        return top1_intent, top1, margin, ranked
