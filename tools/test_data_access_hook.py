"""The raw-data tripwire (``tools/data_access_hook.py``, ADR 059): an agent's own reader of the operator's stores is
blocked and pointed at the front door; the front door, repo code, code searches and a stated reason pass."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_access_hook as hook  # noqa: E402


def test_naming_a_raw_store_is_blocked():
    for command in (r"py -3 -c ""import sqlite3; sqlite3.connect('E:/Nova/massive/movers/day_movers.sqlite3')""",
                    r"Get-Content E:\Nova\massive\store\reference\float.jsonl",
                    "python - < x  # opens F:/Nova/catalysts/edgar/companyfacts.zip"):
        assert hook.shell_verdict(command), command


def test_the_front_door_repo_code_and_a_stated_reason_pass():
    assert hook.shell_verdict(r"py -3 tools/market_data.py scan high_min=50") is None
    assert hook.shell_verdict(r"py -3 research/movers/build_movers.py") is None
    assert hook.shell_verdict(r"Get-Item E:\Nova\massive\movers\day_movers.sqlite3  # raw-data-ok: file size") is None
    assert hook.shell_verdict("git status") is None and hook.shell_verdict("npm test") is None


def test_a_code_search_passes_unless_it_reads_a_data_folder():
    assert hook.shell_verdict('rg "day_movers.sqlite3" backend/') is None
    assert hook.shell_verdict(r'rg "GURE" E:\Nova\massive\store') is not None


def test_an_ad_hoc_script_outside_the_repo_is_read_and_checked(tmp_path):
    raw = tmp_path / "cov.py"
    raw.write_text("DB = 'file:E:/Nova/massive/movers/day_movers.sqlite3?mode=ro'\n", encoding="utf-8")
    clean = tmp_path / "plot.py"
    clean.write_text("print('hi')\n", encoding="utf-8")
    assert "cov.py" in hook.shell_verdict(f'py -3 "{raw}"')
    assert hook.shell_verdict(f"py -3 {clean}") is None


def test_each_client_gets_its_own_verdict_shape():
    raw = {"command": "type E:/Nova/massive/store/reference/float.jsonl"}
    assert hook.decide("cursor-shell", raw)["permission"] == "deny"
    assert hook.decide("cursor-shell", {"command": "git log"}) == {"permission": "allow"}
    claude = hook.decide("claude", {"tool_name": "Bash", "tool_input": raw})
    assert claude["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert hook.decide("claude", {"tool_name": "Read", "tool_input": {"file_path": "README.md"}}) == {}


def test_unreadable_input_fails_open(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    assert hook.main(["--client", "cursor-shell"]) == 0
    assert json.loads(capsys.readouterr().out) == {"permission": "allow"}
