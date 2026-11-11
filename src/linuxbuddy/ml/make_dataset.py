"""Task 36 — v2 Phase 0 training-data generator (DATA ONLY, reproducible).

Builds the labeled corpus the Phase-1 intent encoder will train on, from data we
already have. Deterministic + stdlib-only: NO torch/transformers/tokenizer, NO
LLM, NO paraphrase model. Run reproducibly (fixed seed):

    python -I -m linuxbuddy.ml.make_dataset

Outputs (all under data/, all git-tracked — this corpus is the training input):
  label_space.json        the frozen label space (Part A; from the KB)
  sweep_intent_map.json   the auditable sweep->KB reconciliation (Part B.1)
  single_turn.raw.jsonl   raw, un-augmented single-turn set (Part B)
  multi_turn.raw.jsonl    raw multi-turn set (Part C)
  train.jsonl / val.jsonl           single-turn split (Part E; train augmented)
  train_mt.jsonl / val_mt.jsonl     multi-turn split (whole chains)
  DATA_CARD.md            counts, balance, seed, no-leakage note (Part E)

Label discipline (why this is careful): the encoder is a FALLBACK BEHIND THE
RULES, so its labels must be the EXACT KB intent ids the planner uses. The KB is
the single source of truth (see labels.py). The sweep CSV uses a different,
coarser label vocabulary, so every sweep row is reconciled to a KB id by a
*behavior-verified* mapping (confirmed against what `lb` actually emits), not by
name — and the reconciliation is written out as sweep_intent_map.json for review.
"""
from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from .labels import (
    ABSTAIN, DIALOGUE_ACTS, all_intents, build_label_space, write_label_space,
)

# ---------------------------------------------------------------------------
# Paths & determinism
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
SWEEP_CSV = DATA_DIR / "eval" / "sweep_scenarios.csv"
SYNONYMS = DATA_DIR / "synonyms.json"

SEED = 20261111          # fixed → byte-reproducible outputs
VAL_FRAC = 0.20
MAX_AUG_POS = 4          # cap augmented variants per positive seed
MAX_AUG_ABSTAIN = 2      # fewer for abstain (filler/dropout only)

# ---------------------------------------------------------------------------
# Part B.1 — the sweep.intent -> KB intent reconciliation (behavior-verified)
# ---------------------------------------------------------------------------
# The sweep's `intent` column is a coarser, utility-style vocabulary authored
# before the KB intent ids were frozen. 57 of its 59 labels do not match a KB id
# by name, so each is mapped to the KB id the planner ACTUALLY fires for those
# phrasings (verified by running `lb`), never by name similarity. Rationale is
# emitted to sweep_intent_map.json.
SWEEP_MAP: dict[str, str] = {
    "access_cdrive": "goto_cdrive",
    "backup_copy": "copy_file",
    "cat": "preview_head",            # verified: "show me config.yaml" -> head -n 10
    "cd_absolute": "goto",
    "cd_ancestor": "goto",            # verified: "take me to project" -> cd -- project
    "cd_child": "goto",
    "cd_home": "go_home",
    "cd_parent": "cd_parent",
    "cd_previous": "go_back",         # "go back to where i was" -> cd -
    "check_installed_cli": "check_installed",
    "check_package": "check_package",
    "chmod_exec": "make_executable",
    "chmod_private": "set_permission",
    "clip": "copy_to_clipboard",
    "copy_file": "copy_file",
    "count_files": "count_files",
    "create_archive": "create_archive",
    "date_time": "date_time",
    "delete_file": "delete_file",
    "dir_size": "disk_usage",
    "disk_space": "disk_free",
    "env_var": "env_var",
    "file_type": "detect_type",
    "find_by_ext": "find_by_type",
    "find_by_name": "find_by_name",
    "find_by_size": "find_by_size",
    "find_by_type": "find_by_type",
    "find_empty": "find_empty",
    "find_largest": "find_largest",
    "find_recent": "find_recent",
    "find_perms": "find_perms",
    "find_port": "process_on_port",
    "grep": "search_in_file",
    "grep_count": "count_matches",
    "grep_recursive": "search_recursive",
    "head": "preview_head",
    "history": "show_history",
    "list_archive": "list_archive",
    "list_proc": "list_processes",
    "ls_perms": "show_permissions",
    "make_dir": "make_dir",
    "move_file": "move_file",
    "open_explorer": "open_explorer",
    "open_vscode": "open_vscode",
    "pip_list": "pip_list",
    "pwd": "where_am_i",
    "run_script": "run_script",
    "sort": "sort_lines",
    "stat": "show_stat",
    "tail": "preview_tail",
    "unique": "unique_lines",
    "venv": "where_python",           # E136 is actually "which python am i using"
    "wc": "count_lines",
    "which": "where_python",
    "win_path": "path_to_windows",
}

