"""Optional MCP/SDK adapter contract (#222).

The adapters are *clients* of the localhost OpenAPI -- never the core brain.
These tests pin the promises in `bot/mcp_adapter.py`'s docstring so the map
cannot drift away from the real routes, and so no future edit can quietly
give an adapter its own execution door or its own autonomy switch.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from auth import require_bot_auth
from bot import mcp_adapter, sdk
from bot.http import require_loopback
from main import app
from bot.client import BotApiClient

BOT_ACTION_PATH = "/api/bot/action"
_BACKEND = Path(__file__).resolve().parents[1]


def _route(method: str, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", ()):
            return route
    return None


def _dependency_callables(route) -> set:
    return {dep.dependency for dep in getattr(route, "dependencies", [])}


def _entries():
    return tuple(mcp_adapter.TOOLS) + tuple(mcp_adapter.DESK_ONLY)


def test_tool_names_are_unique_and_desk_tools_are_not_adapter_tools():
    tool_names = [entry["name"] for entry in mcp_adapter.TOOLS]
    desk_names = [entry["name"] for entry in mcp_adapter.DESK_ONLY]
    assert len(tool_names) == len(set(tool_names))
    assert len(desk_names) == len(set(desk_names))
    # Arming and autonomy stay desk-only: an adapter must not be able to raise level.
    assert set(tool_names).isdisjoint(desk_names)


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["name"])
def test_every_declared_tool_maps_to_a_real_route(entry):
    route = _route(entry["method"], entry["path"])
    assert route is not None, f"{entry['name']} -> {entry['method']} {entry['path']} is not served"


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["name"])
def test_every_adapter_path_stays_inside_the_bot_api(entry):
    # Adapters never talk to /api/trading, /api/ibkr or any other door.
    assert entry["path"].startswith("/api/bot/")


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["name"])
def test_every_adapter_route_is_loopback_gated(entry):
    route = _route(entry["method"], entry["path"])
    assert require_loopback in _dependency_callables(route)


@pytest.mark.parametrize("entry", mcp_adapter.TOOLS, ids=lambda e: e["name"])
def test_declared_auth_matches_the_route(entry):
    route = _route(entry["method"], entry["path"])
    needs_key = require_bot_auth in _dependency_callables(route)
    assert needs_key is entry["auth"], (
        f"{entry['name']} declares auth={entry['auth']} but the route "
        f"{'requires' if needs_key else 'does not require'} the API key"
    )


@pytest.mark.parametrize("entry", mcp_adapter.DESK_ONLY, ids=lambda e: e["name"])
def test_desk_only_tools_require_the_api_key(entry):
    route = _route(entry["method"], entry["path"])
    assert require_bot_auth in _dependency_callables(route)


def test_execution_reaches_the_broker_only_through_post_bot_action():
    placing = [e for e in _entries() if e["path"] == BOT_ACTION_PATH]
    assert [e["name"] for e in placing] == ["bot_action"]
    assert placing[0]["method"] == "POST"
    assert placing[0]["auth"] is True


def test_tool_maps_are_immutable_tuples():
    assert isinstance(mcp_adapter.TOOLS, tuple)
    assert isinstance(mcp_adapter.DESK_ONLY, tuple)


def test_adapter_module_starts_no_server():
    # "Do not start an MCP server from this module" -- no run/serve entry point.
    for forbidden in ("serve", "run", "main", "app"):
        assert not hasattr(mcp_adapter, forbidden)


def test_client_is_an_http_client_not_a_brain():
    made = mcp_adapter.client(base="http://127.0.0.1:8000", api_key="k", brain_id="b")
    assert isinstance(made, BotApiClient)
    assert made.base == "http://127.0.0.1:8000"


def test_sdk_reexports_the_same_objects():
    assert sdk.TOOLS is mcp_adapter.TOOLS
    assert sdk.DESK_ONLY is mcp_adapter.DESK_ONLY
    assert sdk.client is mcp_adapter.client
    assert set(sdk.__all__) == {"BotApiClient", "DESK_ONLY", "TOOLS", "client"}


@pytest.mark.parametrize(
    "source",
    [
        _BACKEND / "routes" / "bot.py",
        _BACKEND / "routes" / "bot_ws.py",
        _BACKEND / "bot" / "actions.py",
        _BACKEND / "bot" / "client.py",
    ],
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_core_paths_do_not_import_the_optional_adapters(source):
    text = source.read_text(encoding="utf-8")
    assert "mcp_adapter" not in text, f"{source.name} imports the optional adapter"
    assert "from bot.sdk" not in text and "import bot.sdk" not in text
