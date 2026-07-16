"""Tests for tools/create_nova_agent.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "create_nova_agent.py"


def _load():
    spec = importlib.util.spec_from_file_location("create_nova_agent", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["create_nova_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cna():
    return _load()


def _args(cna, **kwargs):
    # Build namespace via parser
    argv = [
        "--id",
        kwargs.get("id", "demo-agent"),
        "--title",
        kwargs.get("title", "Demo"),
        "--domain",
        kwargs.get("domain", "demo domain"),
    ]
    if kwargs.get("write"):
        argv.append("--write")
    if kwargs.get("home_section"):
        argv.append("--home-section")
    parser = __import__("argparse").ArgumentParser()
    # Reuse module main parser by calling scaffold through parse
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--mission", default="")
    p.add_argument("--permissions", default="")
    p.add_argument("--invoke", default="")
    p.add_argument("--canvas", default="")
    p.add_argument("--home-section", action="store_true")
    p.add_argument("--continuity-rule", default=None)
    p.add_argument("--continuity-waiver", default=None)
    p.add_argument("--write", action="store_true")
    return p.parse_args(argv)


def test_dry_run_no_files(cna, tmp_path, monkeypatch):
    monkeypatch.setattr(cna, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setattr(cna, "MEMORY_DIR", tmp_path / "memory")
    # Keep real registry for collision checks against existing ids — use unique id
    args = _args(cna, id="zz-demo-scaffold")
    result = cna.scaffold(args, write=False)
    assert result["ok"] is True
    assert result.get("dry_run") is True
    assert not (tmp_path / "agents" / "zz-demo-scaffold.md").exists()


def test_collision_with_existing_tester(cna):
    args = _args(cna, id="tester")
    result = cna.scaffold(args, write=False)
    assert result["ok"] is False
    assert any("already registered" in e for e in result["errors"])


def test_write_scaffold_and_contract_pass(cna, tmp_path, monkeypatch):
    agents = tmp_path / "agents"
    memory = tmp_path / "memory"
    system = tmp_path / "system"
    system.mkdir()
    agents.mkdir()
    memory.mkdir()

    # Minimal registry copy
    real_reg = json.loads(cna.REGISTRY_PATH.read_text(encoding="utf-8"))
    reg_path = system / "registry.json"
    reg_path.write_text(json.dumps(real_reg, indent=2), encoding="utf-8")

    monkeypatch.setattr(cna, "AGENTS_DIR", agents)
    monkeypatch.setattr(cna, "MEMORY_DIR", memory)
    monkeypatch.setattr(cna, "REGISTRY_PATH", reg_path)
    monkeypatch.setattr(cna, "SYSTEM_DIR", system)

    args = _args(cna, id="zz-demo-scaffold", write=True)
    result = cna.scaffold(args, write=True)
    assert result["ok"] is True, result
    assert (agents / "zz-demo-scaffold.md").is_file()
    assert (memory / "zz-demo-scaffold-memory.md").is_file()
    updated = json.loads(reg_path.read_text(encoding="utf-8"))
    assert any(a["name"] == "zz-demo-scaffold" for a in updated["agents"])

    # Rollback check: second write must refuse
    result2 = cna.scaffold(args, write=True)
    assert result2["ok"] is False


def test_invalid_canvas_name(cna, tmp_path, monkeypatch):
    monkeypatch.setattr(cna, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setattr(cna, "MEMORY_DIR", tmp_path / "memory")
    (tmp_path / "agents").mkdir()
    (tmp_path / "memory").mkdir()
    args = _args(cna, id="zz-bad-canvas")
    args.canvas = "agent-nova-evil.canvas.tsx"
    # validate_args uses args.canvas when not home_section
    args.home_section = False
    errors = cna.validate_args(args, cna.load_registry())
    assert any("invalid dedicated canvas" in e or "agent-nova" in e for e in errors)
