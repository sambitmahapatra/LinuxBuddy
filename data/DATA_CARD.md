# LinuxBuddy v2 — Phase-0 Data Card (Task 36)

Deterministic, offline, stdlib-only corpus for the Phase-1 intent encoder. No torch / transformers / LLM / paraphrase model. Reproducible with fixed seed **20261111** (`python -I -m linuxbuddy.ml.make_dataset`).

## Label space (frozen, from the KB)
- Intents: **85** (exact KB `frame.intent` ids — see `label_space.json`)
- Dialogue acts: new, refine, operate, reset, fallback
- Special: `_ABSTAIN` (a learned class)
- Sweep→KB reconciliation: `sweep_intent_map.json` (behavior-verified; drift guard fires on any unmapped sweep intent).

## Single-turn
- Raw (un-augmented): **204** (`_ABSTAIN` 35 = 17.2%)
- Train: **688** (of which 539 augmented; augmentation ×4.62 on train) · Val: **55**
- `_ABSTAIN` share — train 84/688 (12.2%), val 7/55 (12.7%)
- By source (raw): {'sweep': 147, 'stress_gap': 27, 'stress_abstain': 12, 'hand_abstain': 18}

### Per-intent counts (train / val)
| intent | train | val |
|---|---|---|
| _ABSTAIN | 84 | 7 |
| cd_parent | 25 | 1 |
| check_installed | 10 | 1 |
| check_package | 10 | 1 |
| check_syntax | 5 | 0 |
| copy_file | 20 | 1 |
| copy_to_clipboard | 5 | 0 |
| count_files | 5 | 1 |
| count_lines | 5 | 1 |
| count_matches | 5 | 1 |
| create_archive | 15 | 1 |
| date_time | 5 | 1 |
| delete_file | 30 | 2 |
| detect_type | 5 | 0 |
| disk_free | 10 | 1 |
| disk_usage | 5 | 1 |
| env_var | 10 | 1 |
| extract_tar | 5 | 0 |
| extract_zip | 5 | 0 |
| find_by_name | 10 | 1 |
| find_by_size | 10 | 1 |
| find_by_time | 10 | 1 |
| find_by_type | 45 | 2 |
| find_empty | 5 | 1 |
| find_largest | 20 | 1 |
| find_perms | 5 | 1 |
| find_recent | 15 | 1 |
| go_back | 4 | 0 |
| go_home | 10 | 1 |
| goto | 40 | 2 |
| goto_cdrive | 5 | 1 |
| kill_pid | 5 | 0 |
| kill_process | 5 | 1 |
| list_all | 10 | 1 |
| list_archive | 5 | 1 |
| list_processes | 20 | 1 |
| make_dir | 10 | 1 |
| make_executable | 10 | 1 |
| move_file | 5 | 1 |
| open_explorer | 5 | 1 |
| open_vscode | 5 | 0 |
| path_to_windows | 5 | 1 |
| pip_list | 5 | 1 |
| preview_head | 30 | 1 |
| preview_tail | 5 | 1 |
| process_on_port | 15 | 1 |
| run_script | 5 | 0 |
| search_in_file | 15 | 1 |
| search_recursive | 5 | 1 |
| set_permission | 10 | 1 |
| show_history | 5 | 0 |
| show_permissions | 10 | 1 |
| show_stat | 15 | 1 |
| sort_lines | 5 | 0 |
| top_by_cpu | 5 | 0 |
| top_by_mem | 5 | 0 |
| unique_lines | 5 | 1 |
| where_am_i | 10 | 1 |
| where_python | 10 | 1 |

### Zero-coverage intents (NO single-turn data at all)
27 of 85 KB intents have no single-turn example in this corpus — the encoder cannot learn them from single-turn data and will never predict them. The rules still handle these; the encoder simply won't be a fallback for them until the corpus grows. (session_* are exercised by the multi-turn set instead.)

> `archive_integrity`, `archive_size`, `cdrive_space`, `check_exists`, `check_readable`, `check_writable`, `clear_screen`, `compress_file`, `extract_archive`, `find_process`, `find_smallest`, `goto_home`, `home_space`, `list_listening`, `list_zip`, `path_to_linux`, `python_version`, `remove_executable`, `session_count`, `session_find`, `session_find_biggest`, `setup_project`, `show_owner`, `show_pid`, `show_size`, `which_shell`, `who_am_i`

### Under-represented intents (<3 raw train seeds — confusion-matrix watchlist)
- check_installed: only 2 train example(s)
- check_package: only 2 train example(s)
- check_syntax: only 1 example (train-only, none in val)
- copy_to_clipboard: only 1 example (train-only, none in val)
- count_files: only 1 train example(s)
- count_lines: only 1 train example(s)
- count_matches: only 1 train example(s)
- date_time: only 1 train example(s)
- detect_type: only 1 example (train-only, none in val)
- disk_free: only 2 train example(s)
- disk_usage: only 1 train example(s)
- env_var: only 2 train example(s)
- extract_tar: only 1 example (train-only, none in val)
- extract_zip: only 1 example (train-only, none in val)
- find_by_name: only 2 train example(s)
- find_by_size: only 2 train example(s)
- find_by_time: only 2 train example(s)
- find_empty: only 1 train example(s)
- find_perms: only 1 train example(s)
- go_back: only 1 example (train-only, none in val)
- go_home: only 2 train example(s)
- goto_cdrive: only 1 train example(s)
- kill_pid: only 1 example (train-only, none in val)
- kill_process: only 1 train example(s)
- list_all: only 2 train example(s)
- list_archive: only 1 train example(s)
- make_dir: only 2 train example(s)
- make_executable: only 2 train example(s)
- move_file: only 1 train example(s)
- open_explorer: only 1 train example(s)
- open_vscode: only 1 example (train-only, none in val)
- path_to_windows: only 1 train example(s)
- pip_list: only 1 train example(s)
- preview_tail: only 1 train example(s)
- run_script: only 1 example (train-only, none in val)
- search_recursive: only 1 train example(s)
- set_permission: only 2 train example(s)
- show_history: only 1 example (train-only, none in val)
- show_permissions: only 2 train example(s)
- sort_lines: only 1 example (train-only, none in val)
- top_by_cpu: only 1 example (train-only, none in val)
- top_by_mem: only 1 example (train-only, none in val)
- unique_lines: only 1 train example(s)
- where_am_i: only 2 train example(s)
- where_python: only 2 train example(s)

## Multi-turn
- Raw turns: **49** across 20 chains
- Train turns: **40** · Val turns: **9** (whole chains; never split across the boundary)
- By dialogue_act (raw): {'new': 23, 'refine': 7, 'operate': 9, 'reset': 6, 'fallback': 4}
  - **Imbalanced by design** (new ≫ refine/operate ≫ reset/fallback); Phase-2 should weight the loss.

## Augmentation (train-only)
- Transforms: synonym substitution, filler/politeness injection, word dropout, filename/extension swap (never on `_ABSTAIN`). Bank: `data/synonyms.json`.
- Cap per seed: positives ≤4, abstain ≤2 (filler/dropout only).
- **Train-only** and **group-level**: augmentation is applied after the split and only to train seeds, so no variant of a val example leaks into train.

## No-leakage guarantee
- Single-turn split is by `seed_id` group; multi-turn by whole `chain_id`. `tests/test_data.py` asserts the train/val id intersection is empty.

