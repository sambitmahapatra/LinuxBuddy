"""Task 01 tests — the find knowledge base loader.

Written before the implementation (TDD, per CLAUDE.md).
"""
import pytest

from linuxbuddy.kb import load_kb, get_capability


FOUR_INTENTS = {"find_by_size", "find_by_time", "find_by_name", "find_by_type"}
# find_largest added in Task 19; find_smallest in Task 20.
SEARCH_INTENTS = FOUR_INTENTS | {"find_largest", "find_smallest",
                                 "find_recent", "count_files"}


def test_find_yaml_loads():
    kb = load_kb()
    assert "search_files" in kb


def test_four_intents_present():
    cap = get_capability("search_files")
    assert set(cap["intents"]) == SEARCH_INTENTS


def test_every_base_argv_is_list_of_strings():
    cap = get_capability("search_files")
    for name, intent in cap["intents"].items():
        base = intent["base_argv"]
        assert isinstance(base, list), f"{name} base_argv is not a list"
        assert base, f"{name} base_argv is empty"
        for elem in base:
            assert isinstance(elem, str), f"{name} base_argv has non-str {elem!r}"


def test_every_optional_fragment_is_list_of_strings():
    cap = get_capability("search_files")
    for name, intent in cap["intents"].items():
        for slot, fragment in intent.get("optional_args", {}).items():
            assert isinstance(fragment, list), f"{name}/{slot} fragment not a list"
            for elem in fragment:
                assert isinstance(elem, str), f"{name}/{slot} has non-str {elem!r}"


def test_placeholder_occupies_exactly_one_element():
    # Invariant: a {placeholder} must never share an argv element with a flag.
    # So an element that contains "{" must not also contain a space.
    cap = get_capability("search_files")
    for name, intent in cap["intents"].items():
        elems = list(intent["base_argv"])
        for fragment in intent.get("optional_args", {}).values():
            elems += fragment
        for elem in elems:
            if "{" in elem:
                assert " " not in elem, f"{name}: placeholder shares element: {elem!r}"


def test_get_capability_missing_raises_keyerror():
    with pytest.raises(KeyError):
        get_capability("nope")
