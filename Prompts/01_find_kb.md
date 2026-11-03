# Task 01 — `find` knowledge base spec + loader

Read `kb/taxonomy.yaml`, the `file_discovery` domain. Follow all invariants
in `CLAUDE.md`.

## Build

### 1. `kb/commands/find.yaml`

Describe `find` as capability `search_files` with four intents:
`find_by_size`, `find_by_time`, `find_by_name`, `find_by_type`.

For each intent provide:
- `base_argv`: a list of strings, e.g. `["find", "{path}", "-type", "f"]`
- `optional_args`: a map of slot -> argv fragment (a list), e.g.
  - `ext`  -> `["-name", "*.{ext}"]`
  - `size` -> `["-size", "+{bytes}c"]`
  - `time` -> `["-mtime", "-{days}"]`
  - `type` -> `["-type", "{ftype}"]`  (f or d)
- `risk_ops`: `[read]`

Rules:
- Every `base_argv` and every `optional_args` fragment is a LIST, never a
  single string.
- A `{placeholder}` occupies exactly one list element
  (`"*.{ext}"` is fine; `"-name *.{ext}"` as one element is NOT).

### 2. `src/linuxbuddy/kb.py`

- `load_kb(path="kb/commands")` reads all command YAMLs.
- `get_capability(name)` returns the capability dict, raising `KeyError` if
  absent.
- Validate on load: reject a spec where any argv element is not a string, or
  where a capability has no intents.

### 3. `tests/test_kb.py`

- Loads `find.yaml`.
- Asserts the four intents are present.
- Asserts every `base_argv` is a list of strings.
- Asserts `get_capability("search_files")` works and
  `get_capability("nope")` raises `KeyError`.

## Done when

- `pytest tests/test_kb.py` passes.
- `python -c "from linuxbuddy.kb import get_capability; print(get_capability('search_files'))"`
  prints the capability.
