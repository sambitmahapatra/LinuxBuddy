"""Task 44 — the attention cross-turn REFERENCE RESOLVER (dev-time spike).

NOT wired into `lb`/`session.py`. Runs only in the ML env:
    .venv-ml/bin/python -I experiments/task44_spike/eval_spike.py

Option 1.5 from attention_context_proposal.md. Given (history, current elliptical
turn), it does the two jobs the proposal assigns to ATTENTION — and nothing the
rules already own:

  1. COREFERENCE / REFERENCE RESOLUTION (attention's headline job). Run the
     fine-tuned torch encoder once over the joined chain, read the cross-turn
     attention, and find which prior-turn WORD the current turn's pronoun
     ("one/them/those/the ones/it") binds to -> map to the accumulated target.
  2. ACT/MODIFIER CROSS-CHECK (only to recover phrasings the regex misses). Pool
     the CURRENT-TURN SPAN embedding ONLY (Finding 3: never the whole blended
     sequence) and match it to the intent descriptions -> operate(max/min-by-size)
     / operate(count) / refine / destructive.

Everything is torch + dev-time; the ONNX runtime does not expose attention.
Rules keep SessionFrame state + dialogue-act detection; this module is additive.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
MODEL_DIR = str(REPO / "models" / "ft-minilm-l6")

# Words that are never the referent of a "the ones / which one" pronoun: the
# pronoun machinery itself, determiners, and the filter vocabulary (size/time).
# The referent we want is the TARGET TYPE noun ("csv", "logs", "python", ...).
_STOP = {
    "the", "a", "an", "those", "these", "them", "they", "it", "one", "ones",
    "that", "this", "of", "is", "are", "which", "what", "whichever", "show",
    "me", "give", "get", "how", "many", "much", "there", "all", "up", "please",
    "only", "just", "and", "also", "plus", "over", "under", "above", "below",
    "bigger", "larger", "smaller", "than", "from", "modified", "changed",
    "yesterday", "today", "recent", "empty", "big", "tiny", "small", "heavy",
    "heaviest", "largest", "biggest", "smallest", "fat", "fattest", "chunkiest",
    "bulkiest", "beefiest", "weightiest", "most", "room", "space", "disk",
    "hogs", "using", "among", "bunch", "count", "tally", "total", "headcount",
    "add", "drop", "trash", "rid", "find", "search", "locate", "list", "pull",
    "dig", "round", "scan", "for", "in", "mb", "gb", "kb",
}

# Pronoun / elliptical heads we try to resolve.
_PRONOUNS = {"one", "ones", "them", "those", "these", "it", "that"}


@lru_cache(maxsize=1)
def _load():
    """torch AutoModel (eager, so attentions are returned) + tokenizer."""
    import torch  # noqa
    import transformers
    tok = transformers.AutoTokenizer.from_pretrained(MODEL_DIR)
    mdl = transformers.AutoModel.from_pretrained(MODEL_DIR, attn_implementation="eager")
    mdl.eval()
    return mdl, tok


@lru_cache(maxsize=1)
def _desc_index():
    """Intent descriptions embedded with the SAME mean-pool-content-tokens +
    normalize as the current-turn span, so the cross-check cosine is consistent."""
    from linuxbuddy.ml.zeroshot import load_descriptions
    descs = load_descriptions()
    ids, texts = [], []
    for i, spec in descs.items():
        d = (spec or {}).get("description", "").strip()
        if d:
            ids.append(i)
            texts.append(d)
    vecs = np.vstack([_embed_text(t) for t in texts]).astype("float32")
    return ids, vecs


def _embed_text(text: str) -> np.ndarray:
    """Mean-pool content-token embeddings (exclude [CLS]/[SEP]) + L2-normalize."""
    import torch
    mdl, tok = _load()
    enc = tok(text, return_tensors="pt")
    with torch.no_grad():
        out = mdl(**enc)
    hid = out.last_hidden_state[0].numpy()           # (seq, dim)
    ids = enc["input_ids"][0].tolist()
    specials = set(tok.all_special_ids)
    keep = [k for k, tid in enumerate(ids) if tid not in specials]
    pooled = hid[keep].mean(axis=0)
    n = np.linalg.norm(pooled)
    return pooled / n if n else pooled


# --------------------------------------------------------------------------
# Encoding a chain: tokens, per-turn word spans, attentions
# --------------------------------------------------------------------------
class ChainEncoding:
    """One forward pass over the joined chain, exposing the pieces the resolver
    needs: word-level grouping, per-turn membership, and the attention tensor."""

    def __init__(self, turns: list[str]):
        import torch
        self.turns = turns
        mdl, tok = _load()
        # Join with " . " (the proven probe joining that produced the 0.626
        # cross-turn signal); the last turn is the "current" one.
        self.joined = " . ".join(turns)
        enc = tok(self.joined, return_tensors="pt")
        with torch.no_grad():
            out = mdl(**enc, output_attentions=True)
        self.toks = tok.convert_ids_to_tokens(enc["input_ids"][0])
        self.hidden = out.last_hidden_state[0].numpy()            # (S, dim)
        self.att = np.stack([a[0].numpy() for a in out.attentions])  # (L,H,S,S)
        self.L, self.H, self.S, _ = self.att.shape
        self._build_words(tok)

    def _build_words(self, tok):
        """Group wordpieces into words; tag each word + token with its turn index.
        Token 0 is [CLS]; the final token is [SEP]; " . " separators are their own
        tokens, skipped. Turn membership is assigned by walking each turn's own
        tokenization in order (robust to repeated words across turns)."""
        specials = set(tok.all_special_tokens)
        # per-turn wordpiece counts, to assign token->turn
        sub = [tok.convert_ids_to_tokens(tok(t, add_special_tokens=False)["input_ids"])
               for t in self.turns]
        tok_turn = [-1] * self.S
        pos = 1  # skip [CLS]
        for ti, s in enumerate(sub):
            for _ in s:
                if pos < self.S:
                    tok_turn[pos] = ti
                    pos += 1
            # skip separator tokens (".", punctuation) between turns
            while pos < self.S and self.toks[pos] in (".", ";", "[SEP]"):
                pos += 1
        self.tok_turn = tok_turn
        # group wordpieces -> words
        words = []          # list of dict(text, turn, tok_idx=[...])
        cur = None
        for k, t in enumerate(self.toks):
            if t in specials or t in (".", ";"):
                cur = None
                continue
            if t.startswith("##") and cur is not None:
                cur["text"] += t[2:]
                cur["tok_idx"].append(k)
            else:
                cur = {"text": t, "turn": tok_turn[k], "tok_idx": [k]}
                words.append(cur)
        self.words = words
        self.cur_turn = len(self.turns) - 1
        # current-turn content token indices (for span pooling)
        self.cur_tok_idx = [k for k in range(self.S)
                            if tok_turn[k] == self.cur_turn and self.toks[k] not in specials]

    # ---- attention signal selection ------------------------------------
    def attn_matrix(self, signal) -> np.ndarray:
        """Return one (S,S) attention matrix for a signal spec:
        ('lh', l, h) one head · ('layeravg', l) heads averaged in a layer ·
        ('allavg',) all layers+heads averaged · ('headmax', l) max over heads."""
        kind = signal[0]
        if kind == "lh":
            return self.att[signal[1], signal[2]]
        if kind == "layeravg":
            return self.att[signal[1]].mean(0)
        if kind == "allavg":
            return self.att.reshape(-1, self.S, self.S).mean(0)
        if kind == "headmax":
            return self.att[signal[1]].max(0)
        raise ValueError(signal)

    # ---- the two jobs ---------------------------------------------------
    def resolve_reference(self, signal):
        """Find the prior-turn WORD the current turn's pronoun binds to.
        Returns (referent_word, score, pronoun_word) or (None, 0.0, None)."""
        A = self.attn_matrix(signal)
        # the pronoun token(s) in the current turn
        pron_idx = [w["tok_idx"] for w in self.words
                    if w["turn"] == self.cur_turn and w["text"] in _PRONOUNS]
        if not pron_idx:
            # no explicit pronoun: use the whole current-turn span as the query
            # (handles "the big one" where "one" is a pronoun, but also elliptical
            # ops like "largest please" with no pronoun — attend from all cur toks)
            q = self.cur_tok_idx
        else:
            q = [k for grp in pron_idx for k in grp]
        if not q:
            return None, 0.0, None
        # aggregate attention from query tokens onto each PRIOR-turn word
        best = (None, -1.0)
        for w in self.words:
            if w["turn"] >= self.cur_turn or w["turn"] < 0:
                continue
            if w["text"] in _STOP:
                continue
            mass = float(A[np.ix_(q, w["tok_idx"])].sum()) / len(q)
            if mass > best[1]:
                best = (w["text"], mass)
        pron = next((w["text"] for w in self.words
                     if w["turn"] == self.cur_turn and w["text"] in _PRONOUNS), None)
        return best[0], best[1], pron

    def act_crosscheck(self):
        """Pool the CURRENT-TURN SPAN only (Finding-3 fix) and match intent
        descriptions. Returns (top_intent, top_cos, margin)."""
        if not self.cur_tok_idx:
            return None, 0.0, 0.0
        pooled = self.hidden[self.cur_tok_idx].mean(axis=0)
        n = np.linalg.norm(pooled)
        pooled = pooled / n if n else pooled
        ids, mat = _desc_index()
        sims = mat @ pooled
        order = np.argsort(-sims)
        top, top2 = int(order[0]), int(order[1])
        return ids[top], float(sims[top]), float(sims[top] - sims[top2])


# --------------------------------------------------------------------------
# Map a top intent -> a dialogue act / modifier (the resolver's recovery output)
# --------------------------------------------------------------------------
def intent_to_act(intent: str, frame_exists: bool) -> dict:
    """Translate the cross-check intent into a session act/modifier the rules
    pipeline would consume. Destructive stays flagged, never auto-emitted."""
    if intent in ("find_largest",):
        return {"act": "operate", "modifier": "max-by-size"}
    if intent in ("find_smallest",):
        return {"act": "operate", "modifier": "min-by-size"}
    if intent in ("count_files", "count_lines", "count_matches"):
        return {"act": "operate", "modifier": "count"}
    if intent in ("delete_file",):
        return {"act": "delete", "modifier": None, "destructive": True}
    if intent in ("find_by_time", "find_by_size", "find_by_type", "find_by_name",
                  "find_recent", "find_empty", "find_perms"):
        # narrowing intents -> a refine of the running query (the concrete slot
        # value stays the rules' job; attention only recovers act + reference).
        return {"act": "refine" if frame_exists else "new", "modifier": None}
    return {"act": "fallback", "modifier": None}


class Resolver:
    """Dev-time convenience wrapper. Holds the chosen attention signal."""

    def __init__(self, signal=("lh", 3, 1)):
        self.signal = signal

    def resolve(self, history: list[str], current: str, frame_exists: bool = True):
        enc = ChainEncoding(history + [current])
        referent, score, pron = enc.resolve_reference(self.signal)
        intent, cos, margin = enc.act_crosscheck()
        act = intent_to_act(intent, frame_exists)
        return {
            "resolved_reference": referent,       # e.g. "csv"
            "reference_score": round(score, 3),
            "pronoun": pron,                       # e.g. "those"
            "crosscheck_intent": intent,
            "suggested_act": act["act"],
            "suggested_modifier": act.get("modifier"),
            "destructive": act.get("destructive", False),
            "confidence": round(cos, 3),
            "margin": round(margin, 3),
            "_enc": enc,
        }


if __name__ == "__main__":  # tiny smoke test
    r = Resolver()
    out = r.resolve(["pull up the csv files", "only the ones over 2mb"],
                    "which of those is heaviest")
    for k, v in out.items():
        if k != "_enc":
            print(f"  {k:20} {v}")
