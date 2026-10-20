"""The ``open_in_nova`` tool. The unified server registers it; this file owns the call.

The tool posts to the desk. It does not place, change, or cancel an order.
"""
from __future__ import annotations

from typing import Any

import nova_open_client as open_client

OPEN_ARGUMENTS = frozenset({"symbol", "date", "as_of"})


def open_message(body: dict[str, Any]) -> tuple[str, bool]:
    if body.get("ok") is True and isinstance(body.get("chat_message"), str):
        return body["chat_message"], False
    reason = str(body.get("reason") or "BAD_REQUEST")
    detail = str(body.get("error") or "")
    if reason == "DESK_NOT_RUNNING":
        return detail or open_client.DESK_NOT_RUNNING_TEXT, True
    if reason == "UNKNOWN_ARGUMENT":
        return f"UNKNOWN_ARGUMENT {detail}".strip(), True
    return f"{reason} {detail}".strip(), True


def register(server, *, writes, guard, result, error_result, open_transport=None) -> None:
    import anyio

    def run_open(symbol: str, date: str, as_of: str | None) -> Any:
        payload: dict[str, Any] = {"symbol": symbol, "date": date}
        if as_of:
            payload["as_of"] = as_of
        transport = open_transport or open_client.post_open
        try:
            body = transport(payload)
        except OSError:
            body = {"ok": False, "reason": "DESK_NOT_RUNNING", "error": open_client.DESK_NOT_RUNNING_TEXT}
        if not isinstance(body, dict):
            body = {"ok": False, "reason": "BAD_REQUEST", "error": "the desk answer was not JSON"}
        message, failed = open_message(body)
        structured = {
            "ok": not failed,
            "chat_message": message,
            "symbol": body.get("symbol") or str(symbol).upper(),
            "date": body.get("date") or str(date),
            "as_of": body.get("as_of"),
            "paused": body.get("paused") if not failed else None,
            "separate_sim": body.get("separate_sim") if not failed else None,
        }
        if failed:
            structured["error"] = {
                "code": str(body.get("reason") or "BAD_REQUEST"),
                "detail": str(body.get("error") or message),
            }
            return error_result(message, structured)
        return result(message, structured, [])

    @server.tool(name="open_in_nova", annotations=writes)
    async def open_in_nova(symbol: str, date: str, as_of: str | None = None):
        """Open one ticker in Nova Sim, paused. Post chat_message verbatim.

        symbol: ticker. date: YYYY-MM-DD. as_of: HH:MM or HH:MM:SS Eastern, optional.
        No other arguments. The server opens the desk. This does not place, change, or cancel an order."""
        return await anyio.to_thread.run_sync(lambda: run_open(symbol, date, as_of))

    guard(server._tool_manager.get_tool("open_in_nova"), OPEN_ARGUMENTS)
