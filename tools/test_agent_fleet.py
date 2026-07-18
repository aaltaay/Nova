"""Tests for tools/agent_fleet.py."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "agent_fleet.py"


def _load():
    # sync_agent_surfaces must be importable under its real name first so
    # agent_fleet's `from sync_agent_surfaces import ...` resolves cleanly.
    sync_spec = importlib.util.spec_from_file_location(
        "sync_agent_surfaces", REPO_ROOT / "tools" / "sync_agent_surfaces.py"
    )
    sync_mod = importlib.util.module_from_spec(sync_spec)
    sys.modules["sync_agent_surfaces"] = sync_mod
    sync_spec.loader.exec_module(sync_mod)

    spec = importlib.util.spec_from_file_location("agent_fleet", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_fleet"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fleet():
    return _load()


def test_parse_backlog_stops_at_completed(fleet, tmp_path, monkeypatch):
    mem = tmp_path / "x-memory.md"
    mem.write_text(
        "## Backlog\n\n"
        "- [ ] first open item\n"
        "- [ ] second open item\n"
        "- [x] already done (ignored, checked)\n\n"
        "### Completed\n\n"
        "- [ ] should not count — past the Completed boundary\n\n"
        "## Run log\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fleet, "REPO_ROOT", tmp_path)
    items = fleet.parse_backlog("x-memory.md")
    assert items == ["first open item", "second open item"]


def test_parse_fleet_map_table_finds_owned_and_continuity(fleet):
    rows = fleet.parse_fleet_map_table("Domain ownership")
    assert rows, "expected at least one parsed domain row"
    statuses = {r["Status"] for r in rows}
    assert "Owned" in statuses
    assert "Continuity-only" in statuses
    assert any(
        r["Domain"] == "News / catalyst pipeline" and r["Owner"] == "news"
        for r in rows
    )
    assert any(r["Domain"] == "Fleet dispatch / orchestration" and r["Owner"] == "daddy" for r in rows)


def test_parse_fleet_map_table_skills(fleet):
    rows = fleet.parse_fleet_map_table("Skill ownership")
    assert any(
        r["Skill"] == "backtest" and r["Status"] == "Owned" and r["Owner"] == "backtester"
        for r in rows
    )


def test_find_unmanaged_canvases_flags_stray_file(fleet, tmp_path, monkeypatch):
    (tmp_path / "agent-tester.canvas.tsx").write_text("x", encoding="utf-8")
    (tmp_path / "agent-mystery.canvas.tsx").write_text("x", encoding="utf-8")
    (tmp_path / "nova-home.canvas.tsx").write_text("x", encoding="utf-8")
    (tmp_path / "context-usage-abc.canvas.tsx").write_text("x", encoding="utf-8")
    monkeypatch.setattr(fleet, "CANVAS_DIR", tmp_path)
    registry = {
        "agents": [
            {"dashboard": {"canvas": "agent-tester.canvas.tsx"}},
        ]
    }
    cracks = fleet.find_unmanaged_canvases(registry)
    subjects = {c.subject for c in cracks}
    assert subjects == {"agent-mystery.canvas.tsx"}


def test_find_missing_titles(fleet, monkeypatch):
    monkeypatch.setattr(fleet, "AGENT_TITLES", {"tester": "Tester"})
    registry = {"agents": [{"id": "tester"}, {"id": "ghost-agent"}]}
    cracks = fleet.find_missing_titles(registry)
    assert [c.subject for c in cracks] == ["ghost-agent"]


def test_stale_snapshot_detection(fleet):
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    registry = {
        "agents": [
            {"id": "tester", "memory": ".cursor/agent-memory/tester-memory.md"}
        ]
    }
    cracks = fleet.find_stale_snapshots(registry, now)
    assert any(c.kind == "stale_snapshot" and c.subject == "tester" for c in cracks)


def test_build_report_has_expected_shape(fleet):
    report = fleet.build_report()
    assert report["agents"] >= 7
    assert report["crack_count"] == len(report["cracks"])
    assert isinstance(report["open_backlog_by_agent"], dict)
    for crack in report["cracks"]:
        assert crack["kind"] in (
            "stale_snapshot",
            "open_blocker",
            "unowned_domain",
            "orphan_skill",
            "unmanaged_canvas",
            "missing_title",
        )
        assert crack["severity"] in ("structural", "blocker", "stale", "info")


def test_build_session_brief_limits_top_n(fleet):
    report = fleet.build_report()
    brief = fleet.build_session_brief(report, top_n=2)
    assert len(brief["top_cracks"]) <= 2
    assert brief["crack_count"] == report["crack_count"]


def test_main_json_smoke(fleet, capsys):
    rc = fleet.main(["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert '"crack_count"' in captured.out
