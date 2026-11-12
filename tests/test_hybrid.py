"""Task 39 — the hybrid seam (encoder as rules fallback). Five guardrails.

The regression + gate + degradation tests need NO ML and run in the main venv
(there the encoder is simply absent → pure v1, which is itself the degradation
proof). The fallback/asymmetry/safety tests need sentence-transformers + the
checkpoint and run in .venv-ml.
"""
from __future__ import annotations

import contextlib
import csv
import io
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
SCENARIOS = DATA / "eval" / "sweep_scenarios.csv"
CKPT = REPO_ROOT / "models" / "ft-minilm-l6"

from linuxbuddy import cli  # noqa: E402  (pure-stdlib import)
from linuxbuddy.nlu import Frame  # noqa: E402


def _run_lb(request: str, cwd: str, encoder_on: bool):
    """Call lb in-process from cwd with the encoder on/off; return (stdout, rc)."""
    old_cwd = os.getcwd()
    saved = {k: os.environ.get(k) for k in ("LINUXBUDDY_ENCODER", "LINUXBUDDY_SESSION")}
    try:
        os.chdir(cwd)
        os.environ.pop("LINUXBUDDY_SESSION", None)   # force single-turn
        if encoder_on:
            os.environ.pop("LINUXBUDDY_ENCODER", None)
        else:
            os.environ["LINUXBUDDY_ENCODER"] = "0"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main([request])
        return out.getvalue().strip(), rc
    finally:
        os.chdir(old_cwd)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture
def maze(tmp_path, monkeypatch):
    """A disposable maze so destructive commands emit (rc 3) deterministically."""
    root = tmp_path / "testlinuxbuddy"
    root.mkdir()
    monkeypatch.setenv("LINUXBUDDY_MAZE_ROOT", str(root))
    return str(root)


def _scenarios():
    with SCENARIOS.open() as f:
        return [(r["id"], r["request"]) for r in csv.DictReader(f) if r.get("request")]


# --- Guardrail 1: rules keep absolute priority (0 regression diffs) ----------
def test_regression_rule_handled_rows_unchanged(maze):
    """Every sweep row the rules HANDLE (rc != 1 with the encoder off) must be
    byte-for-byte identical with the encoder on. Abstains (rc 1) may improve —
    that's new coverage, reported, not a regression."""
    rows = _scenarios()
    assert len(rows) >= 140, f"expected the ~147-row sweep, got {len(rows)}"
    regressions, gained = [], 0
    for sid, req in rows:
        off_out, off_rc = _run_lb(req, maze, encoder_on=False)
        on_out, on_rc = _run_lb(req, maze, encoder_on=True)
        if off_rc != 1:                       # rule produced a command → must match
            if (on_out, on_rc) != (off_out, off_rc):
                regressions.append((sid, req, (off_out, off_rc), (on_out, on_rc)))
        elif on_rc != 1:                      # was abstain, now resolved by encoder
            gained += 1
    assert not regressions, f"encoder changed rule-handled rows: {regressions[:5]}"
    print(f"\n[regression] 0 diffs on rule-handled rows; "
          f"encoder newly resolved {gained}/{sum(1 for _ in rows)} rows "
          f"(0 in the main venv where the encoder is absent).")


# --- Guardrail 4: graceful degradation + kill switch -------------------------
def test_kill_switch_forces_pure_rules(maze):
    """LINUXBUDDY_ENCODER=0 → a true-abstain request abstains exactly like v1."""
    out, rc = _run_lb("what processes are running", maze, encoder_on=False)
    assert rc == 1 and out == "", (out, rc)


def test_rule_hit_identical_with_and_without_encoder(maze):
    out_off, rc_off = _run_lb("find all csv files in data", maze, False)
    out_on, rc_on = _run_lb("find all csv files in data", maze, True)
    assert (out_off, rc_off) == (out_on, rc_on)       # rule hit: encoder irrelevant
    assert rc_off == 0 and out_off.startswith("find ") and "*.csv" in out_off


