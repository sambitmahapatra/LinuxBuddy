"""Task 43 — THROWAWAY feasibility probe for attention-based context retention.

NOT wired into production. Run in the ML env only:
    .venv-ml/bin/python -I experiments/task43_attention/probe.py

De-risks three assumptions behind the attention_context_proposal:
  A. Does CONTEXT actually help intent selection, zero-shot? Rank the fine-tuned
     encoder's intent-description matches for a bare elliptical turn vs the same
     turn prefixed with its history.
  B. Is there real CROSS-TURN attention? On the canonical 3-turn chain, measure
     how much of turn-3's attention mass lands on turn-1/2 tokens.
  C. Produce a sample attention-map FIGURE (dependency-free SVG) for the proposal.

Everything here is read-only w.r.t. production: it loads the already-trained
torch model (models/ft-minilm-l6) and writes only into this experiments dir.
"""
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer, util

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
HERE = Path(__file__).resolve().parent

MODEL_DIR = str(REPO / "models" / "ft-minilm-l6")

CHAIN = ["find the csv files",
         "only the ones modified yesterday",
         "show the biggest one"]


def load():
    m = SentenceTransformer(MODEL_DIR)
    # eager attention so output_attentions works (SDPA can't return weights)
    m[0].auto_model.config.attn_implementation = "eager"
    import transformers
    tr = transformers.AutoModel.from_pretrained(
        MODEL_DIR, attn_implementation="eager")
    tr.eval()
    return m, tr, m.tokenizer


def probe_a(m):
    """Context vs no-context intent ranking (zero-shot, fine-tuned space)."""
    from linuxbuddy.ml.zeroshot import load_descriptions
    descs = load_descriptions()
    intents = [i for i in descs if descs[i] and descs[i].get("description")]
    dvecs = m.encode([descs[i]["description"] for i in intents],
                     normalize_embeddings=True)

    def rank(q, k=5):
        qv = m.encode(q, normalize_embeddings=True)
        sims = util.cos_sim(qv, dvecs)[0].numpy()
        order = np.argsort(-sims)[:k]
        return [(intents[j], round(float(sims[j]), 3)) for j in order]

    print("\n=== PROBE A: does context change the intent match? ===")
    cases = [
        ("show the biggest one", "find the csv files. only the ones modified yesterday. show the biggest one"),
        ("only the ones modified yesterday", "find the csv files. only the ones modified yesterday"),
        ("count them", "find the python files. count them"),
        ("delete them", "find the log files. delete them"),
    ]
    for bare, ctx in cases:
        print(f"\n  bare : {bare!r}")
        for it, s in rank(bare):
            print(f"         {s:+.3f}  {it}")
        print(f"  +ctx : {ctx!r}")
        for it, s in rank(ctx):
            print(f"         {s:+.3f}  {it}")


def _attn_for(tr, tok, text):
    import torch
    enc = tok(text, return_tensors="pt")
    with torch.no_grad():
        out = tr(**enc, output_attentions=True)
    toks = tok.convert_ids_to_tokens(enc["input_ids"][0])
    # (layers, heads, seq, seq)
    att = np.stack([a[0].numpy() for a in out.attentions])
    return toks, att


def _turn_spans(tok, turns):
    """Token index spans for each turn in the joined sequence (for cross-turn mass)."""
    joined = ". ".join(turns)
    ids = tok(joined, return_tensors="pt")["input_ids"][0]
    toks = tok.convert_ids_to_tokens(ids)
    # map by re-tokenizing each turn's words; simplest robust approach: walk tokens
    spans, cur, ti = [], [], 0
    sub = [tok.convert_ids_to_tokens(tok(t, add_special_tokens=False)["input_ids"])
           for t in turns]
    flat = [(i, t) for i, t in enumerate(toks)]
    pos = 1  # skip [CLS]
    for s in sub:
        start = pos
        end = pos + len(s)
        spans.append((start, end))
        pos = end
        # skip the ". " separator tokens between turns
        while pos < len(toks) and toks[pos] in (".", "[SEP]"):
            pos += 1
    return toks, spans, joined


