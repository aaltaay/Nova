"""Tests for tools/session_brief_hook.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "session_brief_hook.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_brief_hook", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["session_brief_hook"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hook():
    return _load()


def test_roadmap_next_parses_product_next_line(hook, tmp_path, monkeypatch):
    fake = tmp_path / "Nova-Roadmap-Status.md"
    fake.write_text(
        "# Status\n\n## Current position\n\n"
        "- **Product NEXT:** **Phase K -- short entry**, `[~]` IN PROGRESS.\n"
        "- **`auto_live`:** **NO-GO**\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hook, "ROADMAP_STATUS", fake)
    assert hook._roadmap_next() == "Phase K -- short entry, `[~]` IN PROGRESS."


def test_roadmap_next_parses_the_live_ledger(hook):
    """The retired `Active ops` regex passed its fixture while missing the real file."""
    assert hook._roadmap_next(), "Nova-Roadmap-Status.md has no `- **Product NEXT:**` line"


def test_build_brief_carries_the_next_move_seed(hook, monkeypatch):
    import next_moves

    monkeypatch.setattr(next_moves, "session_brief_lines", lambda: ["Next-move seed (as of t, source=live):", "- ship= K3"])
    brief = hook.build_brief()
    assert brief and "Next-move seed" in brief and "- ship= K3" in brief


def test_build_brief_fails_open_when_seed_raises(hook, monkeypatch):
    import next_moves

    def _boom():
        raise RuntimeError("gh down")

    monkeypatch.setattr(next_moves, "session_brief_lines", _boom)
    brief = hook.build_brief()
    assert brief and "Next-move seed: unavailable" in brief


def test_roadmap_next_missing_file(hook, tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "ROADMAP_STATUS", tmp_path / "does-not-exist.md")
    assert hook._roadmap_next() is None


def test_build_brief_real_repo_smoke(hook):
    brief = hook.build_brief()
    assert brief is None or "Nova fleet brief" in brief
    if brief:
        assert "Graphify meter:" in brief
        assert "Deferred" in brief
        assert "D-" in brief


def test_main_emits_additional_context(hook, monkeypatch, capsys):
    monkeypatch.setattr(hook, "build_brief", lambda: "sample brief text")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: "{}"})())
    assert hook.main([]) == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {"additional_context": "sample brief text"}


def test_main_claude_flag_emits_hook_specific_output(hook, monkeypatch, capsys):
    monkeypatch.setattr(hook, "build_brief", lambda: "sample brief text")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: "{}"})())
    assert hook.main(["--claude"]) == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "sample brief text",
        }
    }


def test_main_fail_open_when_brief_raises(hook, monkeypatch, capsys):
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(hook, "build_brief", _boom)
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: "{}"})())
    assert hook.main([]) == 0
    assert json.loads(capsys.readouterr().out.strip()) == {}


def test_main_tolerates_malformed_stdin(hook, monkeypatch, capsys):
    monkeypatch.setattr(hook, "build_brief", lambda: "sample brief text")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: "not-json"})())
    assert hook.main([]) == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {"additional_context": "sample brief text"}


def test_build_brief_includes_repo_hygiene_line(hook):
    brief = hook.build_brief()
    if brief:
        assert "Repo hygiene:" in brief
