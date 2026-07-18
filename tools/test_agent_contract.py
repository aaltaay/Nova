"""Tests for tools/agent_contract.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "agent_contract.py"


def _load():
    spec = importlib.util.spec_from_file_location("agent_contract", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_contract"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ac():
    return _load()


def test_current_repo_passes(ac):
    errors = ac.run_validation(ci=True)
    assert errors == [], errors


def test_discovery_finds_registered_agents(ac):
    names = {p.stem for p in ac.discover_agent_files()}
    assert names == {
        "tester",
        "maintainer",
        "security",
        "docs",
        "warrior",
        "hod-momo",
        "widgets",
        "router",
        "execution",
        "ibkr-ops",
        "backtester",
        "market-feed",
        "news",
        "daddy",
    }


def test_unregistered_agent_fails(ac, tmp_path, monkeypatch):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "ghost.md").write_text(
        "---\nname: ghost\n---\n\n## Mission\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ac, "AGENTS_DIR", agents)
    monkeypatch.setattr(ac, "MEMORY_DIR", tmp_path / "memory")
    (tmp_path / "memory").mkdir()
    # Keep real registry so ghost is unregistered
    errors = ac.run_validation(ci=True)
    assert any("unregistered" in e for e in errors)


def test_orphan_memory_fails(ac, tmp_path, monkeypatch):
    mem = tmp_path / "memory"
    mem.mkdir()
    # Copy real memories? Simpler: point MEMORY_DIR at temp with orphan only
    # and keep agents dir empty of extras — use real agents + temp memory with orphan
    monkeypatch.setattr(ac, "MEMORY_DIR", mem)
    # No registered memories present → each real registry memory missing + orphan
    (mem / "orphan-memory.md").write_text("# orphan\n", encoding="utf-8")
    errors = ac.run_validation(ci=True)
    assert any("orphan memory" in e for e in errors)


def test_malformed_frontmatter_fails(ac, tmp_path, monkeypatch):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "tester.md").write_text("# no frontmatter\n", encoding="utf-8")
    monkeypatch.setattr(ac, "AGENTS_DIR", agents)
    errors = ac.run_validation(ci=True)
    assert any("frontmatter" in e for e in errors)


def test_duplicate_invoke_phrase_detected(ac):
    registry = {
        "agents": [
            {"name": "a", "invoke_phrases": ["Use the foo agent"]},
            {"name": "b", "invoke_phrases": ["Use the foo agent"]},
        ]
    }
    errors = ac.validate_duplicate_phrases(registry)
    assert len(errors) == 1


def test_missing_section_detected(ac):
    text = "---\nname: x\n---\n\n## Mission\n\nok\n"
    assert ac.has_section(text, "Mission")
    assert not ac.has_section(text, "Hard constraints")


def test_invalid_dashboard_dedicated_prefix(ac):
    contract = ac.load_json(ac.CONTRACT_PATH)
    naming = contract["dashboard_naming"]
    assert naming["dedicated_prefix"] == "agent-"
    assert "docs" in naming["home_exception_agents"]


def test_continuity_waiver_accepted_for_tester(ac):
    registry = ac.load_json(ac.REGISTRY_PATH)
    tester = next(a for a in registry["agents"] if a["name"] == "tester")
    assert tester.get("continuity_waiver")
    assert tester.get("continuity_rule") is None


def test_broken_command_path_flagged(ac, monkeypatch):
    registry = ac.load_json(ac.REGISTRY_PATH)
    registry_map = ac.registry_by_name(registry)
    # Point tester check at missing script
    registry_map["tester"]["deterministic_checks"] = [
        "py -3 tools/does_not_exist_xyz.py"
    ]
    path = ac.AGENTS_DIR / "tester.md"
    contract = ac.load_json(ac.CONTRACT_PATH)
    errors = ac.validate_agent(path, contract, registry_map, ci=True)
    assert any("does_not_exist_xyz.py" in e for e in errors)
