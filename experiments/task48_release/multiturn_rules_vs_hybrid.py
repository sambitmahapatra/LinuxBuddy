"""Task 48 Part B — multiturn eval, rules-only vs hybrid.

Reuses the Task-45 end-to-end harness (load_chains / expected_command / run_turn,
which drives the REAL `cli.main` session path in-process) but controls
LINUXBUDDY_ENCODER itself, so it can run the SAME frozen multiturn eval with the
encoder off (rules only) and on (hybrid). Changes no runtime code.

For the NOVEL (rules-abstain) turns, the rules-only column is split into abstain vs
MISROUTE — because without the encoder some elliptical turns don't cleanly abstain,
they misfire (e.g. 'which of those is heaviest' -> `command -v -- of`), which is
exactly the failure the encoder fallback removes.

    .venv-ml/bin/python -I experiments/task48_release/multiturn_rules_vs_hybrid.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments" / "task45_wire"))

import eval_e2e as E  # noqa: E402
from linuxbuddy import cli  # noqa: E402


def run_mode(encoder_on: bool):
    chains = E.load_chains()
    cache = tempfile.mkdtemp(prefix="rvh_mt_")
    maze = tempfile.mkdtemp(prefix="rvh_mtmaze_")
    os.environ["LINUXBUDDY_CACHE_DIR"] = cache
    os.environ["LINUXBUDDY_MAZE_ROOT"] = maze
    if encoder_on:
        os.environ.pop("LINUXBUDDY_ENCODER", None)
    else:
        os.environ["LINUXBUDDY_ENCODER"] = "0"
    os.chdir(maze)

    t = Counter()
    for turns in chains:
        sid = f"rvh_{turns[0]['chain_id']}"
        os.environ["LINUXBUDDY_SESSION"] = sid
        cli.main(["--reset"])
        for i, turn in enumerate(turns):
            emitted, rc = E.run_turn(turn["text"], sid, cache, maze)
            exp = E.expected_command(turns, i)
            if turn["risk"] == "destructive":
                t["dest_total"] += 1
                t["dest_abstain"] += (emitted == "" and rc == 1)
            elif turn["act"] == "reset":
                continue
            elif turn["vocab"] == "in":
                t["in_total"] += 1
                t["in_ok"] += (emitted == exp)
            elif turn["vocab"] == "novel" and turn["delta"].get("modifier"):
                t["novel_total"] += 1
                if emitted == exp and rc == 0:
                    t["novel_recovered"] += 1
                elif emitted == "":
                    t["novel_abstain"] += 1
                else:
                    t["novel_misroute"] += 1
    return t


def main():
    rules = run_mode(encoder_on=False)
    hybrid = run_mode(encoder_on=True)

    def row(label, k, tot, d):
        r, h = d[0][k], d[1][k]
        rt, ht = d[0][tot], d[1][tot]
        print(f"{label:34} {r}/{rt:<8} {h}/{ht:<8}")

    print(f"{'metric':34} {'rules-only':12} {'hybrid':12}")
    row("in-vocab no-regression", "in_ok", "in_total", (rules, hybrid))
    row("NOVEL recovered (correct cmd)", "novel_recovered", "novel_total", (rules, hybrid))
    print(f"{'  novel → abstain (no cmd)':34} "
          f"{rules['novel_abstain']}/{rules['novel_total']:<8} "
          f"{hybrid['novel_abstain']}/{hybrid['novel_total']:<8}")
    print(f"{'  novel → MISROUTE (wrong cmd)':34} "
          f"{rules['novel_misroute']}/{rules['novel_total']:<8} "
          f"{hybrid['novel_misroute']}/{hybrid['novel_total']:<8}")
    row("destructive elliptical abstain", "dest_abstain", "dest_total", (rules, hybrid))


if __name__ == "__main__":
    main()
