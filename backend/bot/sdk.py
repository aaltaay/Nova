"""Thin optional SDK for MCP / Astra / Fable adapters.

Adapters are clients of the localhost OpenAPI. This module is not the brain
and does not raise autonomy. Do not marry Nova to Grok -- any model can
call the same HTTP contract documented in docs/bot-localhost-api.md.
"""
from __future__ import annotations

from bot.mcp_adapter import DESK_ONLY, TOOLS, client
from nova_brain.client import BotApiClient

__all__ = ["BotApiClient", "DESK_ONLY", "TOOLS", "client"]
