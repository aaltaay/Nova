"""Unit tests for tools/nova_docs_inventory.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "nova_docs_inventory.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("nova_docs_inventory", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nova_docs_inventory"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def inv():
    return _load_module()


def test_classify_preferred_home(inv):
    assert inv.classify_canvas_name("nova-home.canvas.tsx") == "preferred_home"


def test_classify_preferred_agent(inv):
    assert inv.classify_canvas_name("agent-security.canvas.tsx") == "preferred_agent"
    assert inv.classify_canvas_name("agent-tester.canvas.tsx") == "preferred_agent"


def test_classify_system(inv):
    assert (
        inv.classify_canvas_name(
            "context-usage-f2b38b1a-e2f6-428f-b28b-6aac54b278ef.canvas.tsx"
        )
        == "system"
    )


def test_classify_unmanaged(inv):
    assert inv.classify_canvas_name("nova-security-audit.canvas.tsx") == "unmanaged"
    assert inv.classify_canvas_name("random-board.canvas.tsx") == "unmanaged"


def test_inventory_canvases_tmp(inv, tmp_path: Path):
    (tmp_path / "nova-home.canvas.tsx").write_text("export default function X(){return null}", encoding="utf-8")
    (tmp_path / "agent-tester.canvas.tsx").write_text("export default function X(){return null}", encoding="utf-8")
    (tmp_path / "context-usage-abc.canvas.tsx").write_text("export default function X(){return null}", encoding="utf-8")
    (tmp_path / "nova-security-audit.canvas.tsx").write_text("export default function X(){return null}", encoding="utf-8")

    preferred, system, unmanaged = inv.inventory_canvases(tmp_path)
    assert {e.name for e in preferred} == {"nova-home.canvas.tsx", "agent-tester.canvas.tsx"}
    assert {e.name for e in system} == {"context-usage-abc.canvas.tsx"}
    assert {e.name for e in unmanaged} == {"nova-security-audit.canvas.tsx"}


def test_build_report_jsonable(inv, tmp_path: Path, monkeypatch):
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    (fake_repo / "docs").mkdir()
    (fake_repo / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    canvases = tmp_path / "canvases"
    canvases.mkdir()
    (canvases / "nova-home.canvas.tsx").write_text("x", encoding="utf-8")

    monkeypatch.setattr(inv, "REPO_ROOT", fake_repo)
    report = inv.build_report(canvases_dir=canvases, repo_root=fake_repo)
    payload = inv.to_jsonable(report)
    assert payload["doc_roots_present"] == ["docs"]
    assert "AGENTS.md" in payload["doc_root_files_present"]
    assert payload["preferred"][0]["name"] == "nova-home.canvas.tsx"
    # Ensure JSON serializable
    json.dumps(payload)


def test_main_fail_on_unmanaged(inv, tmp_path: Path):
    canvases = tmp_path / "canvases"
    canvases.mkdir()
    (canvases / "orphan.canvas.tsx").write_text("x", encoding="utf-8")
    code = inv.main(["--canvases-dir", str(canvases), "--fail-on-unmanaged", "--json"])
    assert code == 1
