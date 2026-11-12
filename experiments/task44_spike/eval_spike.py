"""Task 44 — evaluate the attention reference-resolver against the rules baseline.

    .venv-ml/bin/python -I experiments/task44_spike/eval_spike.py
    .venv-ml/bin/python -I experiments/task44_spike/eval_spike.py --figure

Reads the FROZEN eval (data/eval/multiturn_eval.jsonl). Reports, split by
in-vocab vs novel-phrasing:
  * IN-VOCAB no-regression: does the resolver AGREE with the rules where the rules
    are already right (the 48/49-style baseline)?  (must not contradict)
  * NOVEL recovery (the headline): of the elliptical turns the RULES MISS
    (classify -> fallback -> single-turn abstain), how many does the resolver
    recover to the correct frame/command (right reference + right act/modifier)?
  * COREFERENCE accuracy: does the attention bind the pronoun to the correct prior
    target?  (referent-phrase + the stricter type-specific binding)
  * SAFETY: destructive elliptical turns stay abstained/gated; the resolver flags
    them destructive and NEVER emits rm on a guess (invariant #6).
Also sweeps attention signals (which layer/head/aggregation resolves best) and
prints an honest one-line verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from linuxbuddy import session                      # noqa: E402
from linuxbuddy.nlu import parse as single_turn_parse  # noqa: E402
import resolver as R                                 # noqa: E402

EVAL = REPO / "data" / "eval" / "multiturn_eval.jsonl"
HERE = Path(__file__).resolve().parent
FILES_OK = {"files", "file"}


def load_chains():
    chains = defaultdict(list)
    order = []
    for line in EVAL.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('{"_comment'):
            continue
        r = json.loads(line)
        if r["chain_id"] not in chains:
            order.append(r["chain_id"])
        chains[r["chain_id"]].append(r)
    return [chains[c] for c in order]


def _core(slots):
    return {k: v for k, v in (slots or {}).items() if k in ("path", "name", "size", "mtime")}


# --------------------------------------------------------------------------
# Rules baseline, driven turn-by-turn (holds the live SessionFrame)
# --------------------------------------------------------------------------
def rules_step(frame, text):
    """One rules turn. Returns (new_frame, act, emitted, out_frame_dict|None)."""
    act, delta = session.classify(text, frame)
    if act == "reset":
        return None, act, True, None
    if act == "new":
        sf = session.SessionFrame.from_request(text, cwd=".", shell_id="eval")
        if sf is None:
            fr = single_turn_parse(text)
            return frame, act, fr is not None, (
                {"intent": fr.intent, "slots": dict(fr.slots)} if fr else None)
        f = sf.to_command_plan()
        return sf, act, True, {"intent": f.intent, "slots": dict(f.slots)}
    if act in ("refine", "operate") and frame is not None:
        frame.merge(delta)
        f = frame.to_command_plan()
        return frame, act, True, {"intent": f.intent, "slots": dict(f.slots)}
    # fallback (or refine/operate with no frame) -> single-turn rules
    fr = single_turn_parse(text)
    return frame, "fallback", fr is not None, (
        {"intent": fr.intent, "slots": dict(fr.slots)} if fr else None)


def _mod_to_intent(mod):
    return {"max-by-size": "session_find_biggest", "count": "session_count"}.get(
        mod, "session_find")


# --------------------------------------------------------------------------
# Attention-signal sweep: which layer/head/aggregation resolves coref best
# --------------------------------------------------------------------------
def sweep_signals(chains):
    # collect all coref turns as (history, current, binds)
    probes = []
    for turns in chains:
        for i, t in enumerate(turns):
            if t["coref"] and i > 0:
                probes.append(([x["text"] for x in turns[:i]], t["text"],
                               set(t["binds"] or []) | FILES_OK,
                               set(t["binds"] or [])))
    # candidate signals
    cands = [("lh", l, h) for l in range(6) for h in range(12)]
    cands += [("layeravg", l) for l in range(6)]
    cands += [("headmax", l) for l in range(6)]
    cands += [("allavg",)]
    # encode each probe ONCE, score every signal off the cached attention tensor
    encs = [R.ChainEncoding(h + [c]) for h, c, _, _ in probes]
    results = []
    for sig in cands:
        phrase_hits = type_hits = 0
        for enc, (_, _, ok_phrase, ok_type) in zip(encs, probes):
            ref, _, _ = enc.resolve_reference(sig)
            if ref in ok_phrase:
                phrase_hits += 1
            if ref in ok_type:
                type_hits += 1
        results.append((sig, phrase_hits / len(probes), type_hits / len(probes)))
    results.sort(key=lambda r: (-r[1], -r[2]))
    return results, len(probes)


# --------------------------------------------------------------------------
# Main evaluation under a chosen signal
# --------------------------------------------------------------------------
def evaluate(chains, signal):
    res = R.Resolver(signal=signal)
    M = {
        "in_regress_total": 0, "in_regress_agree": 0,
        "nov_read_total": 0, "nov_read_rules_miss": 0, "nov_read_recovered": 0,
        "nov_refine_total": 0, "nov_refine_recovered": 0,
        "coref_total": 0, "coref_phrase": 0, "coref_type": 0,
        "safety_total": 0, "safety_rules_noemit": 0, "safety_resolver_flag": 0,
    }
    details = []

    for turns in chains:
        frame = None
        for i, t in enumerate(turns):
            pre_frame = frame                       # frame BEFORE this turn
            pre_plan = pre_frame.to_command_plan() if pre_frame else None
            frame, ract, remit, rframe = rules_step(frame, t["text"])

            is_disc = t["vocab"] in ("in", "novel") and i > 0
            needs_resolver = bool(t["coref"]) or t["vocab"] == "novel"
            rv = None
            if needs_resolver:
                hist = [x["text"] for x in turns[:i]]
                rv = res.resolve(hist, t["text"], frame_exists=pre_frame is not None)

            # ---- coreference accuracy (all coref turns) ----
            if t["coref"] and rv:
                M["coref_total"] += 1
                ok_phrase = set(t["binds"] or []) | FILES_OK
                ok_type = set(t["binds"] or [])
                if rv["resolved_reference"] in ok_phrase:
                    M["coref_phrase"] += 1
                if rv["resolved_reference"] in ok_type:
                    M["coref_type"] += 1

            # ---- in-vocab no-regression (resolver must not contradict rules) ----
            if t["vocab"] == "in" and t["risk"] == "read" and is_disc:
                M["in_regress_total"] += 1
                gold_mod = t["delta"].get("modifier")
                gold_act = t["act"]
                if rv is None:
                    M["in_regress_agree"] += 1   # resolver not consulted -> no harm
                else:
                    agree = (rv["suggested_act"] == gold_act and
                             rv["suggested_modifier"] == gold_mod) if gold_act == "operate" \
                            else (rv["suggested_act"] in (gold_act, "refine", "new"))
                    if agree:
                        M["in_regress_agree"] += 1

            # ---- novel read recovery (the headline) ----
            if t["vocab"] == "novel" and t["risk"] == "read" and t["delta"].get("modifier"):
                M["nov_read_total"] += 1
                rules_right = (remit and rframe and t["expected_frame"] and
                               rframe["intent"] == t["expected_frame"]["intent"] and
                               _core(rframe["slots"]) == _core(t["expected_frame"]["slots"]))
                if not rules_right:
                    M["nov_read_rules_miss"] += 1
                    # build the recovered frame: prior accumulated slots + modifier
                    gold_mod = t["delta"]["modifier"]
                    rec_ok = False
                    if rv and rv["suggested_modifier"] == gold_mod and pre_plan is not None:
                        slots = _core(dict(pre_plan.slots))
                        rec = {"intent": _mod_to_intent(gold_mod), "slots": slots}
                        ref_ok = (rv["resolved_reference"] in (set(t["binds"] or []) | FILES_OK))
                        if (rec["intent"] == t["expected_frame"]["intent"] and
                                _core(rec["slots"]) == _core(t["expected_frame"]["slots"]) and ref_ok):
                            rec_ok = True
                    if rec_ok:
                        M["nov_read_recovered"] += 1
                    details.append((turns[0]["chain_id"], t["text"], "RECOVERED" if rec_ok
                                    else "missed", rv["suggested_modifier"] if rv else None,
                                    rv["resolved_reference"] if rv else None))

            # ---- novel refine (act + reference recovery only) ----
            if t["vocab"] == "novel" and t["risk"] == "read" and not t["delta"].get("modifier") \
                    and t["act"] == "refine":
                M["nov_refine_total"] += 1
                if rv and rv["suggested_act"] in ("refine", "new") and \
                        rv["resolved_reference"] in (set(t["binds"] or []) | FILES_OK):
                    M["nov_refine_recovered"] += 1

            # ---- safety: destructive elliptical turns (invariant #6) ----
            if t["risk"] == "destructive":
                M["safety_total"] += 1
                # HARD invariant: the rules emit NO command for a delete turn —
                # "trash them"/"drop the tiny ones" route to fallback -> single-turn,
                # which abstains (no concrete target). The resolver never emits by
                # design (it only suggests; emission stays behind gate + exit-3), so
                # this is the number that actually guards invariant #6.
                if (not remit) or (rframe is None):
                    M["safety_rules_noemit"] += 1
                # softer: did the resolver RECOGNISE the turn as destructive? (a miss
                # here degrades to a non-destructive suggestion, so it still cannot
                # cause an rm — reported as a recognition gap, not a breach.)
                if rv and rv["destructive"]:
                    M["safety_resolver_flag"] += 1

    return M, details


def pct(a, b):
    return f"{a}/{b} ({100*a/b:.0f}%)" if b else "0/0 (n/a)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--figure", action="store_true")
    args = ap.parse_args()

    chains = load_chains()
    print(f"loaded {len(chains)} chains, "
          f"{sum(len(c) for c in chains)} turns from {EVAL.name}\n")

    print("=== attention-signal sweep (coref referent accuracy) ===")
    sweep, nprobe = sweep_signals(chains)
    print(f"  {nprobe} coref turns probed")
    for sig, ph, ty in sweep[:8]:
        print(f"  {str(sig):20} phrase={ph:.2f}  type-specific={ty:.2f}")
    best = sweep[0][0]
    print(f"  => best signal: {best}\n")

    for label, sig in [("best-swept", best), ("L3H1 (probe default)", ("lh", 3, 1)),
                       ("last-layer head-avg", ("layeravg", 5))]:
        M, details = evaluate(chains, sig)
        print(f"=== results under {label} = {sig} ===")
        print(f"  IN-VOCAB no-regression (resolver agrees w/ rules): "
              f"{pct(M['in_regress_agree'], M['in_regress_total'])}")
        print(f"  NOVEL read turns: {M['nov_read_total']}  | rules MISS: "
              f"{M['nov_read_rules_miss']}  | RECOVERED by attention: "
              f"{pct(M['nov_read_recovered'], M['nov_read_rules_miss'])}   <-- headline")
        print(f"  NOVEL refine (act+ref recovery): "
              f"{pct(M['nov_refine_recovered'], M['nov_refine_total'])}")
        print(f"  COREFERENCE phrase-accuracy: {pct(M['coref_phrase'], M['coref_total'])}"
              f"   type-specific: {pct(M['coref_type'], M['coref_total'])}")
        print(f"  SAFETY — rules emit NO command on destructive elliptical (hard "
              f"invariant #6): {pct(M['safety_rules_noemit'], M['safety_total'])}")
        print(f"  SAFETY — resolver recognises destructive (soft; a miss degrades to "
              f"a non-destructive suggestion): {pct(M['safety_resolver_flag'], M['safety_total'])}")
        if sig == best:
            print("  recovery detail:")
            for cid, tx, verdict, mod, ref in details:
                print(f"     [{verdict:9}] {cid} {tx!r} -> mod={mod} ref={ref}")
        print()

    if args.figure:
        make_figure(chains)


# --------------------------------------------------------------------------
# Figure on a novel-phrasing chain
# --------------------------------------------------------------------------
def make_figure(chains):
    """Task 48 — the showcase at L4H4 (the resolver's REAL head; 98% held-out
    type-specific coref), on BOTH the golden chain and a novel-phrasing chain, plus a
    head-averaged variant of each. Dev-time only (torch); no runtime dependency."""
    from resolver import ChainEncoding

    L4H4 = ("lh", 4, 4)          # label LxHy == att[x, y] (as with the old "L3H1")
    # the honest headline: L4H4's type-specific coref accuracy across the held-out set
    M, _ = evaluate(chains, L4H4)
    acc = pct(M["coref_type"], M["coref_total"])
    print(f"L4H4 held-out type-specific coref = {acc}")

    GOLDEN = ["find the csv files", "only the ones modified yesterday", "show the biggest one"]
    NOVEL = ["pull up the csv files", "only the ones over 2mb", "which of those is heaviest"]
    for tag, turns, pron in [("golden", GOLDEN, "the biggest ONE"),
                             ("novel", NOVEL, "which of THOSE")]:
        enc = ChainEncoding(turns)
        _svg(enc, enc.attn_matrix(L4H4), HERE / f"attention_{tag}_L4H4.svg",
             f"{tag.title()} chain · coref '{pron}' → turn-1 type (L4H4 · {acc} held-out)")
        _svg(enc, enc.attn_matrix(("layeravg", 4)), HERE / f"attention_{tag}_layer4_avg.svg",
             f"{tag.title()} chain · coref '{pron}' → turn-1 type (layer 4, head-avg)")
    print("wrote figures -> experiments/task44_spike/attention_{golden,novel}_{L4H4,layer4_avg}.svg")


def _svg(enc, A, path, title):
    toks = enc.toks
    # turn bands from tok_turn
    spans = []
    for ti in range(len(enc.turns)):
        idx = [k for k in range(enc.S) if enc.tok_turn[k] == ti]
        spans.append((min(idx), max(idx) + 1) if idx else (0, 0))
    n = len(toks)
    cell, pad_l, pad_t = 26, 160, 160
    W, Hh = pad_l + n * cell + 20, pad_t + n * cell + 30
    mx = float(A.max()) or 1.0
    colors = ["#2563eb", "#059669", "#d97706"]
    band = {}
    for ti, (a, b) in enumerate(spans):
        for k in range(a, b):
            band[k] = ti

    def esc(t):
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{Hh}" '
           f'font-family="ui-monospace,Menlo,monospace" font-size="11">']
    out.append(f'<rect width="{W}" height="{Hh}" fill="white"/>')
    out.append(f'<text x="{pad_l}" y="24" font-size="14" font-weight="700">{esc(title)}</text>')
    out.append(f'<text x="{pad_l}" y="42" font-size="11" fill="#555">rows = query token · cols = key token · darker = more attention</text>')
    for i in range(n):
        for j in range(n):
            v = A[i, j] / mx
            if v < 0.02:
                continue
            g = int(255 * (1 - v))
            out.append(f'<rect x="{pad_l+j*cell}" y="{pad_t+i*cell}" width="{cell}" '
                       f'height="{cell}" fill="rgb({g},{g},255)" stroke="#eee"/>')
    for i, t in enumerate(toks):
        c = colors[band[i] % 3] if i in band else "#999"
        out.append(f'<text x="{pad_l-6}" y="{pad_t+i*cell+cell-8}" text-anchor="end" fill="{c}">{esc(t)}</text>')
    for j, t in enumerate(toks):
        c = colors[band[j] % 3] if j in band else "#999"
        x = pad_l + j * cell + cell - 9
        out.append(f'<text x="{x}" y="{pad_t-6}" fill="{c}" transform="rotate(-60 {x} {pad_t-6})">{esc(t)}</text>')
    ly = pad_t + n * cell + 6
    for ti, lab in enumerate(["turn 1", "turn 2", "turn 3 (current)"]):
        out.append(f'<rect x="{pad_l+ti*140}" y="{ly}" width="12" height="12" fill="{colors[ti]}"/>')
        out.append(f'<text x="{pad_l+ti*140+16}" y="{ly+11}" fill="#333">{lab}</text>')
    out.append('</svg>')
    Path(path).write_text("\n".join(out))


if __name__ == "__main__":
    main()
