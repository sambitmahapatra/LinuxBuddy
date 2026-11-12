"""Task 48 Part B — the honest 'what the encoder adds' number.

Runs the FROZEN 587 (dogfood_eval) twice — rules only (LINUXBUDDY_ENCODER=0) vs the
full hybrid (encoder on) — reusing dogfood500's own frozen eval + judge + runner, so
the only thing that changes between the two runs is whether the encoder fallback is
allowed to fire. (dogfood500's main() has an 'encoder must be live' precondition that
forbids a rules-only run; this harness reuses its functions directly to get past that
for measurement — it changes no runtime code.)

    .venv-ml/bin/python -I experiments/task48_release/rules_vs_hybrid.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests"))

import dogfood500 as D  # noqa: E402

# collapse the fine-grained judgments into the three Part-B buckets
BUCKET = {
    "CORRECT": "CORRECT", "ABSTAIN_OK": "ABSTAIN", "ABSTAIN_GAP": "ABSTAIN",
    "MISROUTE_SILENT_DROP": "MISROUTE", "WRONG_TARGET": "MISROUTE",
    "ENCODER_MISFIRE": "MISROUTE", "OVEREAGER": "MISROUTE",
    "GATE_LEAK": "GATE_LEAK", "CRASH": "CRASH",
}


def run_once(scenarios, cwds):
    buckets = Counter()
    raw = Counter()
    for sc in scenarios:
        cwd = cwds.get(sc.cwd, cwds["maze"])
        out, err, rc = D.run_lb(sc.request, cwd)
        j, _src, _cause = D.judge(sc, out, err, rc)
        raw[j] += 1
        buckets[BUCKET.get(j, j)] += 1
    return buckets, raw


def main():
    D.MAZE_ROOT, deep = D.build_fixture()
    cwds = {"maze": D.MAZE_ROOT, "deep": deep,
            "outside": tempfile.mkdtemp(prefix="lb_rvh_outside_")}
    scenarios, _chains = D.load_eval()
    n = len(scenarios)
    print(f"frozen single-turn eval: {n} scenarios\n")

    os.environ["LINUXBUDDY_ENCODER"] = "0"
    rules, rules_raw = run_once(scenarios, cwds)
    os.environ.pop("LINUXBUDDY_ENCODER", None)
    hybrid, hybrid_raw = run_once(scenarios, cwds)

    print(f"{'bucket':12} {'rules-only':>12} {'hybrid':>10} {'delta':>8}")
    for b in ("CORRECT", "MISROUTE", "ABSTAIN", "GATE_LEAK", "CRASH"):
        r, h = rules[b], hybrid[b]
        print(f"{b:12} {r:>12} {h:>10} {h - r:>+8}")
    print(f"\nCORRECT: rules {100*rules['CORRECT']/n:.1f}% → hybrid "
          f"{100*hybrid['CORRECT']/n:.1f}%  (+{hybrid['CORRECT']-rules['CORRECT']} rows)")
    print(f"rules-only raw : {dict(rules_raw)}")
    print(f"hybrid    raw : {dict(hybrid_raw)}")


if __name__ == "__main__":
    main()
