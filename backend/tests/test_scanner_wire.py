"""Wire-safe socket JSON (QA C32): a bare NaN token drops the whole browser frame."""
from __future__ import annotations

import json
import math

import pytest

from scanner_wire import dumps_wire, wire_safe


def test_non_finite_floats_become_null_at_any_depth():
    payload = {
        "type": "initial",
        "alerts": [{"rvol": math.nan, "gap_pct": -math.inf, "price": 1.5, "ids": ("a", math.inf)}],
        "total": 1,
    }
    text = dumps_wire(payload)
    assert "NaN" not in text and "Infinity" not in text
    back = json.loads(text)
    assert back["alerts"][0] == {"rvol": None, "gap_pct": None, "price": 1.5, "ids": ["a", None]}


def test_clean_payloads_are_returned_as_is():
    clean = {"a": [1, 2.5, "x"], "b": {"c": None}}
    assert wire_safe(clean) is clean
    assert dumps_wire(clean) == json.dumps(clean)


def test_plain_json_dumps_would_have_emitted_nan():
    # The regression this guards: json.dumps writes a token JSON.parse refuses.
    assert "NaN" in json.dumps({"rvol": math.nan})
    with pytest.raises(ValueError):
        json.dumps({"rvol": math.nan}, allow_nan=False)
