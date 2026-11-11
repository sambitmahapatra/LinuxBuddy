"""Task 38 Part A — base-model bake-off (NO training, NO GPU).

Runs the SAME zero-shot eval harness (eval_zeroshot) across several pretrained
sentence encoders to see whether a stronger base moves the numbers for free,
before we spend any GPU-minute on fine-tuning. Each model is fed its documented
input convention (e5/gte/bge prefixes — see zeroshot.conventions) so the
comparison is fair, embeddings are normalized, and T* is re-tuned per model.

Winner criterion (from the task): the PRIMARY goal is nonsense FP < 15% while
keeping gap recovery >= 80%. So per model we search the (T x margin) grid for the
operating point that reaches gap recovery >= GAP_FLOOR with the LOWEST nonsense
false-positive rate (tie-broken by val top-1). Winner = lowest FP among those,
tie-broken by val top-1. If no model clears the bar, we say so.

Run (ML env, network needed on first run to download the models):
    python -I -m linuxbuddy.ml.bakeoff
"""
from __future__ import annotations

import json
from pathlib import Path

from .eval_zeroshot import (_datasets, _rank_all, _metrics_at_T, _ceiling,
                            T_GRID, MARGIN_GRID)
from .zeroshot import MODES, IntentIndex

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT = REPO_ROOT / "bakeoff_report.md"

GAP_FLOOR = 0.80          # keep gap recovery at or above this
FP_TARGET = 0.15          # primary goal: nonsense FP below this

MODELS = [
    "sentence-transformers/all-MiniLM-L6-v2",     # current baseline
    "sentence-transformers/all-MiniLM-L12-v2",
    "BAAI/bge-small-en-v1.5",
    "thenlper/gte-small",
    "intfloat/e5-small-v2",
]


def _operating_point(sg, sn, sv):
    """Over the (T x margin) grid, pick the point with gap_recovery >= GAP_FLOOR
    and the LOWEST nonsense FP (tie: highest val top-1). If none reach the floor,
    fall back to the max-gap point (and flag it)."""
    grid = []
    for T in T_GRID:
        for mm in MARGIN_GRID:
            gr, na, v1 = _metrics_at_T(sg, sn, sv, T, margin_min=mm)
            grid.append({"T": T, "margin_min": mm, "gap_recovery": gr,
                         "nonsense_abstain": na, "nonsense_fp": round(1 - na, 3),
                         "val_top1_at_T": v1})
    feasible = [g for g in grid if g["gap_recovery"] >= GAP_FLOOR]
    if feasible:
        # lowest FP, then highest val top-1, then highest gap
        best = min(feasible, key=lambda g: (g["nonsense_fp"],
                                            -g["val_top1_at_T"], -g["gap_recovery"]))
        best["meets_floor"] = True
    else:
        best = max(grid, key=lambda g: (g["gap_recovery"], -g["nonsense_fp"],
                                        g["val_top1_at_T"]))
        best["meets_floor"] = False
    return best


def evaluate_model(model_name: str) -> dict:
    gap, neg, val, val_cov = _datasets()
    best_mode = None
    for mode in MODES:
        index = IntentIndex.build(mode=mode, model_name=model_name)
        sg = _rank_all(index, gap)
        sn = _rank_all(index, neg)
        sv = _rank_all(index, val_cov)
        op = _operating_point(sg, sn, sv)
        rec = {
            "model": model_name, "mode": mode,
            "val_top1": _ceiling(sv, 1), "val_top3": _ceiling(sv, 3),
            "op": op, "n_gap": len(sg), "n_neg": len(sn), "n_val_cov": len(sv),
        }
        # best mode per model: prefer meeting the floor, then lowest FP, then val top1
        key = (rec["op"]["meets_floor"], -rec["op"]["nonsense_fp"],
               rec["val_top1"], rec["op"]["gap_recovery"])
        if best_mode is None or key > best_mode["_key"]:
            rec["_key"] = key
            best_mode = rec
    best_mode.pop("_key", None)
    return best_mode


