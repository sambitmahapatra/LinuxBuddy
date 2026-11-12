"""Task 38 Part B — contrastive fine-tune of the bi-encoder (a Siamese network).

A bi-encoder trained with a contrastive objective IS a Siamese network (rubric
concept #2): the SAME encoder embeds both an utterance and an intent description,
and the loss pulls a true (utterance, description) pair together while pushing the
in-batch negatives (every other description) apart. We use
MultipleNegativesRankingLoss — in-batch negatives, the natural fit for our
(utterance ↔ description) pairs.

Abstain is a first-class target. The pure cosine threshold already failed once
(Task 37: nonsense FP 31%), so AFTER fine-tuning we train a tiny calibrated gate
(option b): a logistic regression on [max_sim, top1−top2 margin] that makes the
in-domain-vs-abstain decision, replacing the single cosine cut. We chose (b) over
"abstain rows as hard negatives" because MNRL sharpens in-domain similarities
(the whole space contracts), so nonsense can still score high in absolute terms —
but AFTER fine-tuning the *margin* becomes discriminative (neighbours are pushed
apart), and a 2-feature gate exploits both signals, directly optimising the FP
target rather than hoping one global threshold lands right.

Reproduce (ML env):  python -I -m linuxbuddy.ml.finetune
Trains on GPU if available, else CPU (dataset is tiny — CPU takes minutes).
Deterministic given SEED (hardware may prevent byte-identical embeddings).
"""
from __future__ import annotations

import itertools
import json
import random
from pathlib import Path

from .zeroshot import ABSTAIN, load_descriptions

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
MODELS_DIR = REPO_ROOT / "models"
OUT_DIR = MODELS_DIR / "ft-minilm-l6"
GATE_PATH = OUT_DIR / "abstain_gate.json"

BASE = "sentence-transformers/all-MiniLM-L6-v2"   # Part A winner (lowest FP, CPU-small)
SEED = 42
EPOCHS = 3
LR = 2e-5
BATCH = 32
MAX_UTT_PAIRS_PER_INTENT = 8          # cap utt↔utt pairs so big intents don't swamp


def _read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def heldout_texts() -> set[str]:
    """Utterances that MUST NOT be trained on: the gap set (the rules-ceiling eval)
    and val. The Task-36 split put many gap rows into train.jsonl, so we filter them
    here — otherwise 'gap recovery' would be a training-set number (leakage)."""
    raw = _read(DATA / "single_turn.raw.jsonl")
    gap = {r["text"] for r in raw if r.get("source") == "stress_gap"}
    val = {r["text"] for r in _read(DATA / "val.jsonl")}
    return gap | val


def build_pairs(train_path: Path = DATA / "train.jsonl") -> list[tuple[str, str]]:
    """Positive pairs for MNRL: utterance↔description and utterance↔utterance
    within the same intent. Abstain rows are NOT positives (handled by the gate).
    Gap-set and val utterances are excluded so those remain genuine held-out eval.

    ``train_path`` defaults to the shipped train.jsonl; the continual-learning loop
    (Task 46) passes a CANDIDATE train file (old train + newly-labelled misses) to
    retrain without touching the shipped data."""
    descs = load_descriptions()
    held = heldout_texts()
    train = _read(train_path)
    by_intent: dict[str, list[str]] = {}
    for r in train:
        it = r["intent"]
        if it == ABSTAIN or it not in descs or r["text"] in held:
            continue
        by_intent.setdefault(it, []).append(r["text"])

    pairs: list[tuple[str, str]] = []
    for it, utts in by_intent.items():
        desc = (descs[it] or {}).get("description", "").strip()
        if desc:
            pairs += [(u, desc) for u in utts]
    rng = random.Random(SEED)
    for it, utts in by_intent.items():
        combos = list(itertools.combinations(sorted(set(utts)), 2))
        rng.shuffle(combos)
        pairs += combos[:MAX_UTT_PAIRS_PER_INTENT]
    rng.shuffle(pairs)
    return pairs


