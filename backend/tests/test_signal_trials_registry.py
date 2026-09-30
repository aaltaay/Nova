"""The signal trials are pre-registered and frozen (ADR 041).

``knowledge/signal-trials.json`` fixes every trial's rule, population, metric,
sample and pass line before any data dated ``data_from`` or later is read. A
trial that changes after that is a new trial on new days, never an edit, so the
file is held to the hash it was registered with. The hash is over the canonical
JSON (sorted keys, no whitespace), so a line-ending change on checkout is not an edit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[2] / "knowledge" / "signal-trials.json"
REGISTERED_SHA256 = "2fbb7dce5c3476c80bc8786f2d02252e5edadba4ecf3de3bde81d322b2e3f8a0"
TRIAL_KEYS = {
    "id", "name", "role", "signal", "rule", "population", "primary_metric", "test", "sample", "pass",
    "reported_not_deciding", "on_pass", "on_fail", "in_sample",
}
ROLES = {"sell", "sell_bot_only", "buy_veto", "buy_warning"}


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_the_registry_is_the_one_registered():
    canonical = json.dumps(_registry(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    got = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert got == REGISTERED_SHA256, (
        "knowledge/signal-trials.json changed after it was registered (ADR 041). A trial is never edited: "
        "register a new trial, with a new id and a new data_from, in a new registry version."
    )


def test_every_trial_states_what_decides_it():
    reg = _registry()
    assert reg["schema_version"] == 1 and reg["frozen"] is True
    assert reg["data_from"] >= reg["registered_at"]
    ids = [t["id"] for t in reg["trials"]]
    assert ids == ["T1", "T2", "T3", "T4", "T5", "T6"]
    for trial in reg["trials"]:
        assert set(trial) == TRIAL_KEYS, trial["id"]
        assert trial["role"] in ROLES, trial["id"]
        assert trial["pass"] and trial["sample"] and trial["on_pass"] and trial["on_fail"], trial["id"]
        assert any("Holm" in line for line in trial["pass"]), f"{trial['id']} is not read under the family-wise rule"


def test_no_trial_lets_nova_act_on_live():
    reg = _registry()
    assert "never buys or sells on Live by itself" in reg["note"]
    for trial in reg["trials"]:
        on_pass = trial["on_pass"]
        assert "Live" not in on_pass or "a call only" in on_pass, trial["id"]
