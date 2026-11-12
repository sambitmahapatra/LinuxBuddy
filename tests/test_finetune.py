"""Task 38 — tests for the fine-tune + abstain gate.

Data-leakage tests are always-on (no ML libs): they keep the fine-tune and its
probes honest in the main venv. The model tests require sentence-transformers AND
a built checkpoint, so they skip in the main venv and when no checkpoint is present
(a fresh clone before `python -m linuxbuddy.ml.finetune`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
CKPT = REPO_ROOT / "models" / "ft-minilm-l6"


def _texts(path, pred=lambda r: True):
    return {r["text"] for r in (json.loads(l) for l in
            path.read_text().splitlines() if l.strip()) if pred(r)}


# --- always-on leakage guards ----------------------------------------------
def test_train_pairs_no_leakage():
    """The ACTUAL fine-tune pairs (not raw train.jsonl, which the Task-36 split
    salted with gap/val rows) must contain no utterance equal to a gap or val
    utterance — otherwise gap recovery / val are training-set numbers. build_pairs
    and the gate both filter via heldout_texts(); this verifies it holds."""
    pytest.importorskip("yaml", reason="build_pairs needs PyYAML (ML env)")
    from linuxbuddy.ml.finetune import build_pairs, heldout_texts
    held = heldout_texts()
    pair_utts = {a for a, _ in build_pairs()} | {b for _, b in build_pairs()}
    leak = pair_utts & held
    # descriptions (the right side of utt↔desc pairs) are prose, never equal to a
    # short test utterance; the left side is train utterances minus held-out.
    assert not leak, f"fine-tune pairs leak held-out utterances: {sorted(leak)}"


def test_probes_no_leakage():
    """The fresh nonsense probe and the zero-data probe must be held out of
    train and val, or their numbers are meaningless."""
    train = _texts(DATA / "train.jsonl")
    val = _texts(DATA / "val.jsonl")
    for name in ("nonsense_probe.jsonl", "zero_data_probe.jsonl"):
        probe = _texts(DATA / name)
        bad = (probe & train) | (probe & val)
        assert not bad, f"{name} leaks into train/val: {sorted(bad)}"


# --- model tests (need ML + a checkpoint) ----------------------------------
@pytest.fixture(scope="module")
def ft_index():
    pytest.importorskip("sentence_transformers",
                        reason="ML env only (.venv-ml)")
    if not (CKPT / "config.json").exists():
        pytest.skip("no fine-tuned checkpoint; run linuxbuddy.ml.finetune first")
    from linuxbuddy.ml.zeroshot import IntentIndex
    return IntentIndex.build(mode="desc", model_name=str(CKPT))


def test_example_anchors_no_test_leakage():
    """Task-37 guard, kept: no example anchor may equal a gap/val test utterance."""
    pytest.importorskip("yaml", reason="needs PyYAML (ML env)")
    from linuxbuddy.ml.zeroshot import load_descriptions
    descs = load_descriptions()
    val = _texts(DATA / "val.jsonl")
    gap = _texts(DATA / "single_turn.raw.jsonl", lambda r: r.get("source") == "stress_gap")
    test = val | gap
    leaks = [(i, ex) for i, sp in descs.items()
             for ex in (sp or {}).get("examples", []) or [] if ex in test]
    assert not leaks, f"example anchors equal to test utterances: {leaks}"


def test_finetuned_ranking_is_deterministic(ft_index):
    assert ft_index.rank("erase scratch.tmp") == ft_index.rank("erase scratch.tmp")


def test_gate_accepts_in_domain_rejects_nonsense(ft_index):
    """The learned abstain gate must answer a clear in-domain request and reject
    clear nonsense — the whole point of option (b)."""
    from linuxbuddy.ml.finetune import gate_says_answer, load_gate
    gate = load_gate(CKPT / "abstain_gate.json")
    assert gate, "gate file missing next to the checkpoint"

    def decide(text):
        ranked = ft_index.rank(text)
        top1, top2 = ranked[0][1], (ranked[1][1] if len(ranked) > 1 else 0.0)
        return gate_says_answer(gate, top1, top1 - top2)

    assert decide("delete old.log"), "gate wrongly abstained on a clear command"
    assert not decide("velvet thunder biscuit parade"), "gate answered on nonsense"
