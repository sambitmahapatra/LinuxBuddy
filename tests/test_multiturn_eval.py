"""Guard the Task-44 frozen multi-turn eval (data/eval/multiturn_eval.jsonl).

Pure stdlib — NO torch/ML deps — so it runs in the main venv suite and keeps the
eval honest: leakage-clean vs the 49 training turns, well-formed schema, and a
real in-vocab/novel split. This is the multi-turn analogue of the dogfood eval's
leakage assertion; it does NOT exercise the resolver (that is dev-time, in
.venv-ml, under experiments/task44_spike/).
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVAL = REPO / "data" / "eval" / "multiturn_eval.jsonl"
TRAIN = REPO / "data" / "multi_turn.raw.jsonl"

ACTS = {"new", "refine", "operate", "reset", "delete"}
VOCAB = {"seed", "in", "novel"}
RISK = {"read", "destructive"}


def _rows():
    out = []
    for line in EVAL.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('{"_comment'):
            continue
        out.append(json.loads(line))
    return out


def test_eval_exists_and_nonempty():
    assert EVAL.exists(), "frozen multi-turn eval missing"
    assert len(_rows()) >= 60, "expected a substantial eval (>=60 turn-rows)"


def test_no_training_leakage():
    train = {json.loads(l)["text"].lower().strip()
             for l in TRAIN.read_text().splitlines() if l.strip()}
    dups = sorted({r["text"] for r in _rows() if r["text"].lower().strip() in train})
    assert dups == [], f"eval turns leaked from training data: {dups}"


def test_schema_well_formed():
    for r in _rows():
        for k in ("chain_id", "domain", "turn", "text", "act", "vocab", "risk",
                  "coref", "binds", "delta", "expected_frame"):
            assert k in r, f"{r.get('chain_id')} missing key {k}"
        assert r["act"] in ACTS, f"bad act {r['act']!r}"
        assert r["vocab"] in VOCAB, f"bad vocab {r['vocab']!r}"
        assert r["risk"] in RISK, f"bad risk {r['risk']!r}"
        # a destructive / reset turn has no emittable read frame
        if r["risk"] == "destructive" or r["act"] == "reset":
            assert r["expected_frame"] is None
        else:
            ef = r["expected_frame"]
            assert ef and ef["intent"] in (
                "session_find", "session_find_biggest", "session_count")


def test_in_novel_split_present():
    rows = _rows()
    n_in = sum(r["vocab"] == "in" for r in rows)
    n_novel = sum(r["vocab"] == "novel" for r in rows)
    assert n_in >= 10 and n_novel >= 10, (n_in, n_novel)


def test_coreference_turns_labelled():
    # the whole experiment needs coref turns with their resolved target words
    coref = [r for r in _rows() if r["coref"]]
    assert len(coref) >= 20
    for r in coref:
        assert r["binds"], f"{r['chain_id']} t{r['turn']} coref without binds"
