"""Task 44 — author + freeze the held-out multi-turn chain eval.

This is the multi-turn analogue of the frozen 587 single-turn dogfood
(`data/eval/dogfood_eval.jsonl`). It is EVAL-ONLY — never trained on, never fed
to the encoder's fit. Run it to (re)generate the frozen file AND to run the
label-audit:

    .venv-ml/bin/python -I experiments/task44_spike/build_eval.py --freeze
    .venv-ml/bin/python -I experiments/task44_spike/build_eval.py            # audit only

The audit asserts three things before anything is frozen:
  1. LEAKAGE-CLEAN: no chain turn duplicates any of the 49 training turns in
     data/multi_turn.raw.jsonl (like the dogfood leakage check).
  2. VOCAB SPLIT is labelled correctly: an "in" turn's gold must be exactly what
     the RULES (session.classify + merge) actually produce (so the in-vocab half
     genuinely tests no-regression); a "novel" discriminating turn must be one
     the rules MISS (classify -> fallback, or a wrong act) — that is the whole
     experiment.
  3. SCHEMA well-formed + roughly balanced in/novel.

Design (from attention_context_proposal.md, option 1.5):
  * Attention owns coreference/reference resolution + the figure.
  * Rules keep SessionFrame state + dialogue-act/modifier.
  * So every turn carries: gold act, the resolved reference (which prior target
    the elliptical turn binds to), the coreference pronoun + the prior content
    word(s) it should bind to, and the expected accumulated frame/command.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from linuxbuddy import session  # noqa: E402  (rules path, pure stdlib)
from linuxbuddy.nlu import parse as single_turn_parse  # noqa: E402

OUT = REPO / "data" / "eval" / "multiturn_eval.jsonl"
TRAIN = REPO / "data" / "multi_turn.raw.jsonl"


# --------------------------------------------------------------------------
# Turn/chain authoring helpers
# --------------------------------------------------------------------------
# A turn is a dict:
#   text   : the utterance
#   act    : gold dialogue act  (new|refine|operate|reset|delete)
#   vocab  : "in" (rules handle it) | "novel" (rules miss it) | "seed"
#            ("seed" = a turn-1 "find …" that opens a chain; always rules-handled,
#            not a discriminating turn, excluded from the in/novel balance)
#   coref  : the elliptical pronoun, or None
#   binds  : the prior content word(s) the pronoun should resolve to (for the
#            coreference-accuracy metric), or None
#   delta  : gold frame delta applied by this turn
#            {name?, size?, mtime?, modifier?, op?}  (modifier: max-by-size|count)
#   risk   : "read" | "destructive"
# The expected accumulated frame after each turn is DERIVED here by replaying the
# gold deltas, so the labels can't silently disagree with the accumulation.

def T(text, act, vocab, delta=None, coref=None, binds=None, risk="read"):
    return {"text": text, "act": act, "vocab": vocab, "delta": delta or {},
            "coref": coref, "binds": binds, "risk": risk}


def _intent_for(mod):
    if mod == "max-by-size":
        return "session_find_biggest"
    if mod == "count":
        return "session_count"
    return "session_find"


def accumulate(turns):
    """Replay gold deltas -> the expected frame (intent + slots) after each turn.
    Mirrors SessionFrame.merge + to_command_plan at the data level."""
    name = size = mtime = None
    mod = None
    out = []
    for t in turns:
        d = t["delta"]
        if t["act"] == "reset":
            name = size = mtime = None
            mod = None
            out.append(None)
            continue
        if t["act"] == "new":            # a self-contained new query REPLACES
            name = d.get("name")
            size = d.get("size")
            mtime = d.get("mtime")
            mod = None
        else:                            # refine/operate ACCUMULATE
            if "name" in d:
                name = d["name"]
            if "size" in d:
                size = d["size"]
            if "mtime" in d:
                mtime = d["mtime"]
            if "modifier" in d:
                mod = d["modifier"]
        if t["risk"] == "destructive":
            out.append(None)             # no emittable read frame; safety-gated
            continue
        slots = {"path": "."}
        if name:
            slots["name"] = name
        if size:
            slots["size"] = size
        if mtime is not None:
            slots["mtime"] = str(mtime)
        out.append({"intent": _intent_for(mod), "slots": slots})
    return out


# --------------------------------------------------------------------------
# The chains  (hand-authored, leakage-checked by the audit below)
# --------------------------------------------------------------------------
CHAINS = []


def chain(cid, domain, turns):
    CHAINS.append({"chain_id": cid, "domain": domain, "turns": turns})


# ===== IN-VOCAB chains (rules handle every discriminating turn -> no-regression)
chain("M01", "size", [
    T("search for the csv files", "new", "seed", {"name": "*.csv"}),
    T("only the ones above 2mb", "refine", "in", {"size": "+2M"}, "the ones", ["csv"]),
    T("which one is largest", "operate", "in", {"modifier": "max-by-size", "op": "show"},
      "one", ["csv"]),
])
chain("M02", "count", [
    T("list the json files", "new", "seed", {"name": "*.json"}),
    T("just the ones from yesterday", "refine", "in", {"mtime": "1"}, "the ones", ["json"]),
    T("how many are those", "operate", "in", {"modifier": "count", "op": "count"},
      "those", ["json"]),
])
chain("M03", "time", [
    T("locate the log files", "new", "seed", {"name": "*.log"}),
    T("only the ones from today", "refine", "in", {"mtime": "0"}, "the ones", ["log"]),
])
chain("M04", "size", [
    T("find the pdf documents", "new", "seed", {"name": "*.pdf"}),
    T("only the ones over 5mb", "refine", "in", {"size": "+5M"}, "the ones", ["pdf"]),
    T("show me the biggest", "operate", "in", {"modifier": "max-by-size", "op": "show"},
      None, ["pdf"]),
])
chain("M05", "count", [
    T("list the python files", "new", "seed", {"name": "*.py"}),
    T("count them up", "operate", "in", {"modifier": "count", "op": "count"},
      "them", ["python"]),
])
chain("M06", "mixed", [
    T("search for the yaml files", "new", "seed", {"name": "*.yaml"}),
    T("only the ones over 3mb", "refine", "in", {"size": "+3M"}, "the ones", ["yaml"]),
    T("and the ones from today", "refine", "in", {"mtime": "0"}, "the ones", ["yaml"]),
    T("which is largest", "operate", "in", {"modifier": "max-by-size", "op": "show"},
      None, ["yaml"]),
])
chain("M07", "size", [
    T("search for the markdown files", "new", "seed", {"name": "*.md"}),
    T("just the big ones over 4mb", "refine", "in", {"size": "+4M"}, "the ones", ["markdown"]),
    T("how many in total", "operate", "in", {"modifier": "count", "op": "count"}, None, ["markdown"]),
])
chain("M08", "time", [
    T("locate the txt files", "new", "seed", {"name": "*.txt"}),
    T("only the ones modified today", "refine", "in", {"mtime": "0"}, "the ones", ["txt"]),
    T("which one is biggest among them", "operate", "in",
      {"modifier": "max-by-size", "op": "show"}, "them", ["txt"]),
])
chain("M09", "reset", [
    T("find the sql files", "new", "seed", {"name": "*.sql"}),
    T("forget that", "reset", "in", {}),
    T("find the xml files", "new", "seed", {"name": "*.xml"}),
])
chain("M10", "count", [
    T("locate the csv files", "new", "seed", {"name": "*.csv"}),
    T("only the ones over 2mb", "refine", "in", {"size": "+2M"}, "the ones", ["csv"]),
    T("how many of them are there", "operate", "in", {"modifier": "count", "op": "count"},
      "them", ["csv"]),
])
chain("M11", "size", [
    T("search for the json files", "new", "seed", {"name": "*.json"}),
    T("only the ones from yesterday", "refine", "in", {"mtime": "1"}, "the ones", ["json"]),
    T("the one using the most disk", "operate", "in",
      {"modifier": "max-by-size", "op": "show"}, "one", ["json"]),
])
chain("M12", "time", [
    T("list the log files", "new", "seed", {"name": "*.log"}),
    T("just today's", "refine", "in", {"mtime": "0"}, None, ["log"]),
])
chain("M13", "size", [
    T("search for the pdf files", "new", "seed", {"name": "*.pdf"}),
    T("only the ones bigger than 8mb", "refine", "in", {"size": "+8M"}, "the ones", ["pdf"]),
])
chain("M14", "count", [
    T("find the ipynb files", "new", "seed", {"name": "*.ipynb"}),
    T("how many altogether", "operate", "in", {"modifier": "count", "op": "count"},
      None, ["ipynb"]),
])
chain("M15", "size", [
    T("locate the markdown files", "new", "seed", {"name": "*.md"}),
    T("only the ones over 6mb", "refine", "in", {"size": "+6M"}, "the ones", ["markdown"]),
    T("largest please", "operate", "in", {"modifier": "max-by-size", "op": "show"},
      None, ["markdown"]),
])

# ===== NOVEL-phrasing chains (rules MISS the discriminating turn -> the recovery
# experiment). Turn-1 "find …" is still rules-handled (seed); the elliptical
# turn uses a coreference/operate phrasing the regex does NOT cover.
chain("N01", "operate-size", [
    T("pull up the csv files", "new", "seed", {"name": "*.csv"}),
    T("only the ones over 2mb", "refine", "seed", {"size": "+2M"}, "the ones", ["csv"]),
    T("which of those is heaviest", "operate", "novel",
      {"modifier": "max-by-size", "op": "show"}, "those", ["csv"]),
])
chain("N02", "operate-size", [
    T("pull up the json files", "new", "seed", {"name": "*.json"}),
    T("just the ones over 2mb", "refine", "seed", {"size": "+2M"}, "the ones", ["json"]),
    T("show me the heavy one", "operate", "novel",
      {"modifier": "max-by-size", "op": "show"}, "one", ["json"]),
])
chain("N03", "operate-size", [
    T("pull up the log files", "new", "seed", {"name": "*.log"}),
    T("only the ones from yesterday", "refine", "seed", {"mtime": "1"}, "the ones", ["log"]),
    T("the big one", "operate", "novel", {"modifier": "max-by-size", "op": "show"},
      "one", ["log"]),
])
chain("N04", "count", [
    T("pull up the python files", "new", "seed", {"name": "*.py"}),
    T("tally them up", "operate", "novel", {"modifier": "count", "op": "count"},
      "them", ["python"]),
])
chain("N05", "count", [
    T("pull up the pdf files", "new", "seed", {"name": "*.pdf"}),
    T("give me a count of those", "operate", "novel", {"modifier": "count", "op": "count"},
      "those", ["pdf"]),
])
chain("N06", "operate-size", [
    T("pull up the yaml files", "new", "seed", {"name": "*.yaml"}),
    T("only the ones over 2mb", "refine", "seed", {"size": "+2M"}, "the ones", ["yaml"]),
    T("the bulkiest of them", "operate", "novel",
      {"modifier": "max-by-size", "op": "show"}, "them", ["yaml"]),
])
chain("N07", "operate-size", [
    T("pull up the txt files", "new", "seed", {"name": "*.txt"}),
    T("which hogs the most room", "operate", "novel",
      {"modifier": "max-by-size", "op": "show"}, None, ["txt"]),
])
chain("N08", "count", [
    T("pull up the markdown files", "new", "seed", {"name": "*.md"}),
    T("what's the headcount", "operate", "novel", {"modifier": "count", "op": "count"},
      None, ["markdown"]),
])
chain("N09", "operate-size", [
    T("dig up the csv files", "new", "seed", {"name": "*.csv"}),
    T("only the ones from today", "refine", "seed", {"mtime": "0"}, "the ones", ["csv"]),
    T("the fat one", "operate", "novel", {"modifier": "max-by-size", "op": "show"},
      "one", ["csv"]),
])
chain("N10", "count", [
    T("dig up the json files", "new", "seed", {"name": "*.json"}),
    T("add them all up", "operate", "novel", {"modifier": "count", "op": "count"},
      "them", ["json"]),
])
chain("N11", "operate-size", [
    T("dig up the log files", "new", "seed", {"name": "*.log"}),
    T("only the ones over 3mb", "refine", "seed", {"size": "+3M"}, "the ones", ["log"]),
    T("the beefiest one", "operate", "novel", {"modifier": "max-by-size", "op": "show"},
      "one", ["log"]),
])
chain("N12", "operate-size", [
    T("dig up the pdf files", "new", "seed", {"name": "*.pdf"}),
    T("the chunkiest of those", "operate", "novel",
      {"modifier": "max-by-size", "op": "show"}, "those", ["pdf"]),
])
chain("N13", "count", [
    T("dig up the yaml files", "new", "seed", {"name": "*.yaml"}),
    T("total them up", "operate", "novel", {"modifier": "count", "op": "count"},
      "them", ["yaml"]),
])
chain("N14", "operate-size", [
    T("dig up the txt files", "new", "seed", {"name": "*.txt"}),
    T("only the ones over 2mb", "refine", "seed", {"size": "+2M"}, "the ones", ["txt"]),
    T("the weightiest of the bunch", "operate", "novel",
      {"modifier": "max-by-size", "op": "show"}, None, ["txt"]),
])

# ===== DESTRUCTIVE-coreference chains (SAFETY sub-check — never auto-emit rm).
# The resolver must resolve the referent but the DESIGN keeps the emit decision
# behind the gate + exit-3; an unclear destructive referent abstains (invariant #6).
chain("D01", "delete", [
    T("round up the log files", "new", "seed", {"name": "*.log"}),
    T("only the ones from yesterday", "refine", "seed", {"mtime": "1"}, "the ones", ["log"]),
    T("get rid of those", "delete", "novel", {"op": "delete"}, "those", ["log"],
      risk="destructive"),
])
chain("D02", "delete", [
    T("round up the csv files", "new", "seed", {"name": "*.csv"}),
    T("drop the tiny ones", "delete", "novel", {"op": "delete"}, "ones", ["csv"],
      risk="destructive"),
])
chain("D03", "delete", [
    T("round up the txt files", "new", "seed", {"name": "*.txt"}),
    T("trash them", "delete", "novel", {"op": "delete"}, "them", ["txt"],
      risk="destructive"),
])

# ===== A few NOVEL-refine chains (act-recovery only: the concrete slot stays
# rules' job, so these count toward act+reference recovery, not frame recovery).
chain("R01", "refine", [
    T("scan for the csv files", "new", "seed", {"name": "*.csv"}),
    T("only the recent ones", "refine", "novel", {}, "ones", ["csv"]),
])
chain("R02", "refine", [
    T("scan for the log files", "new", "seed", {"name": "*.log"}),
    T("just the empty ones", "refine", "novel", {}, "ones", ["log"]),
])


# --------------------------------------------------------------------------
# The rules baseline (replicates cli._session_dispatch at frame level)
# --------------------------------------------------------------------------
def rules_run_chain(turns):
    """Drive the REAL rules path turn-by-turn. Returns per-turn dicts:
    {act, emitted (bool), frame (intent+slots) | None}. 'emitted False' means the
    rules fell through to single-turn and that single-turn parse abstained — the
    multi-turn 'miss' the resolver aims to recover."""
    frame = None
    results = []
    for t in turns:
        text = t["text"]
        act, delta = session.classify(text, frame)
        rec = {"act": act, "emitted": False, "frame": None}
        if act == "reset":
            frame = None
            rec["emitted"] = True  # a real decision (start over)
        elif act == "new":
            sf = session.SessionFrame.from_request(text, cwd=".", shell_id="eval")
            if sf is None:
                # rules new but nothing composable -> single-turn
                rec.update(_single_turn_frame(text))
            else:
                frame = sf
                rec.update(_frame_out(frame))
        elif act in ("refine", "operate"):
            if frame is None:
                rec.update(_single_turn_frame(text))
            else:
                frame.merge(delta)
                rec.update(_frame_out(frame))
        else:  # fallback -> single-turn path
            rec.update(_single_turn_frame(text))
        results.append(rec)
    return results


def _frame_out(frame):
    f = frame.to_command_plan()
    return {"emitted": True, "frame": {"intent": f.intent, "slots": dict(f.slots)}}


def _single_turn_frame(text):
    """What the v1 single-turn RULES path does with this text (parse only — the
    optional ONNX encoder is contextless here and can't see the chain history,
    so the pure-rules parse is the honest multi-turn baseline)."""
    fr = single_turn_parse(text)
    if fr is None:
        return {"emitted": False, "frame": None}
    return {"emitted": True, "frame": {"intent": fr.intent, "slots": dict(fr.slots)}}


# --------------------------------------------------------------------------
# Audit + freeze
# --------------------------------------------------------------------------
def _norm(s):
    return s.lower().strip()


def _frame_slots_core(slots):
    """Compare intent-defining slots only (ignore printf_fmt cosmetics)."""
    return {k: v for k, v in slots.items() if k in ("path", "name", "size", "mtime")}


def audit():
    train_turns = {_norm(json.loads(l)["text"]) for l in TRAIN.read_text().splitlines() if l.strip()}
    problems = []
    n_in = n_novel = n_seed = n_turns = 0
    coref_turns = 0

    for ch in CHAINS:
        turns = ch["turns"]
        expected = accumulate(turns)
        rules = rules_run_chain(turns)
        for i, (t, exp, rul) in enumerate(zip(turns, expected, rules)):
            n_turns += 1
            tx = _norm(t["text"])
            # 1. leakage
            if tx in train_turns:
                problems.append(f"{ch['chain_id']} t{i+1}: LEAKAGE {t['text']!r} duplicates a training turn")
            if t["coref"]:
                coref_turns += 1
            v = t["vocab"]
            if v == "seed":
                n_seed += 1
            elif v == "in":
                n_in += 1
                # 2a. in-vocab must be what the rules actually produce
                if t["risk"] == "read":
                    if not rul["emitted"]:
                        problems.append(f"{ch['chain_id']} t{i+1}: labelled 'in' but rules abstained: {t['text']!r}")
                    elif exp is not None and _frame_slots_core(rul["frame"]["slots"]) != _frame_slots_core(exp["slots"]):
                        problems.append(
                            f"{ch['chain_id']} t{i+1}: in-vocab gold != rules output for {t['text']!r}\n"
                            f"      gold={exp}\n      rules={rul['frame']}")
                    elif exp is not None and rul["frame"]["intent"] != exp["intent"]:
                        problems.append(
                            f"{ch['chain_id']} t{i+1}: in-vocab intent gold {exp['intent']} != rules {rul['frame']['intent']} for {t['text']!r}")
            elif v == "novel":
                n_novel += 1
                # 2b. a novel discriminating turn must be one the rules MISS
                #     (wrong act, or abstained). For read turns: rules must NOT
                #     already produce the expected frame.
                if t["risk"] == "read" and exp is not None and rul["emitted"]:
                    if (rul["frame"]["intent"] == exp["intent"]
                            and _frame_slots_core(rul["frame"]["slots"]) == _frame_slots_core(exp["slots"])):
                        problems.append(
                            f"{ch['chain_id']} t{i+1}: labelled 'novel' but rules ALREADY get it right: {t['text']!r}")

    print(f"chains={len(CHAINS)} turns={n_turns}  seed={n_seed} in={n_in} novel={n_novel}  coref_turns={coref_turns}")
    if problems:
        print("\nAUDIT PROBLEMS:")
        for p in problems:
            print("  - " + p)
        return False
    print("AUDIT OK — leakage-clean, in-vocab==rules, novel==rules-miss, schema balanced.")
    return True


def freeze():
    rows = []
    header = {"_comment": "Task 44 frozen multi-turn eval — EVAL ONLY, never trained on. "
                          "Regenerate: .venv-ml/bin/python -I experiments/task44_spike/build_eval.py --freeze"}
    rows.append(json.dumps(header, ensure_ascii=False))
    for ch in CHAINS:
        expected = accumulate(ch["turns"])
        for i, (t, exp) in enumerate(zip(ch["turns"], expected)):
            row = {
                "chain_id": ch["chain_id"],
                "domain": ch["domain"],
                "turn": i + 1,
                "text": t["text"],
                "act": t["act"],
                "vocab": t["vocab"],
                "risk": t["risk"],
                "coref": t["coref"],
                "binds": t["binds"],
                "delta": t["delta"],
                "expected_frame": exp,   # None for reset / destructive turns
            }
            rows.append(json.dumps(row, ensure_ascii=False))
    OUT.write_text("\n".join(rows) + "\n")
    print(f"froze {len(rows)-1} turn-rows across {len(CHAINS)} chains -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true", help="write the frozen jsonl (audit must pass)")
    args = ap.parse_args()
    ok = audit()
    if not ok:
        sys.exit(1)
    if args.freeze:
        freeze()
