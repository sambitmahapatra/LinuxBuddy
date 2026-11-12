"""Task 46 (B) — the continual-learning loop: grow-from-real-use, human-gated.

Rehearsal-based continual learning. The model learns from a STREAM of real logged
misses (plasticity) while the frozen floors + the zero-data guardrail prove it does
NOT forget old capability (stability). The shipped ``data/train.jsonl`` is the
**rehearsal buffer**: every retrain trains on old-train + the new misses, so prior
intents are rehearsed, not overwritten.

The cycle (all human-gated, offline, seed-pinned, reproducible):
  1. relabel   — assign each logged miss an intent from the FROZEN label space;
                 drop genuine out-of-domain (those SHOULD abstain).
  2. fold      — append labelled misses to a CANDIDATE train file; assert
                 leakage-clean against BOTH frozen evals (never train on the floor).
  3. retrain   — re-run the Task-38 contrastive fine-tune on old-train (rehearsal)
                 + new misses, seed-pinned, into a candidate checkpoint.
  4. evaluate  — measure EVERY frozen floor (stability) + held-out miss recovery
                 (plasticity) on the candidate.
  5. ship gate — adopt ONLY if every floor holds; else reject and keep the old
                 checkpoint. No auto-adopt, no network.

Nothing here runs at `lb` time; it is an offline, author-run tool. Reuses
ml.finetune (the Task-38 fine-tune) and the frozen floors.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
MODELS = REPO_ROOT / "models"
SHIPPED = MODELS / "ft-minilm-l6"
LABEL_SPACE = DATA / "label_space.json"
DOGFOOD_EVAL = DATA / "eval" / "dogfood_eval.jsonl"
MULTITURN_EVAL = DATA / "eval" / "multiturn_eval.jsonl"


def _read(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith('{"_comment')]


# --------------------------------------------------------------------------
# 1. relabel — against the FROZEN label space
# --------------------------------------------------------------------------
def valid_intents() -> set[str]:
    spec = json.loads(LABEL_SPACE.read_text())
    intents = spec.get("intents")
    if isinstance(intents, dict):
        return set(intents)
    return set(intents or [])


def relabel(misses: list[dict]) -> list[dict]:
    """Each miss is {text, intent}. Keep only intents in the frozen label space;
    drop genuine out-of-domain (intent None / '_ABSTAIN' → those SHOULD abstain)."""
    ok = valid_intents()
    out = []
    for m in misses:
        it = m.get("intent")
        if not it or it in ("_ABSTAIN", "abstain"):
            continue
        if it not in ok:
            raise ValueError(f"label {it!r} not in the frozen label space")
        out.append({"text": m["text"], "intent": it, "source": "feedback"})
    return out


# --------------------------------------------------------------------------
# 2. fold — never into the frozen evals
# --------------------------------------------------------------------------
def _eval_texts() -> set[str]:
    texts = set()
    for p in (DOGFOOD_EVAL, MULTITURN_EVAL):
        for r in _read(p):
            t = r.get("request") or r.get("text")
            if t:
                texts.add(t.strip().lower())
    return texts


def assert_leakage_clean(rows: list[dict]) -> None:
    """No labelled miss may equal a FROZEN-eval utterance (single-turn or chain)."""
    evalt = _eval_texts()
    leaked = sorted({r["text"] for r in rows if r["text"].strip().lower() in evalt})
    assert not leaked, f"miss(es) leak into a frozen eval: {leaked}"


def fold(labelled: list[dict], base_train: Path, out_train: Path) -> int:
    """Write out_train = base_train rows + labelled misses (the rehearsal buffer +
    the new stream). Asserts leakage-clean first. Returns rows added."""
    assert_leakage_clean(labelled)
    base = _read(base_train)
    out_train.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in (base + labelled)) + "\n")
    return len(labelled)


def fold_balanced(labelled: list[dict], base_train: Path, out_train: Path,
                  upweight: dict[str, int]) -> tuple[int, dict]:
    """Balanced / targeted rehearsal (Task 47): fold the new misses AND upweight the
    rehearsal buffer for the intents the naive cycle *interfered with* — their rows
    are duplicated ``upweight[intent]`` times, so the contrastive fine-tune keeps
    pinning that region instead of letting the new phenomenon drift into it. The
    frozen evals/split/gate are untouched; this only changes the TRAINING MIX.
    Returns (misses_added, {intent: extra_rows_added})."""
    assert_leakage_clean(labelled)
    base = _read(base_train)
    out_rows: list[dict] = []
    extra: dict[str, int] = {}
    for r in base:
        out_rows.append(r)
        factor = upweight.get(r.get("intent"), 1)
        for _ in range(factor - 1):
            out_rows.append(r)
            extra[r["intent"]] = extra.get(r["intent"], 0) + 1
    out_rows += labelled
    out_train.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n")
    return len(labelled), extra


# --------------------------------------------------------------------------
# 3. retrain — reuse the Task-38 fine-tune, seed-pinned, into a candidate dir
# --------------------------------------------------------------------------
def retrain(train_path: Path, out_dir: Path, epochs: int | None = None,
            lr: float | None = None) -> Path:
    from . import finetune
    kw = {}
    if epochs is not None:
        kw["epochs"] = epochs
    if lr is not None:
        kw["lr"] = lr
    finetune.train_encoder(out_dir=out_dir, train_path=train_path, **kw)
    finetune.train_gate(model_dir=str(out_dir), train_path=train_path)
    return out_dir


# --------------------------------------------------------------------------
# 4. evaluate — EVERY frozen floor (stability) + held-out recovery (plasticity)
# --------------------------------------------------------------------------
def _floor_data():
    from .zeroshot import ABSTAIN
    raw = _read(DATA / "single_turn.raw.jsonl")
    gap = [r for r in raw if r.get("source") == "stress_gap"]
    val = _read(DATA / "val.jsonl")
    train_texts = {r["text"] for r in _read(DATA / "train.jsonl")}
    val_cov = [r for r in val if r["intent"] != ABSTAIN and r["text"] not in train_texts]
    fresh = _read(DATA / "nonsense_probe.jsonl")
    nonsense = fresh + [r for r in val if r["intent"] == ABSTAIN]
    zprobe = _read(DATA / "zero_data_probe.jsonl")
    return gap, val_cov, nonsense, zprobe


def _t_read() -> float:
    """The shipped runtime's read abstain threshold (ml_config t_read), so the
    floors are measured with the SAME decision rule the user experiences."""
    from ..hybrid import _load_config
    return float(_load_config().get("t_read", 0.55))


def evaluate_floors(model_dir: str | Path, heldout_misses: list[dict],
                    T: float | None = None) -> dict:
    """Encoder-level floors on a checkpoint, measured with the RUNTIME decision rule
    (cosine top-1 ≥ t_read → answer; else abstain — exactly what `lb`/hybrid does):
    gap recovery, nonsense FP, val top-1/3, the zero-data-tail ceiling
    (anti-forgetting), and held-out miss recovery (plasticity)."""
    from .zeroshot import IntentIndex
    from .eval_zeroshot import _ceiling, _rank_all

    model_dir = str(model_dir)
    T = _t_read() if T is None else T
    index = IntentIndex.build(mode="desc", model_name=model_dir)
    gap, val_cov, nonsense, zprobe = _floor_data()

    def recovered(rows):                       # runtime would emit AND intent correct
        n = 0
        for r in rows:
            i1, s1 = index.rank(r["text"])[0]
            if s1 >= T and i1 == r["intent"]:
                n += 1
        return n

    def answered(rows):                        # runtime would emit at all → FP
        return sum(1 for r in rows if index.rank(r["text"])[0][1] >= T)

    def gold_top3(rows):                        # gold intent within top-3 (softer)
        n = 0
        for r in rows:
            top3 = {i for i, _ in index.rank(r["text"])[:3]}
            if r["intent"] in top3:
                n += 1
        return n

    def gold_sim(rows):                         # mean cosine of the GOLD intent
        if not rows:
            return 0.0
        tot = 0.0
        for r in rows:
            s = next((sc for i, sc in index.rank(r["text"]) if i == r["intent"]), 0.0)
            tot += s
        return tot / len(rows)

    zc = _rank_all(index, zprobe)
    nh = max(1, len(heldout_misses))
    return {
        "gap_recovery": recovered(gap) / max(1, len(gap)),
        "nonsense_fp": answered(nonsense) / max(1, len(nonsense)),
        "val_top1": recovered(val_cov) / max(1, len(val_cov)),
        "val_top3": _ceiling(_rank_all(index, val_cov), 3),
        "zero_top1": _ceiling(zc, 1),
        "zero_top3": _ceiling(zc, 3),
        "heldout_recovery": recovered(heldout_misses) / nh,   # top-1 emit (strict)
        "heldout_top3": gold_top3(heldout_misses) / nh,       # gold in top-3 (softer)
        "heldout_gold_sim": gold_sim(heldout_misses),         # mean gold cosine (gradient)
        "n_heldout": len(heldout_misses),
    }


# --------------------------------------------------------------------------
# 5. ship gate — adopt ONLY if every floor holds (stability guarantee)
# --------------------------------------------------------------------------
def ship_gate(before: dict, after: dict, rt_before: dict | None = None,
              rt_after: dict | None = None, fp_tol: float = 0.02,
              zero_tol: float = 0.10, val_tol: float = 0.05) -> tuple[bool, list[str]]:
    """The checkpoint ships only if EVERY stability floor holds. The encoder-level
    floors are necessary but NOT sufficient — when the authoritative RUNTIME floors
    (587 single-turn, multiturn, GATE_LEAK) are supplied they are hard conditions
    too, and they can catch an end-to-end regression the encoder proxies miss."""
    checks = []

    def chk(name, ok, detail):
        checks.append((name, ok, detail))
        return ok

    passed = True
    passed &= chk("nonsense_fp ≤ before+tol",
                  after["nonsense_fp"] <= before["nonsense_fp"] + fp_tol,
                  f"{before['nonsense_fp']:.2f} → {after['nonsense_fp']:.2f}")
    passed &= chk("zero-data top3 not degraded",
                  after["zero_top3"] >= before["zero_top3"] - zero_tol,
                  f"{before['zero_top3']:.2f} → {after['zero_top3']:.2f}")
    passed &= chk("gap recovery ≥ before-tol",
                  after["gap_recovery"] >= before["gap_recovery"] - val_tol,
                  f"{before['gap_recovery']:.2f} → {after['gap_recovery']:.2f}")
    passed &= chk("val top-1 ≥ before-tol",
                  after["val_top1"] >= before["val_top1"] - val_tol,
                  f"{before['val_top1']:.2f} → {after['val_top1']:.2f}")
    if rt_before and rt_after:
        passed &= chk("587 single-turn CORRECT not regressed",
                      rt_after["dogfood_correct"] >= rt_before["dogfood_correct"],
                      f"{rt_before['dogfood_correct']} → {rt_after['dogfood_correct']}")
        passed &= chk("GATE_LEAK == 0 (containment)",
                      rt_after["gate_leak"] == 0,
                      f"{rt_after['gate_leak']}")
        passed &= chk("multiturn novel recovery not regressed",
                      rt_after["mt_novel_n"] >= rt_before["mt_novel_n"],
                      f"{rt_before['mt_novel_n']}/14 → {rt_after['mt_novel_n']}/14")
        passed &= chk("multiturn in-vocab no-regression held",
                      rt_after["mt_in_n"] >= rt_before["mt_in_n"],
                      f"{rt_before['mt_in_n']}/24 → {rt_after['mt_in_n']}/24")
    lines = [f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}"
             for name, ok, detail in checks]
    lines.append(f"  plasticity (held-out top1/top3/goldsim): "
                 f"{after['heldout_recovery']:.2f}/{after.get('heldout_top3',0):.2f}/"
                 f"{after.get('heldout_gold_sim',0):.3f} (n={after['n_heldout']})")
    return bool(passed), lines


# --------------------------------------------------------------------------
# optional: runtime-floor confirmation (587 + multiturn) for an adopted candidate
# --------------------------------------------------------------------------
def export_candidate_onnx(model_dir: Path, force: bool = False) -> None:
    """Export a candidate checkpoint to ONNX + build its description index, so `lb`
    (pointed via LINUXBUDDY_MODEL_DIR) can run the runtime floors against it. Skips
    (idempotent) when the artifacts already exist, unless ``force``."""
    model_dir = Path(model_dir)
    if not force and (model_dir / "onnx" / "encoder.onnx").exists() \
            and (model_dir / "index_onnx.npz").exists():
        return
    from . import onnx_export
    onnx_export.MODEL_DIR = model_dir
    onnx_export.ONNX_DIR = model_dir / "onnx"
    onnx_export.run()
