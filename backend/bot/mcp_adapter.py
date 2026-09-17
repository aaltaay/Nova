"""Optional MCP/SDK adapter contract -- not imported by routes or nova_brain.

Maps MCP-style tool names to the localhost OpenAPI. Adapters never raise
autonomy and never place except via POST /api/bot/action. Do not start an
MCP server from this module. Do not marry a model vendor.
"""
from __future__ import annotations

from nova_brain.client import BotApiClient

TOOLS = (
    {"name": "bot_session_get", "method": "GET", "path": "/api/bot/session", "auth": False},
    {"name": "bot_watch", "method": "GET", "path": "/api/bot/watch", "auth": False},
    {"name": "bot_session_claim", "method": "POST", "path": "/api/bot/session/claim", "auth": True},
    {"name": "bot_heartbeat", "method": "POST", "path": "/api/bot/session/heartbeat", "auth": True},
    {"name": "bot_action", "method": "POST", "path": "/api/bot/action", "auth": True},
    {"name": "bot_propose", "method": "POST", "path": "/api/bot/proposals", "auth": True},
)

DESK_ONLY = (
    {"name": "bot_arm", "method": "POST", "path": "/api/bot/session/arm"},
    {"name": "bot_disarm", "method": "POST", "path": "/api/bot/session/disarm"},
    {"name": "bot_session_patch", "method": "PATCH", "path": "/api/bot/session"},
)


def client(**kwargs) -> BotApiClient:
    return BotApiClient(**kwargs)
