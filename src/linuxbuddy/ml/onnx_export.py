"""Task 40 — one-time, OFFLINE export of the fine-tuned encoder to ONNX (int8).

Runs in `.venv-ml` (needs torch + sentence-transformers + optimum). Produces a
torch-free runtime artifact so `lb`'s abstain path imports only onnxruntime +
tokenizers (Part A showed the torch/transformers/ST imports are ~7s of the ~10s
cold cost — the model itself is trivial).

Pipeline parity: the ONNX graph outputs token embeddings (last_hidden_state); the
runtime wrapper (onnx_encoder.OnnxEncoder) reimplements mean-pool-over-mask then
L2-normalize to match the SentenceTransformer exactly. This script VERIFIES that
parity (per-pair cosine vs the torch reference) and ships int8 only if cosine
>= 0.999, else falls back to fp32 ONNX (still torch-free at runtime).

Regenerate:  .venv-ml/bin/python -I -m linuxbuddy.ml.onnx_export

Outputs (all under models/ft-minilm-l6/, which is gitignored):
  onnx/encoder.onnx     the shipped graph (int8 or fp32)
  onnx/meta.json        {"precision","cosine_min","cosine_mean"}
  index_onnx.npz        85 description embeddings via the SHIPPED onnx model
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO_ROOT / "models" / "ft-minilm-l6"
ONNX_DIR = MODEL_DIR / "onnx"
MAX_LEN = 128

# A fidelity sample: real utterances + a few descriptions (short + long text).
SAMPLE = [
    "what processes are running", "where are the spreadsheets",
    "delete the file scratch.tmp", "what changed in the last day",
    "list everything here", "how big is this directory",
    "show me the largest files", "count the python files",
    "move report.csv into archive", "make a new folder called out",
    "kill whatever is on port 8080", "extract the tarball",
    "find files bigger than 100mb", "what's my disk usage",
    "the quick brown fox jumps over the lazy dog",
]


def _ref_embeddings(texts):
    """Torch SentenceTransformer reference (the model we must match)."""
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(str(MODEL_DIR))
    return np.asarray(m.encode(texts, normalize_embeddings=True,
                               show_progress_bar=False), dtype="float32")


def _export_and_quantize():
    # optimum's ONNX exporter is incompatible with torch 2.15 (it imports a symbolic
    # that torch removed), so export with torch.onnx directly and quantize with
    # onnxruntime.quantization — no optimum on this path.
    import torch
    from transformers import AutoModel
    from tokenizers import Tokenizer

    ONNX_DIR.mkdir(parents=True, exist_ok=True)
    model = AutoModel.from_pretrained(str(MODEL_DIR))
    model.eval()

    class Wrap(torch.nn.Module):
        """Expose ONLY last_hidden_state (token embeddings) — we pool/normalize in
        numpy at runtime, matching the SentenceTransformer pipeline."""
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask, token_type_ids):
            return self.m(input_ids=input_ids, attention_mask=attention_mask,
                          token_type_ids=token_type_ids).last_hidden_state

    tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
    e = tok.encode("export calibration sentence")
    ids = torch.tensor([e.ids], dtype=torch.long)
    mask = torch.tensor([e.attention_mask], dtype=torch.long)
    tt = torch.zeros_like(ids)

    fp32 = ONNX_DIR / "model.onnx"
    dyn = {0: "batch", 1: "seq"}
    with torch.no_grad():
        torch.onnx.export(
            Wrap(model), (ids, mask, tt), str(fp32),
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["last_hidden_state"],
            dynamic_axes={"input_ids": dyn, "attention_mask": dyn,
                          "token_type_ids": dyn, "last_hidden_state": dyn},
            opset_version=17, do_constant_folding=True)

    from onnxruntime.quantization import quantize_dynamic, QuantType
    int8 = ONNX_DIR / "model_quantized.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    return fp32, int8


def _onnx_cosine(onnx_file, ref):
    """Per-pair cosine of ONNX-vs-torch embeddings on the SAMPLE."""
    from .onnx_encoder import OnnxEncoder
    enc = OnnxEncoder.load(str(onnx_file), str(MODEL_DIR / "tokenizer.json"), MAX_LEN)
    got = enc.encode(SAMPLE)
    cos = (got * ref).sum(axis=1)           # both L2-normalized
    return float(cos.min()), float(cos.mean())


def run():
    print("[export] exporting the fine-tuned encoder to ONNX (fp32 + int8)…")
    fp32, int8 = _export_and_quantize()
    ref = _ref_embeddings(SAMPLE)

    i_min, i_mean = _onnx_cosine(int8, ref)
    f_min, f_mean = _onnx_cosine(fp32, ref)
    print(f"[fidelity] int8  cosine min={i_min:.5f} mean={i_mean:.5f}")
    print(f"[fidelity] fp32  cosine min={f_min:.5f} mean={f_mean:.5f}")

    if i_min >= 0.999:
        precision, src, cmin, cmean = "int8", int8, i_min, i_mean
    elif f_min >= 0.999:
        precision, src, cmin, cmean = "fp32", fp32, f_min, f_mean
        print("[fidelity] int8 below 0.999 → shipping fp32 (still torch-free).")
    else:
        raise SystemExit(f"[FAIL] neither precision reaches cosine 0.999 "
                         f"(int8 {i_min:.5f}, fp32 {f_min:.5f}) — check pooling.")

    shipped = ONNX_DIR / "encoder.onnx"
    shutil.copyfile(src, shipped)
    (ONNX_DIR / "meta.json").write_text(json.dumps(
        {"precision": precision, "cosine_min": round(cmin, 5),
         "cosine_mean": round(cmean, 5), "max_len": MAX_LEN}, indent=2))
    print(f"[ship] {precision} → {shipped.relative_to(REPO_ROOT)} "
          f"(cosine min {cmin:.5f})")

    # Build the description cache through the SHIPPED onnx model (the matrix MUST
    # come from the same model that scores utterances).
    from .onnx_encoder import OnnxIntentIndex
    idx = OnnxIntentIndex.build(MODEL_DIR)
    idx.save(MODEL_DIR / "index_onnx.npz")
    print(f"[cache] {len(idx.intent_ids)} description embeddings → index_onnx.npz")


if __name__ == "__main__":  # pragma: no cover
    run()
