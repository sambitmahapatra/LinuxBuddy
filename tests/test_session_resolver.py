"""Task 45 — the context-aware session resolver (fallback seam).

The guardrail split mirrors test_hybrid: the degradation / safety-cue / fast-path /
"rules keep priority" tests need NO ML and run in the main venv (there the encoder
is simply absent → pure rules, which is itself the degradation proof). The
end-to-end recovery tests need onnxruntime + the .onnx checkpoint and run in
.venv-ml.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CKPT = REPO_ROOT / "models" / "ft-minilm-l6"
ONNX_FILE = CKPT / "onnx" / "encoder.onnx"

from linuxbuddy import cli, session, session_resolver  # noqa: E402


# --------------------------------------------------------------------------
# In-process session-chain driver (separate turns share the disk-backed frame)
# --------------------------------------------------------------------------
def _run_chain(turns, cache_dir, maze, sid="t", encoder_on=True):
    """Run each turn through cli.main in session mode; return [(stdout, rc), …]."""
    saved = {k: os.environ.get(k) for k in
             ("LINUXBUDDY_SESSION", "LINUXBUDDY_CACHE_DIR", "LINUXBUDDY_ENCODER",
              "LINUXBUDDY_MAZE_ROOT")}
    old_cwd = os.getcwd()
    results = []
    try:
        os.environ["LINUXBUDDY_SESSION"] = sid
        os.environ["LINUXBUDDY_CACHE_DIR"] = str(cache_dir)
        os.environ["LINUXBUDDY_MAZE_ROOT"] = str(maze)
        if encoder_on:
            os.environ.pop("LINUXBUDDY_ENCODER", None)
        else:
            os.environ["LINUXBUDDY_ENCODER"] = "0"
        os.chdir(maze)
        cli.main(["--reset"])
        for t in turns:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = cli.main([t])
            results.append((out.getvalue().strip(), rc))
    finally:
        os.chdir(old_cwd)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return results


@pytest.fixture
def maze(tmp_path):
    root = tmp_path / "testlinuxbuddy"
    root.mkdir()
    return str(root)


# --------------------------------------------------------------------------
# No-ML guardrails (run everywhere)
# --------------------------------------------------------------------------
def test_no_frame_returns_none():
    assert session_resolver.resolve_fallback("which of those is heaviest", None) == (None, {})


def test_destructive_cue_never_recovered():
    """SAFETY (invariant #6): a destructive elliptical turn is refused BEFORE any
    model is consulted — returns None regardless of the encoder."""
    frame = session.SessionFrame(targets={"path": ".", "name": "*.log"},
                                 history=[{"request": "find the log files", "act": "new"}])
    for turn in ("get rid of those", "drop the tiny ones", "trash them",
                 "delete them", "remove the big ones", "move those"):
        delta, info = session_resolver.resolve_fallback(turn, frame)
        assert delta is None and info == {}, f"{turn!r} must not be recovered"


def test_kill_switch_forces_pure_rules(monkeypatch):
    monkeypatch.setenv("LINUXBUDDY_ENCODER", "0")
    frame = session.SessionFrame(targets={"path": ".", "name": "*.csv"},
                                 history=[{"request": "find the csv files", "act": "new"}])
    assert session_resolver.resolve_fallback("which of those is heaviest", frame) == (None, {})


def test_degradation_elliptical_abstains_without_encoder(maze, tmp_path):
    """With the encoder off, a novel elliptical turn falls through to single-turn
    and abstains exactly as before (rc 1, empty buffer) — the resolver is a bonus,
    never a dependency."""
    # "the beefiest one" parses to nothing single-turn → genuine abstain without
    # the encoder (with it, the resolver recovers it — see the e2e test).
    res = _run_chain(["dig up the log files", "the beefiest one"],
                     tmp_path / "c", maze, sid="deg", encoder_on=False)
    assert res[0][1] == 0 and "*.log" in res[0][0]        # turn 1 rule-handled
    assert res[1] == ("", 1)                              # turn 2 abstains, no command


def test_rules_keep_priority_resolver_not_consulted(maze, tmp_path, monkeypatch):
    """When the RULES handle the turn (in-vocab 'which one is biggest'), the
    resolver must NOT be consulted at all."""
    calls = []
    orig = session_resolver.resolve_fallback
    monkeypatch.setattr(session_resolver, "resolve_fallback",
                        lambda *a, **k: (calls.append(a), orig(*a, **k))[1])
    res = _run_chain(["find the csv files", "which one is biggest"],
                     tmp_path / "c", maze, sid="prio", encoder_on=False)
    assert res[1][1] == 0 and "sort -rn" in res[1][0]     # rules produced biggest
    assert calls == [], "resolver was consulted on a rule-handled turn"


def test_fast_path_rule_handled_no_ml_stack(maze, tmp_path):
    """A rule-handled SESSION chain imports none of torch/transformers/
    sentence_transformers/onnxruntime."""
    code = (
        "import sys, os; from linuxbuddy import cli; "
        "cli.main(['--reset']); cli.main(['find the csv files']); "
        "cli.main(['which one is biggest']); "
        "heavy=[m for m in ('torch','transformers','sentence_transformers','onnxruntime') "
        "if m in sys.modules]; "
        "assert not heavy, f'ML imported on rule-handled session turn: {heavy}'; print('clean')"
    )
    env = dict(os.environ, LINUXBUDDY_SESSION="fast", LINUXBUDDY_ENCODER="0",
               LINUXBUDDY_CACHE_DIR=str(tmp_path / "c"), LINUXBUDDY_MAZE_ROOT=str(maze))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=env, cwd=maze)
    assert r.returncode == 0 and "clean" in r.stdout, r.stderr


# --------------------------------------------------------------------------
# End-to-end recovery (needs onnxruntime + the .onnx checkpoint → .venv-ml)
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def _onnx():
    pytest.importorskip("onnxruntime", reason="ONNX runtime only (.venv-ml)")
    pytest.importorskip("tokenizers", reason="ONNX runtime only (.venv-ml)")
    if not ONNX_FILE.exists():
        pytest.skip("no .onnx artifact; run linuxbuddy.ml.onnx_export first")


def test_novel_elliptical_recovered_end_to_end(_onnx, maze, tmp_path):
    """The headline: a novel-phrasing elliptical operate turn the rules abstain on
    is recovered to the right session_find_biggest command, accumulating the prior
    -name/-size."""
    res = _run_chain(["pull up the csv files", "only the ones over 2mb",
                      "which of those is heaviest"],
                     tmp_path / "c", maze, sid="novel", encoder_on=True)
    cmd, rc = res[2]
    assert rc == 0, (cmd, rc)
    assert "-name '*.csv'" in cmd and "-size +2M" in cmd
    assert "sort -rn | head -1" in cmd                   # the biggest-one render


def test_novel_count_recovered(_onnx, maze, tmp_path):
    res = _run_chain(["pull up the pdf files", "give me a count of those"],
                     tmp_path / "c", maze, sid="count", encoder_on=True)
    cmd, rc = res[1]
    assert rc == 0 and "-name '*.pdf'" in cmd and "wc -l" in cmd, (cmd, rc)


def test_destructive_elliptical_abstains_end_to_end(_onnx, maze, tmp_path):
    """SAFETY live: a destructive elliptical turn emits NO command (abstains),
    even with the encoder on."""
    res = _run_chain(["round up the log files", "only the ones from yesterday",
                      "get rid of those"],
                     tmp_path / "c", maze, sid="destr", encoder_on=True)
    assert res[2] == ("", 1), res[2]                     # abstain, 0 command emitted
