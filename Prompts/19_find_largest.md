# Task 19 — find_largest intent (the "biggest files" gap)

Read `CLAUDE.md`. From dogfooding: `lb show me the biggest files here` and
`lb top 2 in descending order` both abstained. "Biggest/largest/top N files" is
one of the most common things a user asks and it currently has no intent. Build it.

## The intent

Add `find_largest` to the file_discovery domain (or wherever routing is
cleanest). Read-only. It needs NO size threshold — that's the whole point;
"biggest" means "sort by size, show the top."

| Example | Command |
|---|---|
| "show me the biggest files here" | `find {path} -type f -printf '%s\t%p\n' \| sort -rn \| head -n {count}` |
| "largest files in the data folder" | (path = data) |
| "top 2 files by size" | (count = 2) |
| "what's taking up the most space" | same |

- `path` defaults to `.`; `count` defaults to 10.
- "top N" / "biggest N" / "N largest" → count = N.
- Uses the existing pipe composition (find | sort | head — a 3-stage pipe;
  extend the 2-stage composition to N stages if needed, keeping each stage
  round-tripped and the `|` compiler-inserted).
- Alternative single-tool form if the 3-stage pipe is awkward:
  `du -ah {path} | sort -rh | head -n {count}` (sizes of files AND dirs). Pick
  whichever is cleaner; document the choice. The `find -printf` form is
  files-only and exact; `du` includes directories.

## Routing / abstain fix

"biggest/largest/top N files|data|space" must now route to `find_largest`
instead of abstaining. The old abstain-with-hint ("how big? try over 100MB")
should only fire when the user genuinely gives a size-less `find_by_size`
phrasing that ISN'T a superlative — and honestly, superlatives are exactly
find_largest, so most of those stop abstaining. Check: `lb show me the biggest
files here` must now emit a command, not a hint.

## Tests (`tests/test_find_largest.py`)

| input | expect |
|---|---|
| "show me the biggest files here" | find_largest, path=., count=10 |
| "largest files in data" | find_largest, path=data |
| "top 2 files by size" | find_largest, count=2 |
| "what's taking up the most space" | find_largest |
| "files over 100mb" | still find_by_size (threshold given — unchanged) |

Plus the N-stage pipe round-trip test, and a regression run.

## Done when

`pytest` passes (incl. regression). In the maze:
`lb show me the biggest files here` → emits the find|sort|head pipe and, run,
lists huge_dataset.csv at the top. `lb top 3 files by size` → count=3.
`lb files over 100mb` still works unchanged.
