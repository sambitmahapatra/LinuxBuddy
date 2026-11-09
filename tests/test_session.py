"""Task 30 — v2 Phase 1 spike: multi-turn session (rules only, no model).

Unit: SessionFrame merge/TTL/reset + disk round-trip + cwd-reset.
Integration: the 3-turn target chain through the session store, reset mid-chain,
and an unrelated turn (act=new) replacing the frame — driven through the real
cli.main with LINUXBUDDY_SESSION set and an isolated cache dir.
"""
import io
import contextlib

import pytest

from linuxbuddy import session
from linuxbuddy.session import SessionFrame, classify
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell
from linuxbuddy.cli import main


# --------------------------------------------------------------------------
# Unit — SessionFrame
# --------------------------------------------------------------------------

def test_merge_accumulates_filters_without_clobbering():
    sf = SessionFrame(targets={"name": "*.csv"}, filters={"size": "+100M"})
    sf.merge({"filters": {"mtime": "1"}})          # refine: add a time filter
    assert sf.filters == {"size": "+100M", "mtime": "1"}   # size survives
    assert sf.targets == {"name": "*.csv"}                 # name survives


def test_merge_operate_sets_modifier_keeps_filters():
    sf = SessionFrame(targets={"name": "*.csv"}, filters={"size": "+100M", "mtime": "1"})
    sf.merge({"op": "show", "modifier": "max-by-size"})
    assert sf.op == "show" and sf.modifier == "max-by-size"
    assert sf.filters == {"size": "+100M", "mtime": "1"}   # untouched


def test_is_stale_respects_ttl():
    sf = SessionFrame()
    sf.touch()
    assert not sf.is_stale(600)
    assert sf.is_stale(0)          # ttl=0 → anything is stale


def test_reset_clears_the_running_query():
    sf = SessionFrame(op="show", targets={"name": "*.csv"},
                      filters={"size": "+100M"}, modifier="max-by-size",
                      shell_id="k")
    sf.reset()
    assert sf.targets == {} and sf.filters == {} and sf.modifier is None
    assert sf.op == "find"
    assert sf.shell_id == "k"      # identity kept


def test_to_command_plan_compiles_through_v1_pipeline():
    sf = SessionFrame(targets={"path": ".", "name": "*.csv"},
                      filters={"size": "+100M", "mtime": "1"})
    assert to_shell(compile(sf.to_command_plan())) == \
        "find . -name '*.csv' -size +100M -daystart -mtime 1"
    sf.merge({"op": "show", "modifier": "max-by-size"})
    assert to_shell(compile(sf.to_command_plan())) == \
        "find . -name '*.csv' -size +100M -daystart -mtime 1 -printf '%s\\t%p\\n' | sort -rn | head -1"


# --------------------------------------------------------------------------
# Unit — store round-trips to disk, with TTL + cwd reset
# --------------------------------------------------------------------------

def test_store_round_trips_to_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    sf = SessionFrame(targets={"name": "*.csv"}, filters={"size": "+100M"},
                      cwd="/dirA", shell_id="k")
    session.save("k", sf)
    back = session.load("k", cwd="/dirA")
    assert back is not None
    assert back.targets == {"name": "*.csv"} and back.filters == {"size": "+100M"}


def test_store_missing_file_is_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    assert session.load("does-not-exist") is None


