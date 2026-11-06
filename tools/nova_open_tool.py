"""The ``open_in_nova`` tool. The unified server registers it; this file owns the call.

The tool posts to the desk. It does not place, change, or cancel an order.
Symbol, date, and as_of are checked here first, so a bad value is BAD_REQUEST
even when the desk process is down. The rules match ``agent_desk.open_in_nova.parse_payload``.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import nova_open_client as open_client

OPEN_ARGUMENTS = frozenset({"symbol", "date", "as_of"})
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")
_AS_OF_ERROR = "as_of must be HH:MM or HH:MM:SS ET between 04:00:00 and 20:00:00"
_OPEN_MIN = 4 * 3600
_CLOSE_MAX = 20 * 3600


def argument_error(symbol: object, day: object, as_of: object) -> str | None:
    if not isinstance(symbol, str) or not _SYMBOL.match(symbol.strip().upper()):
        return "symbol must be a ticker (A-Z, dot, dash, at most 10)"
    if not isinstance(day, str) or not _DATE.match(day.strip()):
        return "date must be YYYY-MM-DD"
    try:
        date.fromisoformat(day.strip())
    except ValueError:
        return "date must be YYYY-MM-DD"
    if as_of is None or as_of == "":
        return None
    if not isinstance(as_of, str):
        return _AS_OF_ERROR
    match = _CLOCK.match(as_of.strip())
    if match is None:
        return _AS_OF_ERROR
    hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    stamp = hour * 3600 + minute * 60 + second
    if stamp < _OPEN_MIN or stamp > _CLOSE_MAX:
        return _AS_OF_ERROR
    return None


def open_message(body: dict[str, Any]) -> tuple[str, bool]:
    if body.get("ok") is True and isinstance(body.get("chat_message"), str):
        return body["chat_message"], False
    reason = str(body.get("reason") or "BAD_REQUEST")
    detail = str(body.get("error") or "")
    if reason == "DESK_NOT_RUNNING":
        return detail or open_client.DESK_NOT_RUNNING_TEXT, True
    if reason == "DESK_OUT_OF_DATE":
        return detail or open_client.DESK_OUT_OF_DATE_TEXT, True
    if reason == "UNKNOWN_ARGUMENT":
        return f"UNKNOWN_ARGUMENT {detail}".strip(), True
    return f"{reason} {detail}".strip(), True


def register(server, *, writes, guard, result, error_result, open_transport=None) -> None:
    import anyio

    def run_open(symbol: str, date: str, as_of: str | None) -> Any:
        bad = argument_error(symbol, date, as_of)
        if bad is not None:
            body: dict[str, Any] = {"ok": False, "reason": "BAD_REQUEST", "error": bad}
        else:
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
