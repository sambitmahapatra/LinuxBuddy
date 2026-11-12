"""Task 42 (workstream #1a) — the rules coverage-check.

A bare filename must NOT hijack a request into a `find -name <file>` / `grep
<token>` when the user actually asked for some other operation the rules can't
route. The rules must abstain (or route to the correct domain) instead, so the
encoder fallback — or an honest abstain — handles it, never a confident wrong
command.  See v2_remaining_proposal.md #1 and the 587-dogfood MISROUTE class.
"""
import pytest

from linuxbuddy import nlu


# --- The filename-hijacks. At HEAD these emitted `find -name <file>` / a spurious
# grep at exit 0. The coverage-check must stop that: either abstain (rules return
# None → the encoder/honest-abstain seam takes over) or route to the *correct*
# domain. In no case may the result be the old find_by_name/search-on-a-filename.
HIJACK_ABSTAIN = [
    "stat notes.txt",                 # inspection verb the rules don't route
    "execute src/utils.py",           # run a script
    "identify model.pkl",             # detect type
    "give me file info for README.md",
    "what are the file details of README.md?",
]

# These now route to their CORRECT domain instead of the grep hijack, because
# text_and_logs no longer reads a filename as an all-caps / log-word pattern.
HIJACK_REROUTE = {
    "delete error.log": "delete_file",
    "arrange the lines of README.md in order": "sort_lines",
}


@pytest.mark.parametrize("text", HIJACK_ABSTAIN)
def test_hijack_now_abstains(text):
    frame = nlu.parse(text)
    assert frame is None, (
        f"{text!r} should abstain (→ encoder), got {frame}")


@pytest.mark.parametrize("text,intent", HIJACK_REROUTE.items())
def test_hijack_now_routes_correctly(text, intent):
    frame = nlu.parse(text)
    assert frame is not None and frame.intent == intent, (
        f"{text!r} should route to {intent}, got {frame}")
    # and specifically NOT the grep hijack
    assert frame.intent not in {"find_by_name", "search_in_file", "search_recursive"}


# --- The guard-rail: genuine discovery/search is UNREGRESSED. Each of these has a
# real discovery cue, so the coverage-check passes and the command is unchanged.
DISCOVERY_OK = {
    "find report.csv": "find_by_name",
    "where is config.yaml": "find_by_name",
    "find a file called report.csv": "find_by_name",
    "look for a file named sales.csv": "find_by_name",
    "how many csv files": "count_files",
    "search for TODO in notes.txt": "search_in_file",
    "find all the python files": "find_by_type",
    "list the json files": "find_by_type",
    "which files are over 100mb": "find_by_size",
    "files modified in the last 7 days": "find_by_time",
}


@pytest.mark.parametrize("text,intent", DISCOVERY_OK.items())
def test_genuine_discovery_unregressed(text, intent):
    frame = nlu.parse(text)
    assert frame is not None and frame.intent == intent, (
        f"genuine discovery {text!r} should still emit {intent}, got {frame}")


def test_discovery_requested_helper():
    # positive: discovery verbs / plural files / glob / size / time
    # (standalone time phrasings pass via the plural "files" cue, tested in
    # DISCOVERY_OK; the size cue has its own branch, checked here.)
    for t in ["find x", "where is x", "locate x", "search for x", "how many x",
              "list the files", "the csv files", "*.py", "over 100mb",
              "a file named x", "called x.txt"]:
        assert nlu._discovery_requested(t, t.lower()), t
    # negative: a bare operation + filename, no discovery evidence
    for t in ["stat notes.txt", "run main.py", "delete it", "identify model.pkl",
              "print the file"]:
        assert not nlu._discovery_requested(t, t.lower()), t
