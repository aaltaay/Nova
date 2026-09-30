"""The second signal-trials registry version is pre-registered and frozen (ADR 041, amendment 2026-09-30).

``knowledge/signal-trials-2.json`` holds the trials registered after ``signal-trials.json`` was frozen
(T7, Room under 2R: the day's levels, ADR 036 amendment 2026-09-30). It is held to the hash it was
registered with, over the canonical JSON (sorted keys, no whitespace), exactly as the first version is.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

KNOWLEDGE = Path(__file__).resolve().parents[2] / "knowledge"
REGISTRY = KNOWLEDGE / "signal-trials-2.json"
FIRST = KNOWLEDGE / "signal-trials.json"
REGISTERED_SHA256 = "b99f69821425e1b6c8d84caff0824df2b17cdd4241565c53b532fcfbb7857e04"
TRIAL_KEYS = {
    "id", "name", "role", "signal", "rule", "population", "primary_metric", "test", "sample", "pass",
    "reported_not_deciding", "on_pass", "on_fail", "in_sample",
}
ROLES = {"sell", "sell_bot_only", "buy_veto", "buy_warning"}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_second_registry_is_the_one_registered():
    canonical = json.dumps(_read(REGISTRY), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    got = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert got == REGISTERED_SHA256, (
        "knowledge/signal-trials-2.json changed after it was registered (ADR 041). A trial is never edited: "
        "register a new trial, with a new id and a new data_from, in a new registry version."
    )


def test_it_follows_the_first_and_reuses_no_id():
    reg, first = _read(REGISTRY), _read(FIRST)
    assert reg["schema_version"] == 1 and reg["frozen"] is True and reg["version"] == 2
    assert reg["follows"] == "knowledge/signal-trials.json" and reg["registry"] == first["registry"]
    assert reg["data_from"] > reg["registered_at"] >= first["registered_at"]
    ids = [t["id"] for t in reg["trials"]]
    assert ids == ["T7"] and not set(ids) & {t["id"] for t in first["trials"]}


def test_every_trial_states_what_decides_it_and_none_acts_on_live():
    reg = _read(REGISTRY)
    assert "never buys or sells on Live by itself" in reg["note"]
    for trial in reg["trials"]:
        assert set(trial) == TRIAL_KEYS, trial["id"]
        assert trial["role"] in ROLES, trial["id"]
        assert trial["pass"] and trial["sample"] and trial["on_pass"] and trial["on_fail"], trial["id"]
        assert any("Holm" in line for line in trial["pass"]), f"{trial['id']} is not read under the family-wise rule"
        assert "Live" not in trial["on_pass"], trial["id"]
