#!/usr/bin/env python3
"""Add issues/PRs to the existing Nova Delivery user project.

Do not recreate this board. Open items belong on:

  https://github.com/users/aaltaay/projects/1
  title Nova Delivery, id PVT_kwHOAXJK5M4Ab7Vq, number 1, owner aaltaay

Classic GITHUB_TOKEN and the Cloud Agent GitHub App typically cannot write
user-owned Projects v2. Owner ``gh`` as aaltaay can. Actions should use
repo secret NOVA_PROJECT_TOKEN (classic PAT scopes: project, repo).

Usage:
  python3 tools/nova_delivery_project.py add --url https://github.com/aaltaay/Nova/issues/1
  python3 tools/nova_delivery_project.py token-help
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable

PROJECT_NUMBER = 1
PROJECT_OWNER = "aaltaay"
PROJECT_ID = "PVT_kwHOAXJK5M4Ab7Vq"
PROJECT_URL = "https://github.com/users/aaltaay/projects/1"
PROJECT_TITLE = "Nova Delivery"
STATUS_FIELD_NAME = "Status"
STATUS_TODO = "Todo"
STATUS_IN_PROGRESS = "In Progress"
STATUS_DONE = "Done"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_TOKEN = 2

TOKEN_HELP = f"""\
Nova Delivery already exists -- do not recreate it.
  Board: {PROJECT_URL}
  title {PROJECT_TITLE}, id {PROJECT_ID}, number {PROJECT_NUMBER}, owner {PROJECT_OWNER}

This token cannot write that user-owned Project (Projects v2).
Classic GITHUB_TOKEN and the Cloud Agent GitHub App typically lack `project`
scope. Owner `gh` logged in as {PROJECT_OWNER} can mutate.

For GitHub Actions:
  1. As {PROJECT_OWNER}, create a classic PAT with scopes: project, repo
     (fine-grained: Project "{PROJECT_TITLE}" Read/Write plus Issues and PRs).
  2. Repo Settings -> Secrets and variables -> Actions -> New repository secret
  3. Name: NOVA_PROJECT_TOKEN
  4. Re-run the Nova Delivery project workflow.