# Per-row overrides where one coarse label splits into several KB ids (verified
# by running `lb` on each request). These take precedence over SWEEP_MAP.
SWEEP_ROW_OVERRIDE: dict[str, str] = {
    "E105": "top_by_mem",       # "what's using the most memory" -> ps --sort=-rss
    "E106": "top_by_cpu",       # "top cpu processes"           -> ps --sort=-%cpu
    "E107": "kill_pid",         # "kill process 4321"           -> kill -- 4321
    "E108": "kill_process",     # "stop the python process"     -> pkill -f python
    "E109": "kill_process",     # "terminate the server process"-> pkill -f server
    "E110": "process_on_port",  # "stop whatever's on port 8000"-> ss -ltnp (a READ;
                                #   diverges from sweep "kill": the tool shows the
                                #   port, there is no kill-by-port KB intent)
    "E123": "extract_tar",      # "extract the tarball"         -> tar -xzf
    "E124": "extract_zip",      # "unzip the archive"           -> unzip
}

# Sweep rows the tool ABSTAINS on today (sweep_results_v8: outcome=ABSTAIN).
# Behavior-verified -> _ABSTAIN. These are the documented "honest-5".
SWEEP_ABSTAIN_IDS = {"E056", "E060", "E073", "E138", "E139"}

# ---------------------------------------------------------------------------
# Part B.2 — stress-test GAP examples (hand-labeled against the frozen space)
# ---------------------------------------------------------------------------
# The highest-value signal: phrasings the rules get WRONG or abstain on, where a
# reasonable intent exists. Pulled from the Task-35 stress run and labeled by
# hand with the KB id the request SHOULD hit. (Embedded as literals so the
# generator is reproducible and independent of the ephemeral stress CSV.)
STRESS_GAP: list[tuple[str, str]] = [
    # read phrasings the rules misroute or abstain on
    ("where are the python scripts", "find_by_type"),
    ("list all python files", "find_by_type"),
    ("where are the spreadsheets", "find_by_type"),
    ("got any spreadsheets?", "find_by_type"),
    ("spreadsheet files please", "find_by_type"),
    ("find all the files here", "find_by_type"),
    ("what changed in the last day", "find_by_time"),
    ("what changed in the last day in this directory", "find_by_time"),
    ("find the files modified in the last day", "find_by_time"),
    ("list everything here", "list_all"),
    ("show me what's in this folder", "list_all"),
    ("list everything here in this directory", "list_all"),
    ("what processes are running", "list_processes"),
    ("what processes are running in this directory", "list_processes"),
    ("show me the stats for notes.txt", "show_stat"),
    ("show the permissions of notes.txt", "show_permissions"),
    ("check the syntax of src/main.py", "check_syntax"),
    # destructive verbs that degraded to a read — label the intent they SHOULD
    # have hit (teach the encoder the synonym).
    ("erase scratch.tmp", "delete_file"),
    ("nuke scratch.tmp", "delete_file"),
    ("throw away scratch.tmp", "delete_file"),
    ("wipe scratch.tmp", "delete_file"),
    ("discard scratch.tmp", "delete_file"),
    ("del scratch.tmp", "delete_file"),
    ("set up a folder called reports", "make_dir"),
    ("spin up a folder reports", "make_dir"),
    ("clone config.yaml", "copy_file"),
    ("replicate config.yaml", "copy_file"),
]

