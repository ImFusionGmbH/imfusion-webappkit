"""Check the Python half of the canonical key against the shared table.

The recorder writes edge keys and the browser looks them up, so the two
implementations have to agree character for character. Both are checked against
the same fixture, which lives beside the TypeScript it also feeds: this module
covers `canonical.py`, and ``static/src/static-demo/canonical.test.ts`` covers
its mirror. A change to either one that the other does not follow fails here.
"""

import json
from pathlib import Path

import pytest

import imfusion_webappkit
from imfusion_webappkit.static_demo.canonical import (
    app_only_action_names,
    canonical_json,
    edge_key,
)

FIXTURE = (
    Path(imfusion_webappkit.__file__).parent
    / "static"
    / "src"
    / "static-demo"
    / "edgeKeys.fixture.json"
)
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_edge_key_matches_the_shared_table(case):
    assert edge_key(case["type"], case["data"], case["app_only"]) == case["key"]


def test_unrecordable_message_types_are_rejected():
    with pytest.raises(ValueError, match="cannot be recorded"):
        edge_key("selection_changed", {"indices": [0]})


def test_canonical_json_matches_json_stringify():
    assert (
        canonical_json({"b": 1, "a": [2, {"d": 4, "c": 3}]})
        == '{"a":[2,{"c":3,"d":4}],"b":1}'
    )


def test_non_finite_numbers_are_refused():
    with pytest.raises(ValueError, match="finite"):
        canonical_json({"value": float("nan")})


def test_app_only_action_names_reads_the_descriptors():
    descriptors = [
        {"name": "Reset", "is_app_only": True},
        {"name": "Threshold", "is_app_only": False},
        {"name": "Clear"},
    ]
    assert app_only_action_names(descriptors) == {"Reset"}
