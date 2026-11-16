"""Optional MCP/SDK adapter contract -- not imported by routes.

Maps MCP-style tool names to the localhost OpenAPI. Adapters never raise
autonomy and never place except via POST /api/bot/action (the brain's door to be,
ADR 072; it sends nothing yet). ADR 072 retired proposals. Do not start an
MCP server from this module. Do not marry a model vendor.
"""
from __future__ import annotations

from bot.client import BotApiClient

TOOLS = (
    {"name": "bot_session_get", "method": "GET", "path": "/api/bot/session", "auth": False},
    {"name": "bot_watch", "method": "GET", "path": "/api/bot/watch", "auth": False},
    {"name": "bot_session_claim", "method": "POST", "path": "/api/bot/session/claim", "auth": True},
    {"name": "bot_heartbeat", "method": "POST", "path": "/api/bot/session/heartbeat", "auth": True},
    {"name": "bot_action", "method": "POST", "path": "/api/bot/action", "auth": True},
)

# The desk-only routes an adapter must never call. ADR 072 retired the last of them -- Activate, Stop and the
# session's PATCH went with the Bot switch -- so the bot API has none left.
DESK_ONLY: tuple[dict[str, str], ...] = ()


def client(**kwargs) -> BotApiClient:
    return BotApiClient(**kwargs)
