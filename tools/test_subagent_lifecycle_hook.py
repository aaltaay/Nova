"""Tests for tools/subagent_lifecycle_hook.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "subagent_lifecycle_hook.py"


def _load():
    spec = importlib.util.spec_from_file_location("subagent_lifecycle_hook", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["subagent_lifecycle_hook"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hook():
    return _load()


def test_non_nova_agent_noop(hook):
    out = hook.handle_payload(
        {
            "subagent_type": "generalPurpose",
            "status": "completed",
            "summary": "done",
            "loop_count": 0,
        }
    )
    assert out == {}


def test_missing_footer_followup(hook):
    out = hook.handle_payload(
        {
            "subagent_type": "tester",
            "status": "completed",
            "summary": "## Test report\n- **Result:** PASS\n",
            "loop_count": 0,
        }
    )
    assert "followup_message" in out
    assert "Lifecycle" in out["followup_message"]


def test_present_footer_noop(hook):
    out = hook.handle_payload(
        {
            "subagent_type": "tester",
            "status": "completed",
            "summary": (
                "## Test report\n"
                "**Lifecycle:** memory=unchanged | promotion=none | "
                "dashboard=clean | handoff=none | task_log=n/a | problem_log=n/a\n"
            ),
            "loop_count": 0,
        }
    )
    assert out == {}


def test_footer_missing_problem_log_followup(hook):
    out = hook.handle_payload(
        {
            "subagent_type": "tester",
            "status": "completed",
            "summary": (
                "## Test report\n"
                "**Lifecycle:** memory=unchanged | promotion=none | "
                "dashboard=clean | handoff=none | task_log=n/a\n"
            ),
            "loop_count": 0,
        }
    )
    assert "followup_message" in out
    assert "problem_log" in out["followup_message"]


def test_error_status_noop(hook):
    out = hook.handle_payload(
        {
            "subagent_type": "tester",
            "status": "error",
            "summary": "boom",
            "loop_count": 0,
        }
    )
    assert out == {}


def test_loop_guard(hook):
    out = hook.handle_payload(
        {
            "subagent_type": "tester",
            "status": "completed",
            "summary": "no footer",
            "loop_count": 1,
        }
    )
    assert out == {}


def test_malformed_input_fail_open(hook):
    # handle_payload tolerates weird shapes via main(); direct call with bad types
    out = hook.handle_payload({"status": "completed", "loop_count": "x"})
    assert out == {}


def test_main_fail_open_on_bad_json(hook, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: "not-json"})())
    assert hook.main() == 0
    assert json.loads(capsys.readouterr().out.strip()) == {}