# ---------------------------------------------------------------------------
# Part B.3 — abstain / out-of-domain negatives (a LEARNED class)
# ---------------------------------------------------------------------------
# From the stress run (judged ABSTAIN_OK) ...
STRESS_ABSTAIN = [
    "clean up the temp files", "organize the downloads", "tidy up this folder",
    "fix this", "sort this out", "deal with these files",
    "what is the meaning of life", "tell me a joke", "asdfghjkl",
    "qwerty zxcvbn", "banana telephone sunshine", "what's the weather",
]
# ... plus hand-authored negatives so the abstain boundary is well sampled
# (out-of-domain requests a WSL-migrant might actually type).
EXTRA_ABSTAIN = [
    "send an email to my boss", "play some music", "order a pizza",
    "translate this to french", "set a reminder for 5pm", "open youtube",
    "summarize this document", "schedule a meeting", "what can you do",
    "help me", "undo that", "make it faster", "do the thing",
    "why isn't this working", "good morning", "thanks a lot",
    "lorem ipsum dolor sit amet", "flibbertigibbet wotsit thingamajig",
]

# ---------------------------------------------------------------------------
# Part C — multi-turn chains (dialogue acts + frame deltas)
# ---------------------------------------------------------------------------
# Each chain: (chain_id, source, [turns]); each turn:
#   (text, dialogue_act, frame_delta)  -- prev_frame is computed by accumulation.
# ROADMAP_V2.md does not exist in the repo (noted in STATUS.md), so the golden
# chain C001 is authored here directly, consistent with the documented
# find->refine->operate golden path; the stress chains are reconstructed from the
# Task-35 session run; the HC* chains are hand-authored to cover thin acts.
MT_CHAINS: list[tuple[str, str, list[tuple[str, str, dict]]]] = [
    ("C001", "golden_seed", [
        ("find all the csv files", "new", {"name": "*.csv"}),
        ("only the ones over 1mb", "refine", {"size": "+1M"}),
        ("which one is biggest", "operate", {"op": "show", "modifier": "max-by-size"}),
    ]),
    # --- reconstructed from the Task-35 stress session chains ---
    ("S02", "stress_session", [
        ("find files over 1mb", "new", {"size": "+1M"}),
        ("only the json ones", "refine", {"name": "*.json"}),
        ("how many", "operate", {"op": "count", "modifier": "count"}),
    ]),
    ("S03", "stress_session", [
        ("find the log files", "new", {"name": "*.log"}),
        ("never mind", "reset", {}),
    ]),
    ("S04", "stress_session", [
        ("find the csv files", "new", {"name": "*.csv"}),
        ("find the json files", "new", {"name": "*.json"}),
    ]),
    ("S05", "stress_session", [
        ("find the log files", "new", {"name": "*.log"}),
        ("delete them", "fallback", {}),
    ]),
    ("S07", "stress_session", [
        ("find the csv files", "new", {"name": "*.csv"}),
        ("what's the weather", "fallback", {}),
        ("only the ones over 1mb", "refine", {"size": "+1M"}),
    ]),
    ("S08", "stress_session", [
        ("find the csv files", "new", {"name": "*.csv"}),
        ("only the big ones", "fallback", {}),
        ("which is biggest", "operate", {"op": "show", "modifier": "max-by-size"}),
    ]),
    ("S09", "stress_session", [
        ("find files bigger than 1mb", "new", {"size": "+1M"}),
        ("only the csv ones", "refine", {"name": "*.csv"}),
        ("how many are there", "operate", {"op": "count", "modifier": "count"}),
    ]),
    # --- hand-authored to top up thin acts (reset / operate / new-replaces) ---
    ("HC01", "hand", [
        ("find the python files", "new", {"name": "*.py"}),
        ("just the ones from today", "refine", {"mtime": "0"}),
        ("how many", "operate", {"op": "count", "modifier": "count"}),
    ]),
    ("HC02", "hand", [
        ("find files over 100mb", "new", {"size": "+100M"}),
        ("the biggest one", "operate", {"op": "show", "modifier": "max-by-size"}),
    ]),
    ("HC03", "hand", [
        ("show me the csv files", "new", {"name": "*.csv"}),
        ("count them", "operate", {"op": "count", "modifier": "count"}),
    ]),
    ("HC04", "hand", [
        ("find the json files", "new", {"name": "*.json"}),
        ("start over", "reset", {}),
    ]),
    ("HC05", "hand", [
        ("find big files over 50mb", "new", {"size": "+50M"}),
        ("forget it", "reset", {}),
    ]),
    ("HC06", "hand", [
        ("find the txt files", "new", {"name": "*.txt"}),
        ("scratch that", "reset", {}),
    ]),
    ("HC07", "hand", [
        ("find the markdown files", "new", {"name": "*.md"}),
        ("actually find the yaml files", "new", {"name": "*.yaml"}),
    ]),
    ("HC08", "hand", [
        ("find files modified today", "new", {"mtime": "0"}),
        ("only the logs", "refine", {"name": "*.log"}),
        ("biggest", "operate", {"op": "show", "modifier": "max-by-size"}),
    ]),
    ("HC09", "hand", [
        ("find the pdf files", "new", {"name": "*.pdf"}),
        ("the ones over 10mb", "refine", {"size": "+10M"}),
        ("how many", "operate", {"op": "count", "modifier": "count"}),
    ]),
    ("HC10", "hand", [
        ("find the csv files", "new", {"name": "*.csv"}),
        ("delete them", "fallback", {}),
    ]),
    ("HC11", "hand", [
        ("find the log files", "new", {"name": "*.log"}),
        ("never mind", "reset", {}),
        ("find the csv files", "new", {"name": "*.csv"}),
    ]),
    ("HC12", "hand", [
        ("find the yaml files", "new", {"name": "*.yaml"}),
        ("reset", "reset", {}),
    ]),
]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _read_sweep() -> list[dict]:
    with open(SWEEP_CSV, newline="") as f:
        return list(csv.DictReader(f))


