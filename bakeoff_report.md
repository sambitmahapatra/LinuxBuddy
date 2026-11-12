# Base-Model Bake-Off — Task 38 Part A

*Zero-shot, NO fine-tuning, CPU. Same `eval_zeroshot` harness across 5 pretrained encoders. Each model uses its documented input convention (e5 `query:`/`passage:`, bge query instruction, gte/MiniLM none) so the comparison is fair; embeddings normalized, cosine, T\* re-tuned per model.*

**Primary goal:** nonsense FP < 15% at gap recovery ≥ 80%. Operating point per model = the (T, margin) that reaches the gap floor with the lowest nonsense FP (tie: val top-1).

| model | best mode | T\* | margin | gap rec. | nonsense FP | val top-1 | val top-3 | meets floor |
|---|---|---|---|---|---|---|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` ⭐ | desc | 0.275 | 0.0 | 85% | 31% | 58% | 77% | yes |
| `sentence-transformers/all-MiniLM-L12-v2` | desc | 0.275 | 0.0 | 85% | 34% | 62% | 79% | yes |
| `BAAI/bge-small-en-v1.5` | desc | 0.625 | 0.0 | 81% | 34% | 60% | 85% | yes |
| `thenlper/gte-small` | desc | 0.2 | 0.0 | 89% | 100% | 60% | 79% | yes |
| `intfloat/e5-small-v2` | desc+ex | 0.2 | 0.0 | 67% | 100% | 56% | 79% | NO |

**Winner: `sentence-transformers/all-MiniLM-L6-v2`** (mode `desc`) — operating point T\*=0.275, margin≥0.0: gap recovery 85%, nonsense FP 31%, val top-1 58% / top-3 77%.

> **No base model clears the bar zero-shot** (best feasible FP = 31% at gap 85%). Fine-tuning (Part B) is warranted. The winner is the best *starting point* for the contrastive fine-tune.

