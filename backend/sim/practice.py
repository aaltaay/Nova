"""What the practice desk trades: the loaded real replay, and its market at the playhead.

The Sim venue has no synthetic instrument. A practice order is admitted only for
the symbol of a loaded historical download (with trades) or recorded capture,
and only once that replay has printed at the playhead (#310). A playhead whose
own second is not in the data -- a gap in a recording (R11), or a stretch of a
historical window the download has not covered (R34) -- has no market: the
reference carries no price there, so an order is refused ``SIM_NO_PRICE`` and a
protective close gets flat at the last mark (``last_mark``). A candle close is
never passed off as a print.
"""
from __future__ import annotations

from dataclasses import dataclass

from constants_sim import (
    SIM_NO_PRICE_CODE,
    SIM_NO_PRICE_REASON,
    SIM_NOT_DOWNLOADED_REASON,
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


def _before_window(snap: dict) -> bool:
    """The playhead has not reached the window yet: nothing has printed, rather than "not downloaded"."""
    start = (snap.get("selection") or {}).get("start_ts")
    try:
        return start is not None and playhead_ts() < float(start)
    except (TypeError, ValueError):
        return False


def reference(symbol: str) -> Reference:
    """Last / bid / ask at the playhead for ``symbol``; unknown fields are ``None``."""
    active = loaded()
    if active is None or active.symbol != symbol:
        return Reference(None)
    if active.source == HISTORICAL:
        from sim import history_playback

        snap = history_playback.snapshot(symbol)
        if snap.get("source") == "completed_bars" or snap.get("covered") is False:
            # Not downloaded here: the snapshot's last is a candle close (R34).
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

        snap = history_playback.snapshot(symbol)
        if snap.get("source") == "completed_bars":
            return False, SIM_NO_TRADES_REASON, SIM_NO_TRADES_CODE
        if snap.get("covered") is False and not _before_window(snap):
            # An undownloaded stretch is a stated absence, never a candle close (R34).
            return False, SIM_NOT_DOWNLOADED_REASON, SIM_NO_PRICE_CODE
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
    from sale_conditions import row_sets_price
    from sim import capture_player

    # Only prints that set a price fill a practice order -- never an odd lot or an
    # average-price print (R24, #511); the historical path drops ``unreported`` rows.
    return [
        (float(row["ts"]), float(row["price"]))
        for row in capture_player.prints_since(after_ts, through_ts)
        if row.get("price") is not None and row_sets_price(row)
    ]