def reconcile_sweep_label(row: dict) -> str:
    """Return the KB intent id (or _ABSTAIN) for a sweep row. Fails loudly on an
    unmapped sweep intent — that is the drift guard."""
    rid = row["id"]
    if rid in SWEEP_ABSTAIN_IDS:
        return ABSTAIN
    if rid in SWEEP_ROW_OVERRIDE:
        return SWEEP_ROW_OVERRIDE[rid]
    sweep_intent = row["intent"]
    if sweep_intent not in SWEEP_MAP:
        raise ValueError(
            f"UNMAPPED sweep intent {sweep_intent!r} (row {rid}): the sweep and "
            "KB have drifted. Reconcile in SWEEP_MAP before training.")
    return SWEEP_MAP[sweep_intent]


def write_sweep_map_doc(valid: set[str]) -> dict:
    """Emit the auditable reconciliation (every decision + its basis)."""
    doc = {
        "_comment": (
            "Auditable reconciliation of sweep_scenarios.csv's coarse `intent` "
            "vocabulary to the frozen KB label space (Task 36, Part B.1). Each "
            "mapping was verified by running `lb` on the phrasings, not inferred "
            "by name. Per-row overrides and the behavior-verified _ABSTAIN rows "
            "are listed separately."),
        "coarse_to_kb": dict(sorted(SWEEP_MAP.items())),
        "per_row_override": dict(sorted(SWEEP_ROW_OVERRIDE.items())),
        "abstain_rows": sorted(SWEEP_ABSTAIN_IDS),
        "notes": {
            "cat": "No cat/view intent exists in the KB; `lb` renders head -n 10 "
                   "for 'show me <file>', so cat->preview_head (verified runtime).",
            "E110": "sweep intent 'kill' but `lb` emits `ss -ltnp` (process_on_port, "
                    "a read): there is no kill-by-port KB intent. Labeled by what "
                    "fires.",
            "abstain_rows": "sweep_results_v8 outcome=ABSTAIN (the honest-5): "
                            "generic-target reads + pip install (network, out of "
                            "scope).",
        },
    }
    # sanity: every target is a real label
    targets = set(SWEEP_MAP.values()) | set(SWEEP_ROW_OVERRIDE.values()) | {ABSTAIN}
    bad = sorted(targets - valid)
    if bad:
        raise ValueError(f"sweep map targets not in label space: {bad}")
    (DATA_DIR / "sweep_intent_map.json").write_text(
        json.dumps(doc, indent=2) + "\n")
    return doc


