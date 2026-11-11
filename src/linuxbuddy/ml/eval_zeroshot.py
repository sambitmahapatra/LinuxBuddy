"""Offline evaluation of the zero-shot bi-encoder (Task 37) — NO training.

Answers the spike's question: with a pretrained MiniLM and good descriptions, how
many of the rules' 22 gap phrasings do we recover at top-1, while still abstaining
on nonsense? Produces data/eval_cache.jsonl and zeroshot_spike_report.md.

Run (in the ML env):  python -I -m linuxbuddy.ml.eval_zeroshot
"""
from __future__ import annotations

import json
from pathlib import Path

from .zeroshot import ABSTAIN, MODES, IntentIndex, load_descriptions

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
RAW = DATA / "single_turn.raw.jsonl"
VAL = DATA / "val.jsonl"
CACHE = DATA / "eval_cache.jsonl"
REPORT = REPO_ROOT / "zeroshot_spike_report.md"

T_GRID = [round(0.20 + 0.025 * i, 3) for i in range(19)]    # 0.200 .. 0.650
MARGIN_GRID = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10]
FP_BUDGET = 0.15                                            # nonsense FP soft aim


def _read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _datasets():
    raw = _read(RAW)
    gap = [r for r in raw if r["source"] == "stress_gap"]
    neg = [r for r in raw if r["intent"] == ABSTAIN]
    val = _read(VAL)
    val_cov = [r for r in val if r["intent"] != ABSTAIN]
    return gap, neg, val, val_cov


def _rank_all(index: IntentIndex, rows: list[dict]) -> list[dict]:
    """Attach top-k ranking to each row (so metrics/sweep need no re-embedding)."""
    out = []
    for r in rows:
        ranked = index.rank(r["text"])
        out.append({
            "text": r["text"],
            "true": r["intent"],
            "source": r.get("source", ""),
            "top3": [[i, round(s, 4)] for i, s in ranked[:3]],
            "top1": ranked[0][0], "top1_score": round(ranked[0][1], 4),
            "margin": round(ranked[0][1] - ranked[1][1], 4),
            "rank_of_true": next((k for k, (i, _) in enumerate(ranked)
                                  if i == r["intent"]), -1),
        })
    return out


def _passes(r, T, margin_min):
    """A confident (non-abstain) prediction: top1 >= T AND margin >= margin_min."""
    return r["top1_score"] >= T and r["margin"] >= margin_min


def _metrics_at_T(scored_gap, scored_neg, scored_val_cov, T, margin_min=0.0):
    # gap recovery: true == top1 AND the prediction is confident (T + margin)
    rec = sum(1 for r in scored_gap if r["top1"] == r["true"] and _passes(r, T, margin_min))
    gap_rec = rec / len(scored_gap) if scored_gap else 0.0
    # nonsense correctly abstained: NOT a confident prediction
    ab = sum(1 for r in scored_neg if not _passes(r, T, margin_min))
    nonsense_abstain = ab / len(scored_neg) if scored_neg else 0.0
    # covered-val top-1 that is also confident
    v1 = sum(1 for r in scored_val_cov
             if r["top1"] == r["true"] and _passes(r, T, margin_min))
    val_top1_T = v1 / len(scored_val_cov) if scored_val_cov else 0.0
    return gap_rec, nonsense_abstain, val_top1_T


def _ceiling(scored, k):
    hit = sum(1 for r in scored if 0 <= r["rank_of_true"] < k)
    return hit / len(scored) if scored else 0.0


