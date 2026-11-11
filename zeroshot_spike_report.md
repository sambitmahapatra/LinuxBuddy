# Zero-Shot Bi-Encoder Spike — Report

*Task 37 — measurement spike, NO fine-tuning, CPU only. Model: `sentence-transformers/all-MiniLM-L6-v2` (local, ~22M params).*

## Setup
- Model: all-MiniLM-L6-v2 (CPU torch). Descriptions: `kb/intent_descriptions.yaml` (all 85 intents).
- Description strategy compared: `desc` (val top1 58%, gap@T* 85%), `desc+ex` (val top1 65%, gap@T* 59%)
- **Best strategy: `desc`**; operating point **T\* = 0.275** (chosen to maximize gap recovery while keeping nonsense false-positives ≤ 15%).

## Results (best strategy)
- **Val (ceiling): top-1 58%, top-3 77%** (n=48 covered rows)
- **Gap set: recovered 23/27 at T\*** (85%)  ← the headline number
- **Nonsense abstain: 69% correct (false-positive 31%)** at T\* (n=35)

### Threshold sweep (best strategy)
| T | gap recovery | val top-1 (≥T) | nonsense abstained | nonsense FP |
|---|---|---|---|---|
| 0.2 | 85% | 58% | 37% | 63% |
| 0.225 | 85% | 58% | 57% | 43% |
| 0.25 | 85% | 58% | 63% | 37% |
| 0.275 | 85% | 58% | 69% | 31%  **← T\*** |
| 0.3 | 81% | 58% | 69% | 31% |
| 0.325 | 78% | 56% | 69% | 31% |
| 0.35 | 74% | 56% | 71% | 29% |
| 0.375 | 67% | 52% | 74% | 26% |
| 0.4 | 59% | 48% | 80% | 20% |
| 0.425 | 52% | 44% | 80% | 20% |
| 0.45 | 44% | 42% | 86% | 14% |
| 0.475 | 41% | 42% | 86% | 14% |
| 0.5 | 30% | 40% | 89% | 11% |
| 0.525 | 30% | 33% | 91% | 9% |
| 0.55 | 26% | 29% | 94% | 6% |
| 0.575 | 22% | 27% | 94% | 6% |
| 0.6 | 19% | 27% | 97% | 3% |
| 0.625 | 19% | 25% | 97% | 3% |
| 0.65 | 15% | 25% | 97% | 3% |

T\* chosen at the knee (max gap_recovery × nonsense_abstain), not an arbitrary FP cutoff. The curve shows the real tension: nonsense is not cleanly separable by absolute cosine alone — FP only falls below ~15% near T=0.55, which starts costing gap recovery.

### Margin as a second abstain lever (at T\*=0.275)
Require top1−top2 margin ≥ m as well; does it trim nonsense FP without losing gaps?

| margin ≥ | gap recovery | val top-1 | nonsense abstained | nonsense FP |
|---|---|---|---|---|
| 0.0 | 85% | 58% | 69% | 31%  **← best** |
| 0.02 | 74% | 52% | 71% | 29% |
| 0.04 | 63% | 42% | 74% | 26% |
| 0.06 | 41% | 40% | 77% | 23% |
| 0.08 | 33% | 35% | 83% | 17% |
| 0.1 | 30% | 27% | 83% | 17% |

**Recommended operating point: T\*=0.275, margin≥0.0** → gap recovery 85%, nonsense abstain 69% (FP 31%), val top-1 58%.

## Verdict

**NEEDS FINE-TUNING** — the embedding space is roughly right — the gap set reaches 85% top-1 recovery and val top-3 is 77% — but two things block wiring it as-is: (1) top-1 is soft (val 58%), with errors concentrated between NEIGHBORING intents (find_by_type vs run_script/list_all, make_dir vs setup_project, cd_parent vs go_back, count_matches vs count_lines); and (2) nonsense is not separable by an absolute cosine threshold (no T gives both strong recovery and <15% false-positive, and the top1-top2 margin does not help). Both are exactly what a contrastive fine-tune on the Task-36 labeled pairs targets — pulling neighbours and nonsense apart. Proceed to fine-tuning next; keep kb/intent_descriptions.yaml as the reusable anchor set and re-use this harness to measure the lift.

## Which gap phrasings fail, and why

| utterance | true intent | predicted top-1 (score) | rank of true |
|---|---|---|---|
| where are the python scripts | find_by_type | run_script (0.6446) | top-3 |
| got any spreadsheets? | find_by_type | show_stat (0.2553) | top-2 |
| find all the files here | find_by_type | list_all (0.6317) | top-2 |
| set up a folder called reports | make_dir | setup_project (0.6709) | top-2 |

## Val: worst performers (rank of true label)

| utterance | true | top-1 (score) | rank of true |
|---|---|---|---|
| take me to project | goto | setup_project (0.2858) | top-32 |
| anything readable by everyone | find_perms | check_readable (0.3212) | top-25 |
| bundle the data folder | create_archive | setup_project (0.5202) | top-12 |
| which lines mention warning | search_in_file | check_syntax (0.2512) | top-11 |
| take me back | cd_parent | go_back (0.2985) | top-9 |
| what's the windows path for this folder | path_to_windows | list_all (0.5137) | top-9 |
| when was the log last modified | show_stat | preview_tail (0.503) | top-8 |
| how many errors in the log | count_matches | count_lines (0.2785) | top-8 |
| find a file called config.yaml | find_by_name | find_by_type (0.4167) | top-5 |
| only i should be able to read the secrets file | set_permission | go_home (0.3355) | top-5 |

## The 27 zero-data intents

All 85 intents (including the 27 with no labeled data) have descriptions, so the bi-encoder can rank them with zero examples — 85 also carry example anchors. Whether that is *acceptable* can only be judged once any appear in evaluation; none of the 27 appear in the 55-row val set, so they are not directly measured here. Recommendation: keep them description-served for now and let the Phase-1 confusion matrix (on a broader eval) decide which need the targeted collection pass.