def run():
    rows = []
    for m in MODELS:
        print(f"... evaluating {m}")
        rows.append(evaluate_model(m))

    # winner: among models meeting the floor, lowest FP then val top1; else none
    feasible = [r for r in rows if r["op"]["meets_floor"]]
    if feasible:
        winner = min(feasible, key=lambda r: (r["op"]["nonsense_fp"],
                                              -r["val_top1"]))
    else:
        winner = min(rows, key=lambda r: (r["op"]["nonsense_fp"], -r["val_top1"]))

    _write_report(rows, winner, bool(feasible))
    print("\n=== BAKE-OFF ===")
    for r in rows:
        op = r["op"]
        flag = "" if op["meets_floor"] else "  (below gap floor)"
        print(f"{r['model']:42s} mode={r['mode']:7s} "
              f"T*={op['T']} m>={op['margin_min']} "
              f"gap={op['gap_recovery']*100:3.0f}% FP={op['nonsense_fp']*100:3.0f}% "
              f"val1/3={r['val_top1']*100:.0f}/{r['val_top3']*100:.0f}%{flag}")
    print(f"\nWINNER: {winner['model']} (mode={winner['mode']}, "
          f"FP={winner['op']['nonsense_fp']*100:.0f}% @ gap "
          f"{winner['op']['gap_recovery']*100:.0f}%)")
    cleared = (winner["op"]["meets_floor"] and
               winner["op"]["nonsense_fp"] < FP_TARGET)
    print("ZERO-SHOT ALREADY CLEARS FP<15%@gap>=80%" if cleared
          else "No base clears FP<15% @ gap>=80% zero-shot → fine-tuning warranted")
    return rows, winner


def _write_report(rows, winner, any_feasible):
    L = ["# Base-Model Bake-Off — Task 38 Part A", ""]
    L += ["*Zero-shot, NO fine-tuning, CPU. Same `eval_zeroshot` harness across 5 "
          "pretrained encoders. Each model uses its documented input convention "
          "(e5 `query:`/`passage:`, bge query instruction, gte/MiniLM none) so the "
          "comparison is fair; embeddings normalized, cosine, T\\* re-tuned per "
          "model.*", ""]
    L += [f"**Primary goal:** nonsense FP < {int(FP_TARGET*100)}% at gap recovery "
          f"≥ {int(GAP_FLOOR*100)}%. Operating point per model = the (T, margin) that "
          f"reaches the gap floor with the lowest nonsense FP (tie: val top-1).", ""]
    L += ["| model | best mode | T\\* | margin | gap rec. | nonsense FP | val top-1 | "
          "val top-3 | meets floor |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (not r["op"]["meets_floor"],
                                         r["op"]["nonsense_fp"], -r["val_top1"])):
        op = r["op"]
        star = " ⭐" if r["model"] == winner["model"] else ""
        L += [f"| `{r['model']}`{star} | {r['mode']} | {op['T']} | {op['margin_min']} | "
              f"{op['gap_recovery']*100:.0f}% | {op['nonsense_fp']*100:.0f}% | "
              f"{r['val_top1']*100:.0f}% | {r['val_top3']*100:.0f}% | "
              f"{'yes' if op['meets_floor'] else 'NO'} |"]
    L += [""]
    w, op = winner, winner["op"]
    L += [f"**Winner: `{w['model']}`** (mode `{w['mode']}`) — operating point "
          f"T\\*={op['T']}, margin≥{op['margin_min']}: gap recovery "
          f"{op['gap_recovery']*100:.0f}%, nonsense FP {op['nonsense_fp']*100:.0f}%, "
          f"val top-1 {w['val_top1']*100:.0f}% / top-3 {w['val_top3']*100:.0f}%.", ""]
    cleared = op["meets_floor"] and op["nonsense_fp"] < FP_TARGET
    if cleared:
        L += [f"> **A base model already clears FP<{int(FP_TARGET*100)}% at gap "
              f"≥{int(GAP_FLOOR*100)}% zero-shot.** Fine-tuning may be shortened or "
              f"skipped — confirm against the zero-data probe first.", ""]
    else:
        L += [f"> **No base model clears the bar zero-shot** (best feasible FP = "
              f"{op['nonsense_fp']*100:.0f}% at gap {op['gap_recovery']*100:.0f}%). "
              f"Fine-tuning (Part B) is warranted. The winner is the best *starting "
              f"point* for the contrastive fine-tune.", ""]
    REPORT.write_text("\n".join(L) + "\n")


if __name__ == "__main__":  # pragma: no cover
    run()