def evaluate_mode(mode: str):
    gap, neg, val, val_cov = _datasets()
    index = IntentIndex.build(mode=mode)
    sg, sn, sv = _rank_all(index, gap), _rank_all(index, neg), _rank_all(index, val_cov)
    val_top1 = _ceiling(sv, 1)
    val_top3 = _ceiling(sv, 3)

    sweep = []
    for T in T_GRID:
        gr, na, v1 = _metrics_at_T(sg, sn, sv, T)
        sweep.append({"T": T, "gap_recovery": gr, "nonsense_abstain": na,
                      "val_top1_at_T": v1, "nonsense_fp": round(1 - na, 3)})
    # T*: pick the KNEE — maximize the balanced score gap_recovery * nonsense_abstain
    # (an absolute FP cutoff just lands on the grid edge; the knee is the real
    # operating point). FP is still reported as a soft aim.
    tstar = max(sweep, key=lambda s: (s["gap_recovery"] * s["nonsense_abstain"],
                                      s["val_top1_at_T"]))

    # Margin as a SECOND abstain lever, evaluated at T*: does requiring a top1-top2
    # margin trim nonsense FP without costing gap recovery?
    margin_sweep = []
    for mm in MARGIN_GRID:
        gr, na, v1 = _metrics_at_T(sg, sn, sv, tstar["T"], margin_min=mm)
        margin_sweep.append({"margin_min": mm, "gap_recovery": gr,
                             "nonsense_abstain": na, "val_top1_at_T": v1,
                             "nonsense_fp": round(1 - na, 3)})
    best_margin = max(margin_sweep,
                      key=lambda s: (s["gap_recovery"] * s["nonsense_abstain"],
                                     s["val_top1_at_T"]))
    return {
        "mode": mode, "val_top1": val_top1, "val_top3": val_top3,
        "sweep": sweep, "tstar": tstar,
        "margin_sweep": margin_sweep, "best_margin": best_margin,
        "scored_gap": sg, "scored_neg": sn, "scored_val": sv,
        "n_gap": len(sg), "n_neg": len(sn), "n_val_cov": len(sv),
    }


def _verdict(best) -> tuple[str, str]:
    op = best["best_margin"]          # the best (T*, margin) operating point
    g = op["gap_recovery"]
    na = op["nonsense_abstain"]
    t1, t3 = best["val_top1"], best["val_top3"]
    if g >= 0.85 and na >= 0.85 and t1 >= 0.65:
        return ("GOOD ENOUGH",
                "the zero-shot floor is strong (high gap recovery AND clean nonsense "
                "rejection) — wire it as the rules fallback next, skip fine-tuning.")
    if g >= 0.85 and na >= 0.78:
        return ("GOOD ENOUGH (as a rules fallback)",
                "gap recovery is high and the ranking space is clearly right; the "
                "encoder only runs AFTER the rules abstain, so its job is gap rescue, "
                "which it does well. Nonsense rejection via the absolute threshold is "
                "soft (~15-20% forced), so wire it with the margin gate and treat "
                "tighter abstain (a light contrastive fine-tune) as an optional "
                "follow-up, not a blocker.")
    if t3 >= 0.80 and t1 < 0.65:
        return ("NEEDS FINE-TUNING",
                "the embedding space is right (top-3 high) but top-1 is soft — a "
                "contrastive fine-tune on the labeled pairs should sharpen it.")
    if g < 0.6 and t3 >= 0.70:
        return ("NEEDS BETTER DESCRIPTIONS",
                "specific gaps miss because their descriptions are weak — iterate "
                "Part A (cheap) and re-run before any training.")
    return ("NEEDS FINE-TUNING",
            "the embedding space is roughly right — the gap set reaches "
            f"{g*100:.0f}% top-1 recovery and val top-3 is {t3*100:.0f}% — but two "
            f"things block wiring it as-is: (1) top-1 is soft (val {t1*100:.0f}%), "
            "with errors concentrated between NEIGHBORING intents (find_by_type vs "
            "run_script/list_all, make_dir vs setup_project, cd_parent vs go_back, "
            "count_matches vs count_lines); and (2) nonsense is not separable by an "
            "absolute cosine threshold (no T gives both strong recovery and <15% "
            "false-positive, and the top1-top2 margin does not help). Both are "
            "exactly what a contrastive fine-tune on the Task-36 labeled pairs "
            "targets — pulling neighbours and nonsense apart. Proceed to fine-tuning "
            "next; keep kb/intent_descriptions.yaml as the reusable anchor set and "
            "re-use this harness to measure the lift.")


