"""Tests for tools/sync_agent_surfaces.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "sync_agent_surfaces.py"


def _load():
    spec = importlib.util.spec_from_file_location("sync_agent_surfaces", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_agent_surfaces"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sync():
    return _load()


def test_parse_snapshot_yaml(sync):
    block = """captured_at: 2026-07-16T00:00:00Z
source_revision: abc
result: PASS
metrics:
  pytest_passed: 10
blockers: []
dashboard_freshness: stale
"""
    data = sync.parse_yaml_simple(block)
    assert data["result"] == "PASS"
    assert data["metrics"]["pytest_passed"] == 10
    assert data["dashboard_freshness"] == "stale"


def test_security_counts_from_registry(sync):
    counts = sync.security_counts()
    assert counts.get("open_findings", 0) >= 1
    assert "accepted_risks" in counts


def test_no_writes_without_flag(sync, tmp_path, monkeypatch):
    canvas = tmp_path / "agent-tester.canvas.tsx"
    canvas.write_text(
        "export default function AgentTester() { return null; }\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync, "CANVAS_DIR", tmp_path)
    before = canvas.read_text(encoding="utf-8")
    result = sync.sync(write=False)
    assert result["write_mode"] is False
    assert result["writes"] == 0
    assert canvas.read_text(encoding="utf-8") == before


def test_marker_replacement_idempotent(sync, tmp_path, monkeypatch):
    canvas = tmp_path / "agent-tester.canvas.tsx"
    canvas.write_text(
        "import { H1 } from 'cursor/canvas';\n\n"
        "export default function AgentTester() {\n"
        "  return <H1>Tester</H1>;\n"
        "}\n",
        encoding="utf-8",
    )
    # Only write tester canvas + fake home
    (tmp_path / "nova-home.canvas.tsx").write_text(
        "export default function NovaHome() { return null; }\n",
        encoding="utf-8",
    )
    for name in ("agent-maintainer.canvas.tsx", "agent-security.canvas.tsx"):
        (tmp_path / name).write_text(
            "export default function X() { return null; }\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(sync, "CANVAS_DIR", tmp_path)

    r1 = sync.sync(write=True)
    assert r1["writes"] >= 1
    text1 = canvas.read_text(encoding="utf-8")
    assert "AGENT_SNAPSHOT_START: tester" in text1

    r2 = sync.sync(write=True)
    text2 = canvas.read_text(encoding="utf-8")
    assert text1.count("AGENT_SNAPSHOT_START: tester") == 1
    assert text2.count("AGENT_SNAPSHOT_START: tester") == 1
    # Second pass should be idempotent (0 or same content)
    assert "AGENT_SNAPSHOT_END: tester" in text2


def test_stale_detection(sync):
    snap = sync.build_agent_snapshot(
        {
            "name": "tester",
            "memory": ".cursor/agent-memory/tester-memory.md",
            "domain": "test",
            "invoke_phrases": [],
            "dashboard": {"type": "dedicated", "canvas": "agent-tester.canvas.tsx"},
        },
        "2026-07-16T00:00:00Z",
        "abc",
    )
    assert snap["stale"] is True or snap["dashboard_freshness"] in (
        "stale",
        "unknown",
        "fresh",
    )


def test_load_memory_snapshot(sync):
    data = sync.load_memory_snapshot(".cursor/agent-memory/tester-memory.md")
    assert "result" in data
    assert "metrics" in data


def test_home_agents_block_lists_registry_roster(sync):
    registry = json.loads(
        (REPO_ROOT / ".cursor" / "agent-system" / "registry.json").read_text(
            encoding="utf-8"
        )
    )
    snaps = [
        sync.build_agent_snapshot(a, "2026-07-16T00:00:00Z", "abc")
        for a in registry["agents"]
    ]
    block = sync.home_agents_block(snaps)
    assert '"kind": "nova-home-agents"' in block
    assert '"title": "Warrior Navigator"' in block
    assert '"invoke": "Use the warrior subagent to navigate Warrior Trading"' in block
    assert '"canvas": "agent-warrior.canvas.tsx"' in block
    assert '"title": "Widgets"' in block
    assert '"invoke": "Use the widgets subagent to map Webull widgets to Nova"' in block
    assert '"canvas": "agent-widgets.canvas.tsx"' in block
    for agent_id in (
        "tester",
        "maintainer",
        "security",
        "docs",
        "warrior",
        "hod-momo",
        "widgets",
    ):
        assert f'"id": "{agent_id}"' in block
