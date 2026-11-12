"""Task 45 — END-TO-END acceptance of the wired session resolver.

Drives the FROZEN multi-turn eval (data/eval/multiturn_eval.jsonl) through the
REAL `lb` session path (cli.main, encoder ON), turn by turn, and reports the
acceptance deltas:
  * in-vocab no-regression  (the rules' 25/25 still hold end-to-end)
  * NOVEL recovery          (operate turns the rules abstain on, now emitted)
  * destructive safety      (elliptical destructive turns still abstain, 0 cmd)

    .venv-ml/bin/python -I experiments/task45_wire/eval_e2e.py

Expected commands are derived by replaying the gold deltas through a real
SessionFrame + the actual planner/renderer, so the comparison is exact.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from linuxbuddy import cli, session           # noqa: E402
from linuxbuddy.planner import compile        # noqa: E402
from linuxbuddy.render import to_shell        # noqa: E402

EVAL = REPO / "data" / "eval" / "multiturn_eval.jsonl"


def load_chains():
    chains, order = {}, []
    for line in EVAL.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('{"_comment'):
            continue
        r = json.loads(line)
        if r["chain_id"] not in chains:
            chains[r["chain_id"]] = []
            order.append(r["chain_id"])
        chains[r["chain_id"]].append(r)
    return [chains[c] for c in order]


def expected_command(turns, upto):
    """Replay gold deltas through a real SessionFrame -> the canonical command."""
    sf = None
    for t in turns[:upto + 1]:
        d = t["delta"]
        if t["act"] == "reset":
            sf = None
            continue
        if t["act"] == "new":
            sf = session.SessionFrame(targets={"path": "."})
            if d.get("name"):
                sf.targets["name"] = d["name"]
            if d.get("size"):
                sf.filters["size"] = d["size"]
            if d.get("mtime") is not None:
                sf.filters["mtime"] = d["mtime"]
        elif sf is not None:
            sf.merge({"targets": {k: d[k] for k in ("name",) if k in d},
                      "filters": {k: d[k] for k in ("size", "mtime") if k in d},
                      **({"modifier": d["modifier"]} if "modifier" in d else {})})
    if sf is None:
        return None
    try:
        return to_shell(compile(sf.to_command_plan()))
    except Exception:
        return None


def run_turn(request, sid, cache, maze):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main([request])
    return out.getvalue().strip(), rc


def main():
    chains = load_chains()
    cache = tempfile.mkdtemp(prefix="lb45_")
    maze = tempfile.mkdtemp(prefix="lb45maze_")
    os.environ["LINUXBUDDY_CACHE_DIR"] = cache
    os.environ["LINUXBUDDY_MAZE_ROOT"] = maze
    os.environ.pop("LINUXBUDDY_ENCODER", None)
    os.chdir(maze)

    tally = Counter()
    recovered_detail = []
    for turns in chains:
        cid = turns[0]["chain_id"]
        sid = f"e2e_{cid}"
        os.environ["LINUXBUDDY_SESSION"] = sid
        cli.main(["--reset"])
        for i, t in enumerate(turns):
            emitted, rc = run_turn(t["text"], sid, cache, maze)
            exp = expected_command(turns, i)
            vocab, risk = t["vocab"], t["risk"]

            if risk == "destructive":
                ok = (emitted == "" and rc == 1)
                tally["destructive_total"] += 1
                tally["destructive_abstain"] += ok
                continue
            if t["act"] == "reset":
                continue
            if vocab == "in":
                tally["in_total"] += 1
                tally["in_ok"] += (emitted == exp)
                if emitted != exp:
                    recovered_detail.append(("IN-REGRESS", cid, t["text"], emitted, exp))
            elif vocab == "novel" and t["delta"].get("modifier"):
                tally["novel_total"] += 1
                hit = (emitted == exp and rc == 0)
                tally["novel_recovered"] += hit
                recovered_detail.append(("RECOVERED" if hit else "missed", cid,
                                         t["text"], emitted, exp))

    def p(a, b):
        return f"{a}/{b} ({100*a/b:.0f}%)" if b else "0/0"

    print("=== END-TO-END acceptance (wired session path, encoder ON) ===")
    print(f"  IN-VOCAB no-regression (emitted == expected): "
          f"{p(tally['in_ok'], tally['in_total'])}")
    print(f"  NOVEL recovery (rules-abstain operate turns now emitted correctly): "
          f"{p(tally['novel_recovered'], tally['novel_total'])}   <-- headline")
    print(f"  DESTRUCTIVE elliptical abstain (0 command): "
          f"{p(tally['destructive_abstain'], tally['destructive_total'])}")
    print("\n  novel detail:")
    for verdict, cid, tx, em, ex in recovered_detail:
        if verdict in ("RECOVERED", "missed"):
            print(f"     [{verdict:9}] {cid} {tx!r}")
            if verdict == "missed":
                print(f"          emitted={em!r}  expected={ex!r}")
    regress = [d for d in recovered_detail if d[0] == "IN-REGRESS"]
    if regress:
        print("\n  !! IN-VOCAB REGRESSIONS:")
        for _, cid, tx, em, ex in regress:
            print(f"     {cid} {tx!r}: emitted={em!r} expected={ex!r}")


if __name__ == "__main__":
    main()
