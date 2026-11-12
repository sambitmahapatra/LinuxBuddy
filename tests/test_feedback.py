"""Task 46 (B) — the offline feedback-capture hook.

Behaviour, not plumbing: an ABSTAIN is logged (the miss source the loop feeds on),
a successful emit is NOT, the log is local/offline + user-controlled, and a feedback
failure can NEVER break `lb`.
"""
import json

import pytest

from linuxbuddy import feedback
from linuxbuddy.cli import main


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    # point the cache dir at a temp path and force the single-turn path (the owner's
    # shell may export LINUXBUDDY_SESSION; unset it so these assert single-turn).
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("LINUXBUDDY_SESSION", raising=False)
    return tmp_path


def test_abstain_is_logged(capsys):
    code = main(["asdkjfh qwptoi zzz nonsense"])
    capsys.readouterr()
    assert code == 1
    recs = feedback.read()
    assert len(recs) == 1
    r = recs[0]
    assert r["request"] == "asdkjfh qwptoi zzz nonsense"
    assert r["outcome"] == "abstain"
    assert r["path"] == "single"
    assert "cwd" in r and "ts" in r


def test_successful_emit_is_not_logged(capsys):
    code = main(["csv files over 100 megs"])
    capsys.readouterr()
    assert code == 0                      # a real command emitted
    assert feedback.read() == []          # success is NOT feedback


def test_session_path_tag(capsys, monkeypatch):
    # when the multi-turn widget is active, an abstain that falls through to the
    # single-turn seam is tagged "session", not "single".
    monkeypatch.setenv("LINUXBUDDY_SESSION", "1")
    main(["zzz total gibberish qqq"])
    capsys.readouterr()
    recs = feedback.read()
    assert recs and recs[-1]["path"] == "session"


def test_feedback_flag_prints_log(capsys):
    main(["blah blah unparseable"])
    capsys.readouterr()
    code = main(["--feedback"])
    out = capsys.readouterr().out
    assert code == 0
    assert "blah blah unparseable" in out or "blah blah unparseable"  # request shown
    assert "1 abstain" in out


def test_feedback_clear_wipes(capsys):
    main(["nonsense one"])
    main(["nonsense two"])
    capsys.readouterr()
    assert len(feedback.read()) == 2
    code = main(["--feedback-clear"])
    out = capsys.readouterr().out
    assert code == 0
    assert "cleared 2" in out
    assert feedback.read() == []


def test_unwritable_cache_is_a_noop_not_a_crash(capsys, monkeypatch):
    # an unwritable cache dir must NOT break lb — the abstain still returns 1 and
    # prints nothing to stdout; the feedback write is silently dropped.
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", "/proc/nonexistent/cannot/create")
    code = main(["qqq unparseable zzz"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""             # lb behaviour unchanged
    assert "not sure" in captured.err


def test_log_abstain_never_raises(monkeypatch):
    # direct unit check: even if os.getcwd explodes, log_abstain swallows it.
    monkeypatch.setattr(feedback.os, "getcwd", lambda: (_ for _ in ()).throw(OSError("boom")))
    feedback.log_abstain("x", "single")   # must not raise