# --- Guardrail 2 + gate: an encoder-chosen destructive is still gated --------
def test_gate_holds_for_encoder_chosen_destructive(maze, monkeypatch):
    """A delete_file frame (as the encoder would produce) is refused outside the
    maze and emitted at exit 3 inside it — identical to a rule-chosen destructive.
    No model needed: we hand _emit_frame the frame directly."""
    frame = Frame("delete_file", {"path": "scratch.tmp"})
    info = {"source": "encoder", "destructive": True}

    # inside the maze → exit 3
    monkeypatch.chdir(maze)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = cli._emit_frame(frame, info)
    assert rc == 3 and out.getvalue().strip() == "rm -- scratch.tmp"

    # outside the maze → refused, nothing on stdout
    outside = Path(maze).parent
    monkeypatch.chdir(outside)
    out2 = io.StringIO()
    with contextlib.redirect_stdout(out2), contextlib.redirect_stderr(io.StringIO()):
        rc2 = cli._emit_frame(frame, info)
    assert rc2 == 1 and out2.getvalue().strip() == ""


# --- Guardrail 5: fast path never imports ANY of the ML stack ----------------
def test_fast_path_does_not_import_ml_stack(maze):
    """After a rule hit, none of torch/transformers/sentence_transformers/
    onnxruntime are loaded — the encoder (now ONNX) stays entirely off the hot
    path (Task 40 extends this from torch-only to the full set)."""
    import subprocess
    code = (
        "import sys; from linuxbuddy import cli; "
        "cli.main(['find all csv files in data']); "
        "heavy = [m for m in ('torch','transformers','sentence_transformers',"
        "'onnxruntime') if m in sys.modules]; "
        "assert not heavy, f'ML modules imported on rule hit: {heavy}'; "
        "print('clean')"
    )
    env = dict(os.environ, LINUXBUDDY_MAZE_ROOT=maze)
    env.pop("LINUXBUDDY_SESSION", None)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "clean" in r.stdout, r.stderr


# --- Guardrail 4 (Task 40): ONNX artifact absent → pure v1, no crash ---------
def test_degrades_when_onnx_artifact_absent(maze, monkeypatch):
    """If the .onnx file is missing (here: model_path points nowhere), the encoder
    silently yields to pure rules — runs in ANY venv, imports no ML."""
    from linuxbuddy import hybrid
    base = hybrid._load_config()
    monkeypatch.setattr(hybrid, "_load_config",
                        lambda: {**base, "model_path": "models/does-not-exist"})
    frame, info = hybrid.classify_fallback("what processes are running")
    assert frame is None and info == {}
    # and end-to-end the request simply abstains like v1 (rc 1, empty buffer)
    out, rc = _run_lb("what processes are running", maze, encoder_on=True)
    assert rc == 1 and out == "", (out, rc)


# --- ONNX runtime path: the encoder actually fires + asymmetry + safety ------
# These exercise the SHIPPED torch-free path (onnxruntime + tokenizers), so they
# need onnxruntime + the exported .onnx; they run in .venv-ml after onnx_export.
ONNX_FILE = CKPT / "onnx" / "encoder.onnx"


@pytest.fixture(scope="module")
def _onnx():
    pytest.importorskip("onnxruntime", reason="ONNX runtime only (.venv-ml)")
    pytest.importorskip("tokenizers", reason="ONNX runtime only (.venv-ml)")
    if not ONNX_FILE.exists():
        pytest.skip("no .onnx artifact; run linuxbuddy.ml.onnx_export first")


@pytest.fixture(scope="module")
def _torch():
    pytest.importorskip("sentence_transformers", reason="torch reference only (.venv-ml)")
    if not (CKPT / "config.json").exists():
        pytest.skip("no fine-tuned checkpoint; run linuxbuddy.ml.finetune first")


def test_fallback_resolves_a_true_abstain(_onnx, maze):
    """A read phrasing the rules abstain on now resolves through the gate at rc 0."""
    out, rc = _run_lb("what processes are running", maze, encoder_on=True)
    assert rc == 0 and out == "ps aux", (out, rc)


