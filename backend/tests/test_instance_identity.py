"""Per-process identity snapshot used by /api/health, /livez, /readyz."""
from __future__ import annotations

import instance_identity


def test_snapshot_shape_and_matches_module_constants():
    snap = instance_identity.snapshot()
    assert snap == {
        "instance_id": instance_identity.INSTANCE_ID,
        "pid": instance_identity.PID,
        "parent_pid": instance_identity.PARENT_PID,
        "started_at": instance_identity.STARTED_AT,
        "reload": instance_identity.RELOAD_ENABLED,
    }
    assert isinstance(snap["instance_id"], str) and len(snap["instance_id"]) == 12


def test_instance_id_stable_within_process():
    first = instance_identity.snapshot()["instance_id"]
    second = instance_identity.snapshot()["instance_id"]
    assert first == second
