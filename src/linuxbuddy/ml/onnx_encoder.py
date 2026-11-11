"""Task 40 — torch-free runtime encoder (onnxruntime + tokenizers + numpy ONLY).

This is the shipped abstain-path encoder. It loads the ONNX graph exported by
`onnx_export.py` and the MiniLM WordPiece tokenizer, and reproduces the
SentenceTransformer forward EXACTLY: tokenize → ONNX forward (token embeddings)
→ mean-pool over the attention mask → L2-normalize. No torch / transformers /
sentence-transformers are imported on this path (Part A: those imports were ~7s
of the ~10s cold cost; the model itself is trivial).

Degradation: if `onnxruntime`/`tokenizers` or the `.onnx` file are missing, the
loaders raise and `hybrid.classify_fallback` catches it → pure v1 (no crash).

Interface parity with ml.zeroshot.IntentIndex: `OnnxIntentIndex.rank(utterance)`
returns the same `[(intent_id, cosine), …]` list, so the hybrid seam is unchanged.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
ABSTAIN = "_ABSTAIN"
# MiniLM uses no query/doc prefix (see zeroshot._CONVENTIONS); keep it explicit so
# the ONNX path scores utterances identically to the torch path.
QUERY_PREFIX = ""


def _descriptions_fp(desc_path: Path) -> str:
    """Stdlib fingerprint of the descriptions FILE bytes (no PyYAML needed) — guards
    the cache against an edited intent_descriptions.yaml."""
    return hashlib.sha256(desc_path.read_bytes()).hexdigest()[:16]


class OnnxEncoder:
    """Tokenizer + ONNX session + mean-pool/normalize. onnxruntime & tokenizers are
    imported lazily in load() so merely importing this module stays light."""

    def __init__(self, session, tokenizer, input_names, max_len=128):
        self.session = session
        self.tokenizer = tokenizer
        self.input_names = input_names
        self.max_len = max_len

    @classmethod
    def load(cls, onnx_file: str, tokenizer_file: str, max_len: int = 128):
        import onnxruntime as ort           # lazy: abstain-path only
        from tokenizers import Tokenizer     # lazy: abstain-path only

        so = ort.SessionOptions()
        so.intra_op_num_threads = 1          # tiny model; avoid thread-pool spin-up
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess = ort.InferenceSession(onnx_file, sess_options=so,
                                    providers=["CPUExecutionProvider"])
        tok = Tokenizer.from_file(tokenizer_file)
        tok.enable_truncation(max_length=max_len)
        tok.enable_padding()
        names = {i.name for i in sess.get_inputs()}
        return cls(sess, tok, names, max_len)

    def encode(self, texts: list[str]) -> np.ndarray:
        encs = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        out = self.session.run(None, feeds)[0]          # (B, T, 384) token embeddings
        m = mask[..., None].astype(np.float32)
        summed = (out.astype(np.float32) * m).sum(axis=1)
        counts = np.clip(m.sum(axis=1), 1e-9, None)
        pooled = summed / counts                         # mean-pool over mask
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled / np.clip(norms, 1e-12, None)      # L2-normalize


@dataclass
class OnnxIntentIndex:
    intent_ids: list[str]
    matrix: np.ndarray            # (n_intents, 384) float32, L2-normalized
    encoder: OnnxEncoder
    query_prefix: str = QUERY_PREFIX

    @staticmethod
    def _paths(model_dir: Path):
        return (model_dir / "onnx" / "encoder.onnx",
                model_dir / "tokenizer.json",
                model_dir / "index_onnx.npz")

    @staticmethod
    def _max_len(model_dir: Path) -> int:
        meta = model_dir / "onnx" / "meta.json"
        if meta.exists():
            try:
                return int(json.loads(meta.read_text()).get("max_len", 128))
            except Exception:
                pass
        return 128

    @classmethod
    def build(cls, model_dir: Path) -> "OnnxIntentIndex":
        """Embed the 85 intent descriptions through the ONNX model. Used by the
        export (offline) and as a runtime rebuild if the cache is stale/missing.
        Reading descriptions needs PyYAML — only on this rebuild path, never the
        normal cached() path."""
        from .zeroshot import load_descriptions, anchor_texts
        onnx_file, tok_file, _ = cls._paths(model_dir)
        enc = OnnxEncoder.load(str(onnx_file), str(tok_file), cls._max_len(model_dir))
        texts_by_intent = anchor_texts(load_descriptions(), "desc")
        intent_ids = sorted(texts_by_intent)
        vecs = []
        for intent in intent_ids:
            emb = enc.encode(texts_by_intent[intent])    # desc mode → 1 text
            pooled = emb.mean(axis=0)
            n = np.linalg.norm(pooled)
            vecs.append(pooled / n if n else pooled)
        return cls(intent_ids=intent_ids,
                   matrix=np.vstack(vecs).astype("float32"), encoder=enc)

    def save(self, cache_path: Path) -> None:
        desc_fp = _descriptions_fp(REPO_ROOT / "kb" / "intent_descriptions.yaml")
        np.savez(cache_path, matrix=self.matrix,
                 intent_ids=np.array(self.intent_ids),
                 query_prefix=np.array(self.query_prefix),
                 desc_fp=np.array(desc_fp))

    @classmethod
    def cached(cls, model_dir: Path) -> "OnnxIntentIndex":
        """Normal runtime path: load the ONNX graph + the cached description matrix
        from disk. Rebuilds only if the cache is absent or stale (descriptions
        edited). Raises if the ONNX artifact/deps are missing → caller degrades."""
        onnx_file, tok_file, cache_path = cls._paths(model_dir)
        if not onnx_file.exists():
            raise FileNotFoundError(onnx_file)
        desc_path = REPO_ROOT / "kb" / "intent_descriptions.yaml"
        if cache_path.exists():
            try:
                data = np.load(cache_path, allow_pickle=False)
                if str(data["desc_fp"]) == _descriptions_fp(desc_path):
                    enc = OnnxEncoder.load(str(onnx_file), str(tok_file),
                                           cls._max_len(model_dir))
                    return cls(intent_ids=[str(x) for x in data["intent_ids"]],
                               matrix=data["matrix"].astype("float32"), encoder=enc,
                               query_prefix=str(data["query_prefix"]))
            except FileNotFoundError:
                raise
            except Exception:
                pass                         # corrupt/stale → rebuild
        idx = cls.build(model_dir)
        try:
            idx.save(cache_path)
        except Exception:
            pass
        return idx

    def rank(self, utterance: str) -> list[tuple[str, float]]:
        q = self.encoder.encode([self.query_prefix + utterance])[0]
        sims = self.matrix @ q.astype("float32")
        order = np.argsort(-sims)
        return [(self.intent_ids[i], float(sims[i])) for i in order]