def test_store_corrupt_file_is_tolerated(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    (tmp_path / "session_k.json").write_text("{not valid json")
    assert session.load("k") is None   # no raise


def test_cwd_change_resets(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    session.save("k", SessionFrame(filters={"size": "+100M"}, cwd="/dirA", shell_id="k"))
    assert session.load("k", cwd="/dirA") is not None
    assert session.load("k", cwd="/dirB") is None   # a cd resets context


def test_ttl_expiry_resets(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    session.save("k", SessionFrame(filters={"size": "+100M"}, cwd="/dirA", shell_id="k"))
    assert session.load("k", ttl=0, cwd="/dirA") is None


# --------------------------------------------------------------------------
# Unit — the dialogue-act classifier
# --------------------------------------------------------------------------

def test_classify_new_for_self_contained():
    assert classify("find CSV files larger than 100MB", None)[0] == "new"


def test_classify_refine_for_bare_constraint():
    frame = SessionFrame(targets={"name": "*.csv"}, filters={"size": "+100M"})
    act, delta = classify("only the ones modified yesterday", frame)
    assert act == "refine" and delta["filters"] == {"mtime": "1"}


def test_classify_operate_for_biggest():
    frame = SessionFrame(targets={"name": "*.csv"})
    act, delta = classify("show the biggest one", frame)
    assert act == "operate" and delta["modifier"] == "max-by-size"


def test_classify_new_replaces_even_with_frame():
    frame = SessionFrame(targets={"name": "*.csv"})
    assert classify("find all json files", frame)[0] == "new"


def test_classify_reset_words():
    frame = SessionFrame(targets={"name": "*.csv"})
    assert classify("never mind", frame)[0] == "reset"
    assert classify("start over", frame)[0] == "reset"


# --------------------------------------------------------------------------
# Integration — the chain through the real CLI + session store
# --------------------------------------------------------------------------

def _run(req):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main([req])
    return rc, buf.getvalue().strip()


@pytest.fixture
def session_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("LINUXBUDDY_SESSION", "1")
    monkeypatch.setenv("LINUXBUDDY_CACHE_DIR", str(tmp_path))
    # keep destructive gate irrelevant here (all read-only) and cwd stable
    session.clear(session.store_key())
    yield
    session.clear(session.store_key())


def test_three_turn_chain(session_mode):
    rc1, c1 = _run("find CSV files larger than 100MB")
    rc2, c2 = _run("only the ones modified yesterday")
    rc3, c3 = _run("show the biggest one")
    assert (rc1, c1) == (0, "find . -name '*.csv' -size +100M")
    assert (rc2, c2) == (0, "find . -name '*.csv' -size +100M -daystart -mtime 1")
    assert (rc3, c3) == (
        0,
        "find . -name '*.csv' -size +100M -daystart -mtime 1 "
        "-printf '%s\\t%p\\n' | sort -rn | head -1",
    )


def test_reset_midchain_reparses_fresh(session_mode):
    _run("find CSV files larger than 100MB")
    _run("only the ones modified yesterday")
    rc, out = _run("never mind")
    assert rc == 1 and out == ""                 # nothing to emit on a bare reset
    # the next refine has no frame to build on → falls back to v1 single-turn
    rc2, out2 = _run("find CSV files larger than 100MB")
    assert (rc2, out2) == (0, "find . -name '*.csv' -size +100M")   # fresh


def test_unrelated_turn_replaces_frame(session_mode):
    _run("find CSV files larger than 100MB")
    _run("only the ones modified yesterday")
    rc, out = _run("find all json files")        # act=new → replace
    assert (rc, out) == (0, "find . -name '*.json'")
    # the frame no longer carries the csv/size/mtime of the old chain
    fr = session.load(session.store_key())
    assert fr is not None
    assert fr.targets.get("name") == "*.json"
    assert "size" not in fr.filters and "mtime" not in fr.filters


def test_count_them_operate(session_mode):
    _run("find CSV files larger than 100MB")
    rc, out = _run("count them")
    assert (rc, out) == (0, "find . -name '*.csv' -size +100M | wc -l")


def test_frame_and_reset_flags(session_mode):
    _run("find CSV files larger than 100MB")
    rc, out = _run("--frame")
    assert rc == 0 and '"name": "*.csv"' in out
    rc2, out2 = _run("--reset")
    assert rc2 == 0
    assert session.load(session.store_key()) is None


def test_non_find_request_falls_back_to_single_turn(session_mode):
    # A non-composable request in session mode behaves exactly like v1.
    rc, out = _run("what's my PATH")
    assert (rc, out) == (0, "echo $PATH")
