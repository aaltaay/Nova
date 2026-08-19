from __future__ import annotations

from ibkr import gateway_trail as trail


def test_append_and_recent_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    trail.append_event(
        actor="operator",
        event="click",
        requested="live",
        kind_before="paper",
        plan="force_ibc",
    )
    trail.append_event(
        actor="ibkr",
        event="attached",
        requested="live",
        kind_after="live",
        switched=True,
    )
    rows = trail.recent(limit=10)
    assert len(rows) == 2
    assert rows[0]["event"] == "click"
    assert rows[0]["actor"] == "operator"
    assert rows[0]["schema_version"] == trail.SCHEMA_VERSION
    assert rows[1]["event"] == "attached"
    assert rows[1]["switched"] is True


def test_recent_returns_oldest_first_and_caps(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    for i in range(5):
        trail.append_event(actor="operator", event="click", requested="paper", note=str(i))
    rows = trail.recent(limit=3)
    assert [r["note"] for r in rows] == ["2", "3", "4"]


def test_corrupt_line_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    path = trail.trail_path()
    path.write_text("not-json\n", encoding="utf-8")
    trail.append_event(actor="ibkr", event="refused", requested="live", kind_after="paper", switched=False)
    rows = trail.recent()
    assert len(rows) == 1
    assert rows[0]["event"] == "refused"
    assert rows[0]["switched"] is False
