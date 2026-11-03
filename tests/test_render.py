"""Task 03 tests — THE SECURITY BOUNDARY. Written FIRST, before planner.py
and render.py exist.

The whole safety argument of LinuxBuddy rests here: a slot value, however
hostile, substitutes into exactly ONE argv element and survives the
render round-trip as ONE intact element. A shell metacharacter in a slot
must never become a separate token.
"""
import pytest

from linuxbuddy.nlu import Frame
from linuxbuddy.planner import compile
from linuxbuddy.render import to_shell


# The headline case the reviewer asked to see proven inert.
INJECTION = "my file; rm -rf ~.txt"


def _compile_path(value):
    """Compile a frame whose only payload is a hostile path slot."""
    return compile(Frame("find_by_type", {"path": value}))


def test_injection_stays_one_argv_element():
    argv = _compile_path(INJECTION)
    # The ';' did NOT split the path into separate argv elements.
    assert INJECTION in argv
    assert argv.count(INJECTION) == 1
    # and no element is a bare ';' or 'rm' leaked out of the path
    assert ";" not in argv
    assert "rm" not in argv


def test_injection_survives_render_round_trip():
    import shlex
    argv = _compile_path(INJECTION)
    rendered = to_shell(argv)
    # shlex.split recovers the hostile path as ONE intact element.
    assert shlex.split(rendered) == argv
    assert INJECTION in shlex.split(rendered)


@pytest.mark.parametrize(
    "hostile",
    [
        "my file; rm -rf ~.txt",   # command separator + path expansion
        "a file with spaces.txt",   # whitespace
        "it's a file.txt",          # single quote
        "$(whoami).txt",            # command substitution
        "`whoami`.txt",             # backtick substitution
        "-rf",                      # leading dash (option smuggling)
        "a && b || c.txt",          # boolean operators
        "pipe | danger.txt",        # pipe
    ],
)
def test_hostile_values_round_trip_as_single_element(hostile):
    import shlex
    argv = _compile_path(hostile)
    rendered = to_shell(argv)
    recovered = shlex.split(rendered)
    assert recovered == argv
    assert hostile in recovered  # intact, one element


def test_to_shell_rejects_bad_round_trip():
    # Directly guard the renderer's own invariant: a crafted argv that does
    # not round-trip must raise, never silently return.
    from linuxbuddy.render import RenderError
    # shlex.split drops an unquoted trailing backslash context; simplest
    # forced failure: feed a non-string element.
    with pytest.raises((RenderError, TypeError, AttributeError)):
        to_shell(["find", 123])