def build_single_turn(valid: set[str]) -> list[dict]:
    """Part B: the raw (un-augmented) single-turn dataset."""
    rows: list[dict] = []

    # 1) sweep (already-labeled, reconciled)
    for r in _read_sweep():
        intent = reconcile_sweep_label(r)
        rows.append({
            "text": r["request"].strip(),
            "intent": intent,
            "domain": r.get("domain", ""),
            "source": "sweep",
            "seed_id": r["id"],
        })

    # 2) stress gap (hand-labeled)
    for i, (text, intent) in enumerate(STRESS_GAP, 1):
        rows.append({
            "text": text, "intent": intent, "domain": "", "source": "stress_gap",
            "seed_id": f"SG{i:03d}",
        })

    # 3) abstain negatives
    for i, text in enumerate(STRESS_ABSTAIN, 1):
        rows.append({"text": text, "intent": ABSTAIN, "domain": "",
                     "source": "stress_abstain", "seed_id": f"ABS{i:03d}"})
    for i, text in enumerate(EXTRA_ABSTAIN, 1):
        rows.append({"text": text, "intent": ABSTAIN, "domain": "",
                     "source": "hand_abstain", "seed_id": f"ABE{i:03d}"})

    for row in rows:
        if row["intent"] not in valid:
            raise ValueError(f"invalid label {row['intent']!r} for {row['text']!r}")
        if not row["text"]:
            raise ValueError(f"empty text for seed {row['seed_id']}")
    return rows


def build_multi_turn() -> list[dict]:
    """Part C: one row per turn, with prev_frame computed by accumulation."""
    rows: list[dict] = []
    for chain_id, source, turns in MT_CHAINS:
        frame: dict = {}
        for tno, (text, act, delta) in enumerate(turns, 1):
            if act not in DIALOGUE_ACTS:
                raise ValueError(f"bad dialogue_act {act!r} in {chain_id}")
            rows.append({
                "chain_id": chain_id, "turn": tno, "text": text,
                "prev_frame": dict(frame), "dialogue_act": act,
                "frame_delta": dict(delta), "source": source,
            })
            # accumulate for the next turn's prev_frame
            if act == "reset":
                frame = {}
            elif act == "new":
                frame = {k: v for k, v in delta.items()
                         if k not in ("op", "modifier")}
            elif act == "refine":
                frame.update(delta)
            # operate/fallback: frame carries forward unchanged (operate changes
            # op/modifier, not the find filters; fallback is a no-op on the frame)
    return rows


# ---------------------------------------------------------------------------
# Part D — deterministic augmentation (train rows only)
# ---------------------------------------------------------------------------
def _load_synonyms() -> dict:
    return json.loads(SYNONYMS.read_text())


