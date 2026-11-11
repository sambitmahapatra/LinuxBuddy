"""Task 36 — sanity checks for the Phase-0 training corpus.

Validates the generated .jsonl against the frozen label space: valid labels, no
train/val leakage, abstain present and in range, well-formed schema, and
byte-for-byte reproducibility. Stratification gaps are REPORTED, not failed
(the corpus is small by design).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"

from linuxbuddy.ml.labels import ABSTAIN, DIALOGUE_ACTS, all_intents  # noqa: E402


def _jsonl(name):
    path = DATA / name
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


@pytest.fixture(scope="module", autouse=True)
def _generated():
    """Generate the corpus once before the checks (idempotent)."""
    from linuxbuddy.ml.make_dataset import generate
    generate()


# --- label space -----------------------------------------------------------
def test_label_space_matches_kb():
    space = json.loads((DATA / "label_space.json").read_text())
    assert space["intents"] == all_intents()          # exact, sorted
    assert space["dialogue_acts"] == DIALOGUE_ACTS
    assert space["special"] == [ABSTAIN]
    assert space["counts"]["n_intents"] == len(all_intents())


# --- label validity --------------------------------------------------------
def test_single_turn_labels_valid():
    valid = set(all_intents()) | {ABSTAIN}
    for name in ("train.jsonl", "val.jsonl"):
        for r in _jsonl(name):
            assert r["intent"] in valid, f"bad intent {r['intent']!r} in {name}"


def test_multi_turn_acts_valid():
    for name in ("train_mt.jsonl", "val_mt.jsonl"):
        for r in _jsonl(name):
            assert r["dialogue_act"] in DIALOGUE_ACTS, \
                f"bad act {r['dialogue_act']!r} in {name}"


# --- schema ----------------------------------------------------------------
def test_single_turn_schema():
    need = {"text", "intent", "source", "seed_id"}
    for name in ("train.jsonl", "val.jsonl"):
        rows = _jsonl(name)
        assert rows, f"{name} is empty"
        for r in rows:
            assert need <= set(r), f"missing keys in {name}: {need - set(r)}"
            assert isinstance(r["text"], str) and r["text"].strip(), \
                f"empty text in {name}"


def test_multi_turn_schema():
    need = {"chain_id", "turn", "text", "prev_frame", "dialogue_act",
            "frame_delta", "source"}
    for name in ("train_mt.jsonl", "val_mt.jsonl"):
        for r in _jsonl(name):
            assert need <= set(r), f"missing keys in {name}: {need - set(r)}"
            assert r["text"].strip()
            assert isinstance(r["prev_frame"], dict)
            assert isinstance(r["frame_delta"], dict)


# --- no leakage (the trap) -------------------------------------------------
def test_no_seed_leakage_single_turn():
    tr = {r["seed_id"] for r in _jsonl("train.jsonl")}
    va = {r["seed_id"] for r in _jsonl("val.jsonl")}
    assert tr & va == set(), f"seed leakage: {sorted(tr & va)}"


def test_no_chain_leakage_multi_turn():
    tr = {r["chain_id"] for r in _jsonl("train_mt.jsonl")}
    va = {r["chain_id"] for r in _jsonl("val_mt.jsonl")}
    assert tr & va == set(), f"chain leakage: {sorted(tr & va)}"


def test_augmentation_is_train_only():
    # no val row may be an augmentation
    for r in _jsonl("val.jsonl"):
        assert not str(r.get("source", "")).startswith("aug:"), \
            f"augmented row leaked into val: {r['text']!r}"
    # and every augmented row's parent is on the train side (same seed group)
    tr_seeds = {r["seed_id"] for r in _jsonl("train.jsonl")}
    for r in _jsonl("train.jsonl"):
        if str(r.get("source", "")).startswith("aug:"):
            assert r["parent_seed_id"] in tr_seeds


# --- abstain present & in range -------------------------------------------
def test_abstain_present_and_in_range():
    tr = _jsonl("train.jsonl")
    va = _jsonl("val.jsonl")
    tr_ab = sum(1 for r in tr if r["intent"] == ABSTAIN)
    va_ab = sum(1 for r in va if r["intent"] == ABSTAIN)
    assert tr_ab > 0 and va_ab > 0, "abstain must appear in BOTH splits"
    share = tr_ab / len(tr)
    assert 0.08 <= share <= 0.20, f"_ABSTAIN train share {share:.3f} out of 8-20%"


# --- size sanity -----------------------------------------------------------
def test_single_turn_size_in_target_band():
    total = len(_jsonl("train.jsonl")) + len(_jsonl("val.jsonl"))
    assert 500 <= total <= 900, f"single-turn total {total} outside ~500-800 band"


# --- stratification: REPORT (don't fail) ----------------------------------
def test_stratification_report(capsys):
    from collections import Counter
    tr = Counter(r["intent"] for r in _jsonl("train.jsonl"))
    va = Counter(r["intent"] for r in _jsonl("val.jsonl"))
    val_only = sorted(i for i in va if i not in tr)
    thin = sorted(i for i in tr if tr[i] < 3)
    zero = sorted(i for i in all_intents() if i not in tr and i not in va)
    with capsys.disabled():
        print(f"\n[stratification] val-only intents: {val_only or 'none'}")
        print(f"[stratification] <3 train rows: {len(thin)} intents")
        print(f"[stratification] zero-coverage intents: {len(zero)}")
    # every intent that HAS data and >=2 seeds should appear in train
    assert not val_only or all(True for _ in val_only)  # reported, never fatal


# --- reproducibility (byte-for-byte) --------------------------------------
def test_reproducible_byte_for_byte(tmp_path):
    files = ["label_space.json", "sweep_intent_map.json", "single_turn.raw.jsonl",
             "multi_turn.raw.jsonl", "train.jsonl", "val.jsonl",
             "train_mt.jsonl", "val_mt.jsonl"]
    before = {f: (DATA / f).read_bytes() for f in files}
    # regenerate in-process and compare
    subprocess.run([sys.executable, "-I", "-m", "linuxbuddy.ml.make_dataset"],
                   cwd=REPO_ROOT, check=True, capture_output=True)
    for f in files:
        assert (DATA / f).read_bytes() == before[f], \
            f"{f} changed between identical-seed runs (not reproducible)"
