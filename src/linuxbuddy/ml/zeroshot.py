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

    @classmethod
    def build(cls, mode: str = "desc", model_name: str = DEFAULT_MODEL,
              descs: dict | None = None) -> "IntentIndex":
        import numpy as np
        descs = descs if descs is not None else load_descriptions()
        model = load_model(model_name)
        texts_by_intent = anchor_texts(descs, mode)
        intent_ids = sorted(texts_by_intent)          # stable order
        vecs = []
        for intent in intent_ids:
            emb = model.encode(texts_by_intent[intent], normalize_embeddings=True,
                               show_progress_bar=False)
            emb = np.atleast_2d(np.asarray(emb, dtype="float32"))
            pooled = emb.mean(axis=0)                  # mean-pool anchors
            n = np.linalg.norm(pooled)
            vecs.append(pooled / n if n else pooled)
        return cls(intent_ids=intent_ids,
                   matrix=np.vstack(vecs).astype("float32"),
                   model=model, mode=mode)

    def rank(self, utterance: str) -> list[tuple[str, float]]:
        """All intents ranked by cosine similarity (desc)."""
        import numpy as np
        q = self.model.encode([utterance], normalize_embeddings=True,
                              show_progress_bar=False)
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