def _augment_text(text: str, rng: random.Random, syn: dict, allow_fname: bool):
    """Produce ONE augmented variant + the transform name, or (None, None)."""
    low = text
    transforms = []
    # pick a transform family at random, apply at most two
    families = ["synonym", "filler", "dropout"]
    if allow_fname:
        families.append("fname")
    rng.shuffle(families)
    out = low
    for fam in families[:2]:
        if fam == "synonym":
            applied = False
            for bank in ("verb_phrases", "nouns"):
                for src, alts in syn[bank].items():
                    if src in out.lower():
                        alt = rng.choice(alts)
                        # case-insensitive first-occurrence replace
                        idx = out.lower().find(src)
                        out = out[:idx] + alt + out[idx + len(src):]
                        applied = True
                        break
                if applied:
                    break
            if applied:
                transforms.append("synonym")
        elif fam == "filler":
            pre = rng.choice(syn["fillers_prefix"])
            suf = rng.choice(syn["fillers_suffix"])
            if pre or suf:
                out = f"{pre}{out}{suf}"
                transforms.append("filler")
        elif fam == "dropout":
            toks = out.split()
            drop_idx = [i for i, t in enumerate(toks)
                        if t.lower().strip(".,?") in syn["droppable_tokens"]]
            if drop_idx and len(toks) > 2:
                i = rng.choice(drop_idx)
                toks.pop(i)
                out = " ".join(toks)
                transforms.append("dropout")
        elif fam == "fname":
            applied = False
            for fn, alts in syn["filename_pool"].items():
                if fn in out:
                    out = out.replace(fn, rng.choice(alts), 1)
                    transforms.append("fname")
                    applied = True
                    break
            if not applied:
                for ext, alts in syn["ext_pool"].items():
                    token = f".{ext}"
                    if token in out or f"*.{ext}" in out:
                        out = out.replace(ext, rng.choice(alts), 1)
                        transforms.append("fname")
                        break
    out = out.strip()
    if not transforms or out.lower() == text.lower() or not out:
        return None, None
    return out, "+".join(transforms)


def augment_train(train_rows: list[dict], rng: random.Random) -> list[dict]:
    syn = _load_synonyms()
    out = list(train_rows)
    for row in train_rows:
        is_abstain = row["intent"] == ABSTAIN
        cap = MAX_AUG_ABSTAIN if is_abstain else MAX_AUG_POS
        allow_fname = not is_abstain      # never filename-swap an abstain row
        seen = {row["text"].lower()}
        made = 0
        attempts = 0
        while made < cap and attempts < cap * 4:
            attempts += 1
            variant, tname = _augment_text(row["text"], rng, syn, allow_fname)
            if variant is None or variant.lower() in seen:
                continue
            seen.add(variant.lower())
            made += 1
            aug = dict(row)
            aug["text"] = variant
            aug["source"] = f"aug:{tname}"
            aug["parent_seed_id"] = row["seed_id"]
            aug["seed_id"] = row["seed_id"]      # stays grouped with parent
            out.append(aug)
    return out


# ---------------------------------------------------------------------------
# Part E — group-level stratified split
# ---------------------------------------------------------------------------
def split_single_turn(rows: list[dict], rng: random.Random):
    """80/20 by seed GROUP, stratified by intent. A seed (and later its
    augmentations) stays wholly on one side. Returns (train_raw, val, flags)."""
    by_intent: dict[str, list[str]] = defaultdict(list)
    seed_rows: dict[str, dict] = {}
    for r in rows:
        seed_rows[r["seed_id"]] = r          # one raw row per seed
        by_intent[r["intent"]].append(r["seed_id"])

    train_seeds, val_seeds, flags = set(), set(), []
    for intent in sorted(by_intent):
        seeds = sorted(set(by_intent[intent]))
        rng.shuffle(seeds)
        n = len(seeds)
        if n == 1:
            train_seeds.add(seeds[0])
            flags.append(f"{intent}: only 1 example (train-only, none in val)")
            continue
        n_val = max(1, round(n * VAL_FRAC))
        n_val = min(n_val, n - 1)            # keep >=1 in train
        val_seeds.update(seeds[:n_val])
        train_seeds.update(seeds[n_val:])
        if n - n_val < 3:
            flags.append(f"{intent}: only {n - n_val} train example(s)")
    train = [seed_rows[s] for s in sorted(train_seeds)]
    val = [seed_rows[s] for s in sorted(val_seeds)]
    return train, val, flags


