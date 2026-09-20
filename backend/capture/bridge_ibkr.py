"""AllLast feeder; all disk writes run on the existing fenced capture worker."""

from datetime import datetime
from zoneinfo import ZoneInfo

from capture import worker


def enqueue_print(payload) -> None:
    token = worker.session_token(payload["symbol"])
    if token is not None:
        worker.submit(_write_print, dict(payload), token=token)


def _write_print(payload: dict) -> None:
    from capture import bar_buckets, recorder

    payload["session_date"] = datetime.fromtimestamp(payload["ts"], ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    recorder.record_print(payload)
    bar_buckets.on_print(
        payload["symbol"],
        payload["ts"],
        payload["price"],
        payload["size"],
        source=payload["source"],
        session_date=payload["session_date"],
    )


def producer_health(symbol: str) -> dict:
    from ibkr import tape_stream
    from ibkr import client
    from ibkr.tape_recording import producer_status

    state = producer_status(symbol)
    if not tape_stream.is_subscribed(symbol) or client.get_ib() is None:
        return state | {
            "state": "disconnected",
            "healthy": False,
            "error": "IBKR AllLast is not connected/subscribed for " + symbol,
        }
    return state


def admission_error(symbol: str) -> str | None:
    from constants_sim import SIM_SYMBOL

    if symbol == SIM_SYMBOL:
        return None
    return producer_health(symbol).get("error")