def test_destructive_threshold_asymmetry(_onnx, monkeypatch):
    from linuxbuddy import hybrid
    req = "delete the file scratch.tmp"
    # default thresholds: clearly destructive above the bar → a delete_file frame
    frame, info = hybrid.classify_fallback(req)
    assert frame is not None and info["intent"] == "delete_file" and info["destructive"]

    # raise the destructive bar above its score → must abstain (no rm emitted)
    base = hybrid._load_config()
    monkeypatch.setattr(hybrid, "_load_config",
                        lambda: {**base, "t_destructive": 0.99})
    frame2, _ = hybrid.classify_fallback(req)
    assert frame2 is None, "destructive emitted below its (raised) confidence bar"


def test_safety_zero_destructive_on_nonsense(_onnx):
    """THE safety metric: the encoder emits zero destructive intents on nonsense."""
    from linuxbuddy import hybrid
    probe = [__import__("json").loads(l)
             for l in (DATA / "nonsense_probe.jsonl").read_text().splitlines() if l.strip()]
    destructive = []
    for r in probe:
        frame, info = hybrid.classify_fallback(r["text"])
        if frame is not None and info.get("destructive"):
            destructive.append((r["text"], info["intent"]))
    assert not destructive, f"destructive command(s) on nonsense: {destructive}"
    print(f"\n[safety] destructive-on-nonsense = 0 / {len(probe)}")


# --- Task 40 fidelity + decision parity (ONNX must match the torch model) -----
_PARITY_PROBE = [
    "what processes are running", "where are the spreadsheets",
    "delete the file scratch.tmp", "what changed in the last day",
    "list everything here", "show me the largest files",
    "count the python files", "make a new folder called out",
    "kill whatever is on port 8080", "asdfqwer zxcv", "fix this", "clean up",
    "the quick brown fox", "how big is this directory", "extract the tarball",
]


def test_onnx_torch_embedding_fidelity(_onnx, _torch):
    """ONNX embeddings must match the torch reference per-pair cosine ≥ 0.999
    (pooling/precision parity). A drop here means silent accuracy loss."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from linuxbuddy.ml.onnx_encoder import OnnxEncoder

    ref = np.asarray(SentenceTransformer(str(CKPT)).encode(
        _PARITY_PROBE, normalize_embeddings=True, show_progress_bar=False), dtype="float32")
    enc = OnnxEncoder.load(str(ONNX_FILE), str(CKPT / "tokenizer.json"))
    got = enc.encode(_PARITY_PROBE)
    cos = (got * ref).sum(axis=1)
    assert float(cos.min()) >= 0.999, f"embedding drift: min cosine {cos.min():.5f}"
    print(f"\n[fidelity] ONNX-vs-torch cosine min={cos.min():.5f} mean={cos.mean():.5f}")


def _decide(ranked, cfg):
    """Replicate hybrid's emit/abstain decision from a ranking (for parity)."""
    from linuxbuddy import gate
    from linuxbuddy.planner import risk_ops
    top1_i, top1 = ranked[0]
    top2 = ranked[1][1] if len(ranked) > 1 else 0.0
    try:
        destructive = gate.is_destructive(risk_ops(top1_i))
    except Exception:
        return "_ABSTAIN"
    T = cfg["t_destructive"] if destructive else cfg["t_read"]
    if top1 < T or (destructive and (top1 - top2) < cfg["margin_min"]):
        return "_ABSTAIN"
    return top1_i


def test_onnx_torch_decision_parity(_onnx, _torch):
    """Row for row, the ONNX index makes the SAME emit/abstain decision and picks
    the SAME intent as the torch index — swapping the backend moves no decision."""
    from linuxbuddy import hybrid
    from linuxbuddy.ml.onnx_encoder import OnnxIntentIndex
    from linuxbuddy.ml.zeroshot import IntentIndex
    cfg = hybrid._load_config()
    onnx_idx = OnnxIntentIndex.cached(CKPT)
    torch_idx = IntentIndex.cached(mode="desc", model_name=str(CKPT),
                                   cache_path=str(CKPT / "index_desc.npz"))
    diffs = []
    for u in _PARITY_PROBE:
        o = _decide(onnx_idx.rank(u), cfg)
        t = _decide(torch_idx.rank(u), cfg)
        if o != t:
            diffs.append((u, t, o))
    assert not diffs, f"ONNX changed a decision vs torch: {diffs}"
    print(f"\n[parity] {len(_PARITY_PROBE)}/{len(_PARITY_PROBE)} decisions identical")