def split_multi_turn(rows: list[dict], rng: random.Random):
    """Split WHOLE chains 80/20 (never split a chain across train/val)."""
    chains = defaultdict(list)
    for r in rows:
        chains[r["chain_id"]].append(r)
    ids = sorted(chains)
    rng.shuffle(ids)
    n_val = max(1, round(len(ids) * VAL_FRAC))
    val_ids = set(ids[:n_val])
    train, val = [], []
    for cid in sorted(chains):
        (val if cid in val_ids else train).extend(
            sorted(chains[cid], key=lambda r: r["turn"]))
    return train, val


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _write_jsonl(path: Path, rows: list[dict]):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def _counts(rows, key):
    return dict(Counter(r[key] for r in rows))


def write_data_card(st_raw, tr, va, mt_raw, tr_mt, va_mt, flags):
    sp = build_label_space()
    n_intents = sp["counts"]["n_intents"]
    tr_ab = sum(1 for r in tr if r["intent"] == ABSTAIN)
    va_ab = sum(1 for r in va if r["intent"] == ABSTAIN)
    raw_ab = sum(1 for r in st_raw if r["intent"] == ABSTAIN)
    aug = sum(1 for r in tr if str(r.get("source", "")).startswith("aug:"))
    L = []
    L.append("# LinuxBuddy v2 — Phase-0 Data Card (Task 36)")
    L.append("")
    L.append("Deterministic, offline, stdlib-only corpus for the Phase-1 intent "
             "encoder. No torch / transformers / LLM / paraphrase model. "
             f"Reproducible with fixed seed **{SEED}** "
             "(`python -I -m linuxbuddy.ml.make_dataset`).")
    L.append("")
    L.append("## Label space (frozen, from the KB)")
    L.append(f"- Intents: **{n_intents}** (exact KB `frame.intent` ids — see "
             "`label_space.json`)")
    L.append(f"- Dialogue acts: {', '.join(sp['dialogue_acts'])}")
    L.append(f"- Special: `{ABSTAIN}` (a learned class)")
    L.append("- Sweep→KB reconciliation: `sweep_intent_map.json` "
             "(behavior-verified; drift guard fires on any unmapped sweep intent).")
    L.append("")
    L.append("## Single-turn")
    L.append(f"- Raw (un-augmented): **{len(st_raw)}** "
             f"(`_ABSTAIN` {raw_ab} = {100*raw_ab/len(st_raw):.1f}%)")
    L.append(f"- Train: **{len(tr)}** (of which {aug} augmented; "
             f"augmentation ×{len(tr)/max(1,len(tr)-aug):.2f} on train) · "
             f"Val: **{len(va)}**")
    L.append(f"- `_ABSTAIN` share — train {tr_ab}/{len(tr)} "
             f"({100*tr_ab/len(tr):.1f}%), val {va_ab}/{len(va)} "
             f"({100*va_ab/len(va):.1f}%)")
    L.append(f"- By source (raw): {_counts(st_raw, 'source')}")
    L.append("")
    L.append("### Per-intent counts (train / val)")
    L.append("| intent | train | val |")
    L.append("|---|---|---|")
    tr_c, va_c = _counts(tr, "intent"), _counts(va, "intent")
    for intent in sorted(set(tr_c) | set(va_c)):
        L.append(f"| {intent} | {tr_c.get(intent,0)} | {va_c.get(intent,0)} |")
    L.append("")
    L.append("### Zero-coverage intents (NO single-turn data at all)")
    have = {r["intent"] for r in st_raw}
    zero = [i for i in all_intents() if i not in have]
    L.append(f"{len(zero)} of {n_intents} KB intents have no single-turn example "
             "in this corpus — the encoder cannot learn them from single-turn data "
             "and will never predict them. The rules still handle these; the "
             "encoder simply won't be a fallback for them until the corpus grows. "
             "(session_* are exercised by the multi-turn set instead.)")
    L.append("")
    L.append("> " + ", ".join(f"`{i}`" for i in zero))
    L.append("")
    L.append("### Under-represented intents (<3 raw train seeds — confusion-matrix watchlist)")
    if flags:
        for fl in flags:
            L.append(f"- {fl}")
    else:
        L.append("- none")
    L.append("")
    L.append("## Multi-turn")
    L.append(f"- Raw turns: **{len(mt_raw)}** across {len({r['chain_id'] for r in mt_raw})} chains")
    L.append(f"- Train turns: **{len(tr_mt)}** · Val turns: **{len(va_mt)}** "
             "(whole chains; never split across the boundary)")
    L.append(f"- By dialogue_act (raw): {_counts(mt_raw, 'dialogue_act')}")
    L.append("  - **Imbalanced by design** (new ≫ refine/operate ≫ reset/fallback); "
             "Phase-2 should weight the loss.")
    L.append("")
    L.append("## Augmentation (train-only)")
    L.append("- Transforms: synonym substitution, filler/politeness injection, "
             "word dropout, filename/extension swap (never on `_ABSTAIN`). "
             "Bank: `data/synonyms.json`.")
    L.append(f"- Cap per seed: positives ≤{MAX_AUG_POS}, abstain ≤{MAX_AUG_ABSTAIN} "
             "(filler/dropout only).")
    L.append("- **Train-only** and **group-level**: augmentation is applied after "
             "the split and only to train seeds, so no variant of a val example "
             "leaks into train.")
    L.append("")
    L.append("## No-leakage guarantee")
    L.append("- Single-turn split is by `seed_id` group; multi-turn by whole "
             "`chain_id`. `tests/test_data.py` asserts the train/val id "
             "intersection is empty.")
    L.append("")
    (DATA_DIR / "DATA_CARD.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
# Orchestrate
# ---------------------------------------------------------------------------
def generate():
    DATA_DIR.mkdir(exist_ok=True)
    sp = write_label_space(DATA_DIR / "label_space.json")
    valid = set(sp["intents"]) | {ABSTAIN}
    write_sweep_map_doc(valid)

    # Part B/C raw
    st_raw = build_single_turn(valid)
    mt_raw = build_multi_turn()
    _write_jsonl(DATA_DIR / "single_turn.raw.jsonl", st_raw)
    _write_jsonl(DATA_DIR / "multi_turn.raw.jsonl", mt_raw)

    # Part E split (one RNG, seeded once, used in a fixed order → reproducible)
    rng = random.Random(SEED)
    tr_raw, va, flags = split_single_turn(st_raw, rng)
    tr = augment_train(tr_raw, rng)          # Part D: train-only augmentation
    tr.sort(key=lambda r: (r["seed_id"], r["source"], r["text"]))
    va.sort(key=lambda r: (r["seed_id"], r["text"]))
    _write_jsonl(DATA_DIR / "train.jsonl", tr)
    _write_jsonl(DATA_DIR / "val.jsonl", va)

    tr_mt, va_mt = split_multi_turn(mt_raw, rng)
    _write_jsonl(DATA_DIR / "train_mt.jsonl", tr_mt)
    _write_jsonl(DATA_DIR / "val_mt.jsonl", va_mt)

    write_data_card(st_raw, tr, va, mt_raw, tr_mt, va_mt, flags)

    print(f"label space: {sp['counts']['n_intents']} intents + _ABSTAIN")
    print(f"single-turn raw={len(st_raw)}  train={len(tr)}  val={len(va)}")
    print(f"multi-turn  raw={len(mt_raw)} turns  train={len(tr_mt)}  val={len(va_mt)}")
    ab = sum(1 for r in tr if r['intent'] == ABSTAIN)
    print(f"_ABSTAIN train share: {100*ab/len(tr):.1f}%")
    if flags:
        print(f"under-represented intents flagged: {len(flags)}")
    return {
        "st_raw": st_raw, "train": tr, "val": va,
        "mt_raw": mt_raw, "train_mt": tr_mt, "val_mt": va_mt, "flags": flags,
    }


if __name__ == "__main__":  # pragma: no cover
    generate()
