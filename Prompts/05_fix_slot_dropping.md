# Task 05 — fix two bugs found by real use

Read `CLAUDE.md`. These are reproductions from actual use, not hypotheticals.

## Bug 1 — silent slot dropping produces match-everything

`lb show me the biggest files here` -> `find . -type f`

"biggest" was dropped and the command now matches every file. This is the
dangerous case: looks like it worked, floods the user, ignored the request.

Fix the abstention gate: **if the chosen intent is missing its defining
slot, abstain — never emit a degenerate command.**
- `find_by_size` with no `size_bytes` -> abstain.
- `find_by_time` with no `days` -> abstain.
- `find_by_name` with no `pattern` -> abstain.
- A bare `find . -type f` (no filter at all) must never be emitted unless
  the user explicitly asked to list all files.

Superlatives with no number ("biggest", "largest", "oldest", "newest")
should abstain for now with a message hinting what's missing, e.g.
`LinuxBuddy: how big? try "over 100MB"`. (A real sort-by-size intent is
later work, not this task.)

## Bug 2 — plural extensions dropped

`lb find csvs bigger than 2 gigs` -> `find . -type f -size +2147483648c`

"csvs" (plural) was not recognized as the csv extension, so `-name` is
missing. The size parsed fine.

Fix: normalize plural/possessive file-type words to the extension before
slot extraction. `csvs->csv`, `logs->log`, `pys->py`, `jsons->json`,
`notebooks->ipynb`, `scripts->sh`, `images->` (skip, ambiguous).
Keep it a small explicit map plus a trailing-s fallback, not a stemmer.

## Tests

Add to `tests/test_nlu.py`:
- `"show me the biggest files here"` -> None (abstain)
- `"largest files"` -> None
- `"csvs bigger than 2 gigs"` -> by_size, ext=csv, size_bytes=2147483648
- `"logs from today"` -> by_time, ext=log, days=1
- regression: the four originally-passing cases still pass.

## Done when

`pytest` passes, and in a real shell:
- `lb show me the biggest files here` prints the abstain hint, exit 1
- `lb csvs bigger than 2 gigs` includes `-name '*.csv'`