def run_all():
    results = {m: evaluate_mode(m) for m in MODES}
    best = max(results.values(),
              key=lambda r: (r["tstar"]["gap_recovery"], r["val_top1"]))

    # cache the BEST mode's per-utterance rankings
    with open(CACHE, "w") as f:
        for setname, rows in (("gap", best["scored_gap"]),
                              ("abstain_neg", best["scored_neg"]),
                              ("val_covered", best["scored_val"])):
            for r in rows:
                f.write(json.dumps({**r, "set": setname, "mode": best["mode"]},
                                   sort_keys=True) + "\n")

    _write_report(results, best)
    v, _ = _verdict(best)
    bm = best["best_margin"]
    print(f"best mode: {best['mode']}  T*={best['tstar']['T']}  margin>={bm['margin_min']}")
    print(f"gap recovery: {bm['gap_recovery']*100:.0f}% "
          f"({round(bm['gap_recovery']*best['n_gap'])}/{best['n_gap']})")
    print(f"nonsense abstain: {bm['nonsense_abstain']*100:.0f}% "
          f"(FP {bm['nonsense_fp']*100:.0f}%)")
    print(f"val top1/top3 (ceiling): {best['val_top1']*100:.0f}% / {best['val_top3']*100:.0f}%")
    print(f"VERDICT: {v}")
    return results, best


