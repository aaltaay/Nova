"""What the practice desk trades: the loaded real replay, and its market at the playhead.

The Sim venue has no synthetic instrument. A practice order is admitted only for
the symbol of a loaded historical download (with trades) or recorded capture,
and only once that replay has printed at the playhead (#310).
"""
from __future__ import annotations

from dataclasses import dataclass

from constants_sim import (
    SIM_NO_PRICE_CODE,
    SIM_NO_PRICE_REASON,
    SIM_NOT_RECORDED_REASON,
    SIM_NO_REPLAY_CODE,
    SIM_NO_REPLAY_REASON,
    SIM_NO_TRADES_CODE,
    SIM_NO_TRADES_REASON,
    SIM_SYMBOL_MISMATCH_CODE,
)
from sim.fill_model import Reference

HISTORICAL = "historical"
CAPTURE = "capture"


@dataclass(frozen=True)
class Loaded:
    source: str
    symbol: str
    key: tuple


def loaded() -> Loaded | None:
    """The replay the desk is trading, or ``None`` when nothing is loaded."""
    from sim import history_playback, replay

    spec = history_playback.status()
    if spec:
        key = (HISTORICAL, spec["symbol"], spec["date"], spec["start"], spec["end"])
        return Loaded(HISTORICAL, spec["symbol"], key)
    if replay.is_capture_replay():
        state = replay.status_payload()
        symbol = str(state["replay_symbol"])
        return Loaded(CAPTURE, symbol, (CAPTURE, symbol, state["replay_date"]))
    return None


def playhead_ts() -> float:
    from sim import session_clock

    return session_clock.now_et().timestamp()


def reference(symbol: str) -> Reference:
    """Last / bid / ask at the playhead for ``symbol``; unknown fields are ``None``."""
    active = loaded()
    if active is None or active.symbol != symbol:
        return Reference(None)
    if active.source == HISTORICAL:
        from sim import history_playback

        snap = history_playback.snapshot(symbol)
        if snap.get("source") == "completed_bars":
            return Reference(None)
        return Reference(snap.get("last"))
    from sim import capture_player

    now = playhead_ts()
    quote = capture_player.quote_at(now) or {}
    return Reference(capture_player.last_print_at(now), quote.get("bid"), quote.get("ask"))


def admission(symbol: str) -> tuple[bool, str, str | None]:
    """May a practice place/bracket for ``symbol`` proceed right now?"""
    active = loaded()
    if active is None:
        return False, SIM_NO_REPLAY_REASON, SIM_NO_REPLAY_CODE
    if symbol != active.symbol:
        return (
            False,
            f"Practice orders trade the loaded replay ({active.symbol}), not {symbol or 'no symbol'}",
            SIM_SYMBOL_MISMATCH_CODE,
        )
    if active.source == HISTORICAL:
        from sim import history_playback

        if history_playback.snapshot(symbol).get("source") == "completed_bars":
            return False, SIM_NO_TRADES_REASON, SIM_NO_TRADES_CODE
    else:
        from sim import capture_player

        if not capture_player.covered(playhead_ts()):
            # A gap in the recording is a stated absence, never the market from before it (R11).
            return False, SIM_NOT_RECORDED_REASON, SIM_NO_PRICE_CODE
    if reference(symbol).last is None:
        return False, SIM_NO_PRICE_REASON, SIM_NO_PRICE_CODE
    return True, "OK", None


def prints_between(symbol: str, after_ts: float, through_ts: float) -> list[tuple[float, float]]:
    """Replay prints in ``(after_ts, through_ts]`` as ``(ts, price)``, oldest first."""
    active = loaded()
    if active is None or active.symbol != symbol or through_ts <= after_ts:
        return []
    if active.source == HISTORICAL:
        from sim import history_playback

        return history_playback.prints_between(symbol, after_ts, through_ts)
    from sim import capture_player
    from sim.capture_spans import is_odd_lot

    # Odd lots never fill a practice order -- the historical path's ``unreported`` rule (R24).
    return [
        (float(row["ts"]), float(row["price"]))
        for row in capture_player.prints_since(after_ts, through_ts)
        if row.get("price") is not None and not is_odd_lot(row)
    ]
