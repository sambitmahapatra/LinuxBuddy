"""Task 46 (B) — the continual-learning loop's discipline (no training here).

The expensive fine-tune is exercised by the demonstration; these assert the cheap,
safety-critical invariants: relabel against the frozen label space, NEVER train on a
frozen eval (leakage), and the ship gate REJECTS a regression (stability guarantee).
"""
import json

import pytest

from linuxbuddy.ml import retrain


def test_relabel_keeps_valid_drops_out_of_domain():
    misses = [
        {"text": "my latest edited files", "intent": "find_recent"},
        {"text": "fix this whole mess", "intent": None},          # genuine OOD → drop
        {"text": "clean up in here", "intent": "_ABSTAIN"},       # explicit abstain → drop
    ]
    out = retrain.relabel(misses)
    assert [r["text"] for r in out] == ["my latest edited files"]
    assert out[0]["intent"] == "find_recent" and out[0]["source"] == "feedback"


def test_relabel_rejects_label_outside_frozen_space():
    with pytest.raises(ValueError):
        retrain.relabel([{"text": "x", "intent": "not_a_real_intent_zzz"}])


def test_leakage_assertion_rejects_a_frozen_eval_utterance():
    # a miss that equals a FROZEN dogfood-eval request must be refused (never train
    # on the floor you measure against).
    leak = [{"text": "find all the python source files"}]        # verbatim dogfood eval
    with pytest.raises(AssertionError):
        retrain.assert_leakage_clean(leak)


def test_clean_misses_pass_leakage():
    retrain.assert_leakage_clean([{"text": "the newest things here"},
                                  {"text": "zero byte files"}])   # not in any eval


def test_fold_appends_and_checks_leakage(tmp_path):
    base = tmp_path / "train.jsonl"
    base.write_text(json.dumps({"text": "old row", "intent": "list_all"}) + "\n")
    out = tmp_path / "cand.jsonl"
    n = retrain.fold([{"text": "zero byte files", "intent": "find_empty", "source": "feedback"}],
                     base, out)
    assert n == 1
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(rows) == 2 and rows[-1]["text"] == "zero byte files"


def test_fold_balanced_upweights_protected_intents(tmp_path):
    # Task 47: the protected intents' rows are duplicated by their factor; others
    # appear once; the new misses are appended. Only the training MIX changes.
    base = tmp_path / "train.jsonl"
    base.write_text("\n".join(json.dumps(r) for r in [
        {"text": "a", "intent": "find_largest"},
        {"text": "b", "intent": "find_recent"},
        {"text": "c", "intent": "find_by_size"}]) + "\n")
    out = tmp_path / "cand.jsonl"
    n, extra = retrain.fold_balanced(
        [{"text": "newest files", "intent": "find_recent", "source": "feedback"}],
        base, out, {"find_largest": 3, "find_by_size": 2})
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    counts = {}
    for r in rows:
        counts[r["intent"]] = counts.get(r["intent"], 0) + 1
    assert counts["find_largest"] == 3            # upweighted ×3
    assert counts["find_by_size"] == 2            # upweighted ×2
    assert counts["find_recent"] == 2             # original + the new miss (unweighted)
    assert n == 1 and extra == {"find_largest": 2, "find_by_size": 1}


def test_fold_balanced_still_asserts_leakage(tmp_path):
    base = tmp_path / "train.jsonl"
    base.write_text(json.dumps({"text": "x", "intent": "list_all"}) + "\n")
    with pytest.raises(AssertionError):      # a frozen-eval utterance still refused
        retrain.fold_balanced([{"text": "find all the python source files"}],
                              base, tmp_path / "o.jsonl", {})


def _floors(fp=0.03, zero3=0.96, gap=0.93, val1=0.72, held=0.0):
    return {"nonsense_fp": fp, "zero_top3": zero3, "gap_recovery": gap,
            "val_top1": val1, "val_top3": 0.89, "zero_top1": 0.71,
            "heldout_recovery": held, "n_heldout": 12}


def test_ship_gate_adopts_when_every_floor_holds():
    before = _floors(held=0.0)
    after = _floors(held=0.33, gap=0.96)           # plasticity up, nothing regressed
    passed, lines = retrain.ship_gate(before, after)
    assert passed is True


def test_ship_gate_rejects_nonsense_fp_regression():
    before = _floors(fp=0.03)
    after = _floors(fp=0.20, held=0.5)             # learned a lot but abstain eroded
    passed, _ = retrain.ship_gate(before, after)
    assert passed is False


def test_ship_gate_rejects_catastrophic_forgetting():
    before = _floors(zero3=0.96)
    after = _floors(zero3=0.70, held=0.5)          # zero-data tail collapsed → forgetting
    passed, _ = retrain.ship_gate(before, after)
    assert passed is False


def _rt(correct=404, leak=0, novel=11, invocab=24):
    return {"dogfood_correct": correct, "gate_leak": leak,
            "mt_novel_n": novel, "mt_novel": f"{novel}/14",
            "mt_in_n": invocab, "mt_in_regress": f"{invocab}/24"}


def test_ship_gate_rejects_runtime_regression_proxies_pass():
    # the real Task-46 finding: encoder-level floors all hold, but the authoritative
    # 0-regression runtime floors drop (587 −1, novel −2) → the COMPLETE gate rejects.
    before, after = _floors(held=0.0), _floors(held=0.17)        # encoder proxies: fine
    rt_before, rt_after = _rt(404, 0, 11), _rt(403, 0, 9)        # runtime: regressed
    passed, lines = retrain.ship_gate(before, after, rt_before, rt_after)
    assert passed is False
    assert any("587" in l and "FAIL" in l for l in lines)
    assert any("novel" in l and "FAIL" in l for l in lines)


def test_ship_gate_adopts_when_runtime_floors_also_hold():
    before, after = _floors(held=0.0), _floors(held=0.17)
    rt_before, rt_after = _rt(404, 0, 11), _rt(405, 0, 12)       # runtime improved
    passed, _ = retrain.ship_gate(before, after, rt_before, rt_after)
    assert passed is True


def test_ship_gate_rejects_gate_leak():
    before, after = _floors(), _floors(held=0.5)
    rt_before, rt_after = _rt(404, 0, 11), _rt(404, 1, 11)       # containment breach
    passed, _ = retrain.ship_gate(before, after, rt_before, rt_after)
    assert passed is False