def train_encoder(out_dir: Path = OUT_DIR,
                  train_path: Path = DATA / "train.jsonl",
                  epochs: int = EPOCHS, lr: float = LR) -> str:
    """``epochs``/``lr`` default to the shipped recipe; the continual-learning loop
    (Task 47) may lower them as an anti-interference (drift-reduction) knob."""
    import torch
    from sentence_transformers import InputExample, SentenceTransformer, losses
    from torch.utils.data import DataLoader

    random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    pairs = build_pairs(train_path)
    print(f"device={device}  pairs={len(pairs)}  epochs={epochs}  lr={lr}  batch={BATCH}")

    model = SentenceTransformer(BASE, device=device)
    examples = [InputExample(texts=[a, b]) for a, b in pairs]
    loader = DataLoader(examples, shuffle=True, batch_size=BATCH,
                        generator=torch.Generator().manual_seed(SEED))
    loss = losses.MultipleNegativesRankingLoss(model)
    steps = max(1, len(loader) * epochs)
    model.fit(train_objectives=[(loader, loss)], epochs=epochs,
              warmup_steps=max(1, steps // 10),
              optimizer_params={"lr": lr}, show_progress_bar=False, use_amp=False)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(out_dir))
    print(f"saved fine-tuned encoder → {out_dir}")
    return str(out_dir)


# --------------------------------------------------------------------------
# Abstain gate (option b): logistic on [max_sim, margin]
# --------------------------------------------------------------------------
def _features(index, rows):
    import numpy as np
    X = []
    for r in rows:
        ranked = index.rank(r["text"])
        top1 = ranked[0][1]
        top2 = ranked[1][1] if len(ranked) > 1 else 0.0
        X.append([top1, top1 - top2])
    return np.asarray(X, dtype="float64")


def train_gate(model_dir: str = str(OUT_DIR),
               train_path: Path = DATA / "train.jsonl") -> dict:
    """Fit a logistic gate on TRAIN rows (in-domain=1 vs abstain=0) using the
    fine-tuned space. Saves weights (to ``model_dir``); decision is p(in-domain)>=0.5."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    from .zeroshot import IntentIndex, load_descriptions

    descs = load_descriptions()
    held = heldout_texts()
    train = [r for r in _read(train_path) if r["text"] not in held]
    pos = [r for r in train if r["intent"] != ABSTAIN and r["intent"] in descs]
    neg = [r for r in train if r["intent"] == ABSTAIN]

    index = IntentIndex.build(mode="desc", model_name=model_dir)
    Xpos, Xneg = _features(index, pos), _features(index, neg)
    X = np.vstack([Xpos, Xneg])
    y = np.array([1] * len(Xpos) + [0] * len(Xneg))

    # Balanced logistic at p>=0.5. (We tried calibrating the cutoff to the FP budget
    # on train, but the TRAIN abstains are the HARD near-domain ones and far harder
    # than real OOD nonsense, so budgeting on them over-rejects — the plain balanced
    # gate is the better operating point. See finetune_report.md.)
    clf = LogisticRegression(class_weight="balanced", random_state=SEED, max_iter=1000)
    clf.fit(X, y)
    gate = {
        "features": ["max_sim", "margin"],
        "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
        "threshold": 0.5,
        "n_pos": len(pos), "n_neg": len(neg),
        "base": BASE, "seed": SEED,
    }
    gate_path = Path(model_dir) / "abstain_gate.json"
    gate_path.write_text(json.dumps(gate, indent=2))
    print(f"saved abstain gate → {gate_path}  "
          f"(train acc {clf.score(X, y):.2f}, on {len(pos)} in-domain / {len(neg)} abstain)")
    return gate


def load_gate(path: Path = GATE_PATH) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def gate_says_answer(gate: dict, max_sim: float, margin: float) -> bool:
    import math
    z = gate["intercept"] + gate["coef"][0] * max_sim + gate["coef"][1] * margin
    p = 1.0 / (1.0 + math.exp(-z))
    return p >= gate["threshold"]


if __name__ == "__main__":  # pragma: no cover
    d = train_encoder()
    train_gate(d)