Agents: report this limitation. Never claim the issue is on the board.
Never run `gh project create`. Priority stays on labels P0-P3.
"""

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class GhResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class StatusField:
    field_id: str
    todo_option_id: str


def item_add_command(url: str) -> list[str]:
    return [
        "gh",
        "project",
        "item-add",
        str(PROJECT_NUMBER),
        "--owner",
        PROJECT_OWNER,
        "--url",
        url,
        "--format",
        "json",
    ]


def field_list_command() -> list[str]:
    return [
        "gh",
        "project",
        "field-list",
        str(PROJECT_NUMBER),
        "--owner",
        PROJECT_OWNER,
        "--format",
        "json",
    ]


def item_edit_status_command(item_id: str, field_id: str, option_id: str) -> list[str]:
    return [
        "gh",
        "project",
        "item-edit",
        "--id",
        item_id,
        "--project-id",
        PROJECT_ID,
        "--field-id",
        field_id,
        "--single-select-option-id",
        option_id,
    ]


def is_already_on_board(stderr: str) -> bool:
    text = (stderr or "").lower()
    needles = (
        "already exists",
        "already in the project",
        "already in this project",
        "duplicate project item",
    )
    return any(needle in text for needle in needles)


def is_project_token_blocked(stderr: str) -> bool:
    text = (stderr or "").lower()
    needles = (
        "403",
        "forbidden",
        "resource not accessible",
        "not accessible by integration",
        "could not resolve to a projectv2",
        "insufficient scope",
        "insufficient_scope",
        "requires authentication",
        "project scope",
        "projects are disabled",
    )
    return any(needle in text for needle in needles)


def should_default_status_to_todo(current: str | None) -> bool:
    name = (current or "").strip()
    if not name:
        return True
    if name == STATUS_IN_PROGRESS:
        return False
    if name == STATUS_TODO:
        return False
    if name == STATUS_DONE:
        return True
    return False


def parse_item_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        raw = payload.get("id") or payload.get("itemId")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def find_status_field(fields: Any) -> StatusField | None:
    rows = fields
    if isinstance(fields, dict):
        rows = fields.get("fields") or fields.get("items") or []
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("name") or "").strip() != STATUS_FIELD_NAME:
            continue
        field_id = str(row.get("id") or "").strip()
        todo_id = ""
        for option in row.get("options") or []:
            if not isinstance(option, dict):
                continue
            if str(option.get("name") or "").strip() == STATUS_TODO:
                todo_id = str(option.get("id") or "").strip()
        if field_id and todo_id:
            return StatusField(field_id=field_id, todo_option_id=todo_id)
    return None


def parse_status_name(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    node = payload.get("data", {}).get("node") if "data" in payload else payload
    if not isinstance(node, dict):
        return None
    value = node.get("fieldValueByName")
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _run(cmd: list[str], runner: Runner | None) -> GhResult:
    run = runner or subprocess.run
    proc = run(cmd, capture_output=True, text=True, check=False)
    return GhResult(
        returncode=int(proc.returncode),
        stdout=str(proc.stdout or ""),
        stderr=str(proc.stderr or ""),
    )


def _parse_json(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def current_status_command(item_id: str) -> list[str]:
    query = (
        "query($id:ID!){node(id:$id){... on ProjectV2Item{"
        "fieldValueByName(name:\"Status\"){"
        "... on ProjectV2ItemFieldSingleSelectValue{name}}}}}"
    )
    return ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"id={item_id}"]


def add_url(url: str, *, runner: Runner | None = None) -> int:
    target = (url or "").strip()
    if not target:
        print("Missing --url (issue or PR html_url).", file=sys.stderr)
        return EXIT_ERROR

    added = _run(item_add_command(target), runner)
    item_id = parse_item_id(_parse_json(added.stdout))
    if added.returncode != 0:
        err = added.stderr or added.stdout
        if is_already_on_board(err):
            print(f"already-on-board url={target}")
        elif is_project_token_blocked(err):
            print(TOKEN_HELP, file=sys.stderr)
            print(err, file=sys.stderr)
            return EXIT_TOKEN
        else:
            print(err or "gh project item-add failed", file=sys.stderr)
            return EXIT_ERROR
    else:
        print(f"added item_id={item_id or 'unknown'} url={target}")

    if not item_id:
        return EXIT_OK

    status_raw = _run(current_status_command(item_id), runner)
    status_name = parse_status_name(_parse_json(status_raw.stdout))
    if not should_default_status_to_todo(status_name):
        print(f"status-unchanged status={status_name or 'unknown'}")
        return EXIT_OK

    fields = _run(field_list_command(), runner)
    if fields.returncode != 0:
        print(
            f"item is on the board; Status default skipped: {fields.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_OK
    status_field = find_status_field(_parse_json(fields.stdout))
    if status_field is None:
        print("item is on the board; Status field Todo option not found", file=sys.stderr)
        return EXIT_OK

    edited = _run(
        item_edit_status_command(
            item_id, status_field.field_id, status_field.todo_option_id
        ),
        runner,
    )
    if edited.returncode != 0:
        print(
            f"item is on the board; Status Todo set failed: {edited.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_OK
    print(f"status-defaulted status={STATUS_TODO}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    add_p = sub.add_parser("add", help="Add an issue or PR URL to Nova Delivery")
    add_p.add_argument("--url", required=True, help="Issue or PR html_url")
    sub.add_parser("token-help", help="Print the NOVA_PROJECT_TOKEN setup text")
    args = parser.parse_args(argv)
    if args.cmd == "token-help":
        print(TOKEN_HELP)
        return EXIT_OK
    return add_url(args.url)


if __name__ == "__main__":
    raise SystemExit(main())