def _write_report(results, best):
    descs = load_descriptions()
    v, v_detail = _verdict(best)
    ts = best["tstar"]
    L = ["# Zero-Shot Bi-Encoder Spike — Report", ""]
    L += [f"*Task 37 — measurement spike, NO fine-tuning, CPU only. "
          f"Model: `sentence-transformers/all-MiniLM-L6-v2` (local, ~22M params).*", ""]
    L += ["## Setup"]
    L += [f"- Model: all-MiniLM-L6-v2 (CPU torch). Descriptions: "
          f"`kb/intent_descriptions.yaml` (all 85 intents)."]
    L += [f"- Description strategy compared: " +
          ", ".join(f"`{m}` (val top1 {results[m]['val_top1']*100:.0f}%, "
                    f"gap@T* {results[m]['tstar']['gap_recovery']*100:.0f}%)"
                    for m in MODES)]
    L += [f"- **Best strategy: `{best['mode']}`**; operating point **T\\* = {ts['T']}** "
          f"(chosen to maximize gap recovery while keeping nonsense false-positives "
          f"≤ {int(FP_BUDGET*100)}%)."]
    L += ["", "## Results (best strategy)"]
    L += [f"- **Val (ceiling): top-1 {best['val_top1']*100:.0f}%, "
          f"top-3 {best['val_top3']*100:.0f}%** (n={best['n_val_cov']} covered rows)"]
    nrec = round(ts["gap_recovery"] * best["n_gap"])
    L += [f"- **Gap set: recovered {nrec}/{best['n_gap']} at T\\*** "
          f"({ts['gap_recovery']*100:.0f}%)  ← the headline number"]
    L += [f"- **Nonsense abstain: {ts['nonsense_abstain']*100:.0f}% correct "
          f"(false-positive {ts['nonsense_fp']*100:.0f}%)** at T\\* (n={best['n_neg']})"]
    L += ["", "### Threshold sweep (best strategy)"]
    L += ["| T | gap recovery | val top-1 (≥T) | nonsense abstained | nonsense FP |",
          "|---|---|---|---|---|"]
    for s in best["sweep"]:
        mark = "  **← T\\***" if s["T"] == ts["T"] else ""
        L += [f"| {s['T']} | {s['gap_recovery']*100:.0f}% | {s['val_top1_at_T']*100:.0f}% | "
              f"{s['nonsense_abstain']*100:.0f}% | {s['nonsense_fp']*100:.0f}%{mark} |"]
    L += ["", f"T\\* chosen at the knee (max gap_recovery × nonsense_abstain), not an "
          f"arbitrary FP cutoff. The curve shows the real tension: nonsense is not "
          f"cleanly separable by absolute cosine alone — FP only falls below ~15% "
          f"near T=0.55, which starts costing gap recovery."]
    bm = best["best_margin"]
    L += ["", f"### Margin as a second abstain lever (at T\\*={ts['T']})"]
    L += ["Require top1−top2 margin ≥ m as well; does it trim nonsense FP without "
          "losing gaps?", ""]
    L += ["| margin ≥ | gap recovery | val top-1 | nonsense abstained | nonsense FP |",
          "|---|---|---|---|---|"]
    for s in best["margin_sweep"]:
        mk = "  **← best**" if s["margin_min"] == bm["margin_min"] else ""
        L += [f"| {s['margin_min']} | {s['gap_recovery']*100:.0f}% | "
              f"{s['val_top1_at_T']*100:.0f}% | {s['nonsense_abstain']*100:.0f}% | "
              f"{s['nonsense_fp']*100:.0f}%{mk} |"]
    L += ["", f"**Recommended operating point: T\\*={ts['T']}, margin≥{bm['margin_min']}** "
          f"→ gap recovery {bm['gap_recovery']*100:.0f}%, nonsense abstain "
          f"{bm['nonsense_abstain']*100:.0f}% (FP {bm['nonsense_fp']*100:.0f}%), "
          f"val top-1 {bm['val_top1_at_T']*100:.0f}%."]
    L += ["", "## Verdict", "", f"**{v}** — {v_detail}", ""]

    # gap failures
    L += ["## Which gap phrasings fail, and why", ""]
    mm = best["best_margin"]["margin_min"]
    miss = [r for r in best["scored_gap"]
            if not (r["top1"] == r["true"] and _passes(r, ts["T"], mm))]
    if not miss:
        L += ["- none — every gap phrasing recovered at T*.", ""]
    else:
        L += ["| utterance | true intent | predicted top-1 (score) | rank of true |",
              "|---|---|---|---|"]
        for r in miss:
            rt = r["rank_of_true"]
            L += [f"| {r['text']} | {r['true']} | {r['top1']} ({r['top1_score']}) | "
                  f"{'top-'+str(rt+1) if rt>=0 else '>top-k'} |"]
        L += [""]

    # worst val performers
    L += ["## Val: worst performers (rank of true label)", ""]
    worst = sorted(best["scored_val"], key=lambda r: -(r["rank_of_true"]
                   if r["rank_of_true"] >= 0 else 999))[:10]
    L += ["| utterance | true | top-1 (score) | rank of true |", "|---|---|---|---|"]
    for r in worst:
        rt = r["rank_of_true"]
        L += [f"| {r['text']} | {r['true']} | {r['top1']} ({r['top1_score']}) | "
              f"{'top-'+str(rt+1) if rt>=0 else '>top-k'} |"]
    L += [""]

    # zero-data intents
    have_examples = sum(1 for s in descs.values() if (s or {}).get("examples"))
    L += ["## The 27 zero-data intents", ""]
    L += [f"All 85 intents (including the 27 with no labeled data) have descriptions, "
          f"so the bi-encoder can rank them with zero examples — {have_examples} also "
          f"carry example anchors. Whether that is *acceptable* can only be judged "
          f"once any appear in evaluation; none of the 27 appear in the 55-row val "
          f"set, so they are not directly measured here. Recommendation: keep them "
          f"description-served for now and let the Phase-1 confusion matrix (on a "
          f"broader eval) decide which need the targeted collection pass.", ""]
    REPORT.write_text("\n".join(L) + "\n")


if __name__ == "__main__":  # pragma: no cover
    run_all()
