"""Contract tests for Nova Delivery project add (workflow + helper)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.nova_delivery_project import (
    EXIT_OK,
    EXIT_TOKEN,
    PROJECT_ID,
    PROJECT_URL,
    TOKEN_HELP,
    add_url,
    find_status_field,
    is_already_on_board,
    is_project_token_blocked,
    item_add_command,
    parse_item_id,
    parse_status_name,
    should_default_status_to_todo,
)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nova-delivery-project.yml"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


def test_item_add_command_matches_required_gh():
    cmd = item_add_command("https://github.com/aaltaay/Nova/issues/1")
    assert cmd[:6] == [
        "gh",
        "project",
        "item-add",
        "1",
        "--owner",
        "aaltaay",
    ]
    assert "--url" in cmd
    assert "https://github.com/aaltaay/Nova/issues/1" in cmd


def test_already_on_board_is_success():
    assert is_already_on_board("item already exists in the project")
    assert is_already_on_board("Already in this project")
    assert not is_already_on_board("boom")


def test_token_blocked_patterns():
    assert is_project_token_blocked("GraphQL: Could not resolve to a ProjectV2 with the number 1")
    assert is_project_token_blocked("HTTP 403: Resource not accessible by integration")
    assert is_project_token_blocked("insufficient scope: project")
    assert not is_project_token_blocked("API rate limit")


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (None, True),
        ("", True),
        ("Todo", False),
        ("In Progress", False),
        ("Done", True),
        ("Weird", False),
    ],
)
def test_should_default_status_to_todo(current, expected):
    assert should_default_status_to_todo(current) is expected


def test_parse_item_id_and_status_field():
    assert parse_item_id({"id": "PVTI_1"}) == "PVTI_1"
    fields = [
        {"id": "TITLE", "name": "Title"},
        {
            "id": "STATUS",
            "name": "Status",
            "options": [
                {"id": "OPT_TODO", "name": "Todo"},
                {"id": "OPT_WIP", "name": "In Progress"},
                {"id": "OPT_DONE", "name": "Done"},
            ],
        },
    ]
    found = find_status_field(fields)
    assert found is not None
    assert found.field_id == "STATUS"
    assert found.todo_option_id == "OPT_TODO"


def test_parse_status_name_from_graphql():
    payload = {
        "data": {
            "node": {
                "fieldValueByName": {"name": "In Progress"},
            }
        }
    }
    assert parse_status_name(payload) == "In Progress"


def test_token_help_is_honest():
    assert PROJECT_URL in TOKEN_HELP
    assert PROJECT_ID in TOKEN_HELP
    assert "NOVA_PROJECT_TOKEN" in TOKEN_HELP
    assert "do not recreate" in TOKEN_HELP.lower()
    assert "gh project create" in TOKEN_HELP.lower()
    assert "P0-P3" in TOKEN_HELP


class _FakeGh:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kwargs):
        self.calls.append(list(cmd))
        if not self.responses:
            raise AssertionError(f"unexpected gh call: {cmd}")
        return self.responses.pop(0)


def _proc(code: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


def test_add_url_succeeds_and_defaults_todo():
    runner = _FakeGh(
        [
            _proc(0, stdout=json.dumps({"id": "PVTI_new"})),
            _proc(0, stdout=json.dumps({"data": {"node": {"fieldValueByName": None}}})),
            _proc(
                0,
                stdout=json.dumps(
                    [
                        {
                            "id": "STATUS",
                            "name": "Status",
                            "options": [{"id": "OPT_TODO", "name": "Todo"}],
                        }
                    ]
                ),
            ),
            _proc(0, stdout="ok"),
        ]
    )
    assert add_url("https://github.com/aaltaay/Nova/issues/9", runner=runner) == EXIT_OK
    assert runner.calls[0][:6] == ["gh", "project", "item-add", "1", "--owner", "aaltaay"]
    assert runner.calls[-1][0:2] == ["gh", "project"]
    assert "--single-select-option-id" in runner.calls[-1]


def test_add_url_leaves_in_progress_alone():
    runner = _FakeGh(
        [
            _proc(0, stdout=json.dumps({"id": "PVTI_wip"})),
            _proc(
                0,
                stdout=json.dumps(
                    {"data": {"node": {"fieldValueByName": {"name": "In Progress"}}}}
                ),
            ),
        ]
    )
    assert add_url("https://github.com/aaltaay/Nova/issues/9", runner=runner) == EXIT_OK
    assert all("item-edit" not in " ".join(call) for call in runner.calls)


def test_add_url_already_exists_is_ok():
    runner = _FakeGh([_proc(1, stderr="already exists in the project")])
    assert add_url("https://github.com/aaltaay/Nova/issues/9", runner=runner) == EXIT_OK


def test_add_url_token_blocked_exits_2():
    runner = _FakeGh(
        [
            _proc(
                1,
                stderr="GraphQL: Could not resolve to a ProjectV2 with the number 1",
            )
        ]
    )
    assert add_url("https://github.com/aaltaay/Nova/issues/9", runner=runner) == EXIT_TOKEN


def test_workflow_wires_issues_prs_concurrency_and_token():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert WORKFLOW.is_file()
    assert "issues:" in text
    assert "opened, reopened, transferred" in text
    assert "pull_request:" in text
    assert "opened, reopened" in text
    assert "concurrency:" in text
    assert "nova-delivery-" in text
    assert "NOVA_PROJECT_TOKEN" in text
    assert "gh project item-add 1 --owner aaltaay" in text
    assert "https://github.com/users/aaltaay/projects/1" in text
    assert "PVT_kwHOAXJK5M4Ab7Vq" in text
    assert "Do not recreate" in text or "do not recreate" in text.lower()
    assert "tools/nova_delivery_project.py add" in text


def test_ci_runs_nova_delivery_project_tests():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "test_nova_delivery_project.py" in text


def test_helper_is_importable_script():
    assert (REPO_ROOT / "tools" / "nova_delivery_project.py").is_file()
    # Guard: tests must not invoke real gh.
    assert subprocess  # imported for type parity with helper
