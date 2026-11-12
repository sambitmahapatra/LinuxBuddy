# Dogfood-500 — Diversity Self-Audit (Task 41)

*538 single-turn scenarios + 22 multi-turn chains (49 turns) = **587** judged rows.*

## Leakage check vs `data/train.jsonl`

- Utterances checked: 587
- **Duplicates of a train row: 0** ✅ leakage-clean

## Intent coverage (all 85 KB intents)

- Intents hit: **85/85** (single-turn 82/85; session_find/count/find_biggest covered via the 22 multi-turn chains).
- Zero-data intents hit: **27/27**
- Floor (≥3 each, session_* exempted as chain-only): **all intents meet the floor** ✅

## Register spread

- imperative: 257 (48%)
- question: 166 (31%)
- indirect: 60 (11%)
- polite: 55 (10%)

## Vocabulary / synonym spread (top 25)

- distinct verbs/synonyms: **355**
- find=39, ood2=25, definite-ref=16, nonsense=15, vague=12, bare=6, delete=5, out-of-scope=5, show=4, locate=4, is there=4, remove=4, deep=4, how many=3, count=3, empty=3, look for=3, verify=3, typo=3, make=3, where=2, list=2, changed=2, touched=2, edited=2

## Compositional complexity (constraint count)

- 0 constraints: 504
- 1 constraints: 10
- 2 constraints: 17
- 3 constraints: 7

## Reference style

- none: 506
- literal: 16
- definite: 13
- superlative: 3

## Risk / location

- read: 377
- destructive: 92
- abstain: 57
- refused: 12

cwd: maze=522, outside=12, deep=4

- Out-of-domain negatives (abstain): 57 (11%)

## Template-domination guard

- Distinct 4-word prefixes: 520
- Most common prefixes: 'what changed in the'×3, 'find files bigger than'×2, 'find files modified in'×2, 'count the lines in'×2, 'what's the size of'×2
- ✅ no single template exceeds ~5%
