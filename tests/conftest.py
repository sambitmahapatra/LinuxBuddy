"""Shared test fixtures / hygiene.

Multi-turn mode is opt-in via ``$LINUXBUDDY_SESSION`` (the shell widget exports
it per terminal). The owner runs pytest from a bash shell where that export is
live, which used to make the single-turn CLI tests route through the session
path and fail spuriously (the very environment that hid the Task-33 bug). Make
every test start from a clean, single-turn baseline; session tests opt back in
by setting the var explicitly (via ``monkeypatch.setenv``), which runs after
this autouse fixture, so they are unaffected.
"""
import pytest


@pytest.fixture(autouse=True)
def _single_turn_by_default(monkeypatch):
    monkeypatch.delenv("LINUXBUDDY_SESSION", raising=False)