def probe_b(tr, tok):
    print("\n=== PROBE B: cross-turn attention mass (turn-3 → turns 1/2) ===")
    toks, spans, joined = _turn_spans(tok, CHAIN)
    _, att = _attn_for(tr, tok, joined)
    L, H, S, _ = att.shape
    t3 = spans[2]
    prior = list(range(spans[0][0], spans[1][1]))  # turn1+turn2 token indices
    best = (-1, -1, -1.0)
    rows = []
    for l in range(L):
        for h in range(H):
            A = att[l, h]
            # mass from turn-3 tokens onto prior-turn tokens (exclude self/CLS/SEP)
            mass = A[t3[0]:t3[1]][:, prior].sum() / max(1, (t3[1] - t3[0]))
            rows.append((l, h, mass))
            if mass > best[2]:
                best = (l, h, mass)
    rows.sort(key=lambda r: -r[2])
    print(f"  joined: {joined!r}")
    print(f"  turn spans (tok idx): {spans}")
    print(f"  top cross-turn (layer,head,mass-onto-prior):")
    for l, h, mss in rows[:6]:
        print(f"     L{l} H{h}  mass={mss:.3f}")
    print(f"  => strongest cross-turn head: L{best[0]} H{best[1]} (mass {best[2]:.3f})")
    return toks, spans, att, best


def _svg_heatmap(toks, att_lh, spans, path, title):
    """Hand-rolled SVG heatmap of one (layer,head) attention matrix. No deps."""
    n = len(toks)
    cell = 26
    pad_l, pad_t = 150, 150
    W = pad_l + n * cell + 20
    H = pad_t + n * cell + 20
    mx = float(att_lh.max()) or 1.0

    def esc(t):
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # turn-color bands for axis labels
    band = {}
    for ti, (a, b) in enumerate(spans):
        for k in range(a, b):
            band[k] = ti
    colors = ["#2563eb", "#059669", "#d97706"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'font-family="ui-monospace,Menlo,monospace" font-size="11">']
    out.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    out.append(f'<text x="{pad_l}" y="24" font-size="15" font-weight="700">{esc(title)}</text>')
    out.append(f'<text x="{pad_l}" y="42" font-size="11" fill="#555">rows = query token (turn 3 attends) · cols = key token (attended to) · darker = more attention</text>')
    # cells
    for i in range(n):
        for j in range(n):
            v = att_lh[i, j] / mx
            if v < 0.02:
                continue
            g = int(255 * (1 - v))
            # blue-ish ramp
            fill = f"rgb({g},{g},255)" if v > 0 else "white"
            x = pad_l + j * cell
            y = pad_t + i * cell
            out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{fill}" stroke="#eee"/>')
    # row labels (query tokens)
    for i, t in enumerate(toks):
        c = colors[band[i]] if i in band else "#999"
        y = pad_t + i * cell + cell - 8
        out.append(f'<text x="{pad_l - 6}" y="{y}" text-anchor="end" fill="{c}">{esc(t)}</text>')
    # col labels (key tokens), rotated
    for j, t in enumerate(toks):
        c = colors[band[j]] if j in band else "#999"
        x = pad_l + j * cell + cell - 9
        out.append(f'<text x="{x}" y="{pad_t - 6}" fill="{c}" transform="rotate(-60 {x} {pad_t - 6})">{esc(t)}</text>')
    # legend
    ly = pad_t + n * cell + 4
    for ti, lab in enumerate(["turn 1", "turn 2", "turn 3"]):
        out.append(f'<rect x="{pad_l + ti*90}" y="{ly}" width="12" height="12" fill="{colors[ti]}"/>')
        out.append(f'<text x="{pad_l + ti*90 + 16}" y="{ly+11}" fill="#333">{lab}</text>')
    out.append('</svg>')
    Path(path).write_text("\n".join(out))
    print(f"  wrote figure -> {path}")


def probe_c(toks, spans, att, best):
    print("\n=== PROBE C: attention-map figure ===")
    l, h, _ = best
    _svg_heatmap(toks, att[l, h], spans,
                 HERE / "attention_map.svg",
                 f"Cross-turn attention  (fine-tuned MiniLM, layer {l} head {h})")
    # also the head-averaged last layer, often cleaner
    _svg_heatmap(toks, att[-1].mean(0), spans,
                 HERE / "attention_map_lastlayer_avg.svg",
                 "Cross-turn attention  (last layer, head-averaged)")


def main():
    m, tr, tok = load()
    probe_a(m)
    toks, spans, att, best = probe_b(tr, tok)
    probe_c(toks, spans, att, best)
    print("\nDONE.")


if __name__ == "__main__":
    main()
