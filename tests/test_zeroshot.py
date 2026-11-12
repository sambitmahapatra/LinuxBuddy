"""Task 37 — tests for the zero-shot bi-encoder spike.

The coverage test needs no ML libraries (it runs in the main venv and keeps the
existing suite honest). The matcher tests require sentence-transformers and so are
skipped where it is not installed (the main Python-3.14 venv) and run in the
isolated .venv-ml. This task adds only; it changes nothing in the rules/router.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"

from linuxbuddy.ml.zeroshot import ABSTAIN, top_level_keys  # noqa: E402 (no ML deps)


# --- always-on: descriptions cover the label space exactly ------------------
def test_descriptions_cover_label_space():
    label_space = set(json.loads((DATA / "label_space.json").read_text())["intents"])
    described = set(top_level_keys())
    missing = label_space - described
    extra = described - label_space
    assert not missing, f"intents missing a description: {sorted(missing)}"
    assert not extra, f"descriptions for unknown intents: {sorted(extra)}"


# --- matcher tests (need the model) ----------------------------------------
# NOTE: the skip must be per-test (via the fixture), NOT a module-level
# importorskip — a module-level skip would also skip the coverage test above,
# which needs no ML libraries and must always run in the main venv.
@pytest.fixture(scope="module")
def index():
    pytest.importorskip("sentence_transformers",
                        reason="ML env only (.venv-ml); skipped in the main venv")
    from linuxbuddy.ml.zeroshot import IntentIndex
    return IntentIndex.build(mode="desc")


def test_prediction_is_in_vocabulary(index):
    valid = set(index.intent_ids) | {ABSTAIN}
    for text in ["find all the python files", "delete old.log",
                 "banana telephone sunshine", "what's using port 8080"]:
        pred, *_ = index.classify(text, T=0.35)
        assert pred in valid


def test_ranking_is_deterministic(index):
    a = index.rank("erase scratch.tmp")
    b = index.rank("erase scratch.tmp")
    assert a == b


def test_golden_delete_synonym_recovers(index):
    # "erase" is a delete synonym the rules miss; it must rank delete_file high.
    ranked = index.rank("erase scratch.tmp")
    top3 = [i for i, _ in ranked[:3]]
    assert "delete_file" in top3, f"delete_file not in top-3: {top3}"


def test_golden_nonsense_scores_low(index):
    # pure nonsense should not confidently match any intent
    _, top1, _, _ = index.classify("banana telephone sunshine", T=0.35)
    assert top1 < 0.5, f"nonsense scored unexpectedly high: {top1}"
