"""The authoritative label space for the Phase-1 intent encoder.

The encoder is a FALLBACK BEHIND THE RULES: its predicted labels must be the
*exact* intent ids the planner/router already use (``frame.intent``), or its
output cannot plug into the hybrid router. So the KB is the single source of
truth — we enumerate intents straight from ``load_kb()`` and never invent or
rename a label.

The KB keys intents as PLAIN, globally-unique strings (e.g. ``find_by_type``,
``copy_file``), NOT domain-dotted — the planner's ``_lookup`` scans every
capability for ``intent in intents``. We therefore use those plain keys as the
label space (matching the KB exactly, per the task), and carry the domain
separately in an intent->domain map for stratification and reporting.

Dialogue acts come from ``session.classify`` (new/refine/operate/reset/fallback).
``_ABSTAIN`` is a real, learned class: what the encoder must emit for
out-of-domain / vague input instead of forcing a wrong intent.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..kb import load_kb

__all__ = [
    "ABSTAIN", "DIALOGUE_ACTS", "CAPABILITY_DOMAIN",
    "build_label_space", "intent_domain_map", "all_intents",
]

ABSTAIN = "_ABSTAIN"

# The dialogue-act space is exactly what session.classify() returns.
DIALOGUE_ACTS = ["new", "refine", "operate", "reset", "fallback"]

# KB capability name -> taxonomy domain (taxonomy.yaml's 9 domains, plus the two
# v2 additions the taxonomy predates: file_management and the session composer).
CAPABILITY_DOMAIN = {
    "search_files": "file_discovery",
    "inspect_file": "file_inspection",
    "search_text": "text_and_logs",
    "workspace": "workspace_and_shell",
    "inspect_filesystem": "filesystem_permissions",
    "inspect_process": "processes",
    "wsl_interop": "wsl_interop",
    "manage_archives": "archives_backup",
    "python_env": "python_environments",
    "manage_files": "file_management",
    "session_compose": "session",
}


def intent_domain_map() -> dict[str, str]:
    """{intent_id: domain} for every intent the KB defines."""
    out: dict[str, str] = {}
    for capname, cap in load_kb().items():
        domain = CAPABILITY_DOMAIN.get(capname, capname)
        for intent in cap.get("intents", {}):
            out[intent] = domain
    return out


def all_intents() -> list[str]:
    """Every KB intent id, sorted. This is the frozen single-turn label space."""
    return sorted(intent_domain_map().keys())


def build_label_space() -> dict:
    """The full frozen label space, ready to serialise to data/label_space.json."""
    idm = intent_domain_map()
    intents = sorted(idm.keys())
    return {
        "_comment": (
            "Frozen Phase-1 label space. Intents are the EXACT plain KB keys the "
            "planner uses as frame.intent (not domain-dotted). Generated from "
            "load_kb() by linuxbuddy.ml.labels — do not hand-edit."
        ),
        "intents": intents,
        "intent_domain": {k: idm[k] for k in intents},
        "dialogue_acts": list(DIALOGUE_ACTS),
        "special": [ABSTAIN],
        "counts": {
            "n_intents": len(intents),
            "n_dialogue_acts": len(DIALOGUE_ACTS),
        },
    }


def write_label_space(path: str | Path) -> dict:
    space = build_label_space()
    Path(path).write_text(json.dumps(space, indent=2, sort_keys=False) + "\n")
    return space


if __name__ == "__main__":  # pragma: no cover
    sp = build_label_space()
    print(json.dumps(sp, indent=2))
    print("n_intents:", sp["counts"]["n_intents"])
