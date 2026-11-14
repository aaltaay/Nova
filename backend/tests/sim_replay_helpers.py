"""A real historical window loaded into the Sim, for the tests that read a replay at its playhead (ADR 052).

The IBKR download path: prints, no quotes. ``load_window`` loads IMCC 07:00-10:00 on ``DAY`` with ``TAPE`` and
pauses the playhead; ``go`` moves the playhead (paused there) and lets the Sim feed match what rests. Moved here
from the strategy bot's Sim replay tests when the bot retired (ADR 072).
"""
from __future__ import annotations

from sim import feed
from sim import history_playback as playback, history_store as store, session_clock as clock

DAY = "2026-09-18"
SYM = "IMCC"
# 07:00:10 10.00 · 07:00:30 11.00 · 07:00:32 10.40 · 07:01:00 12.00 · 07:01:30 10.00
TAPE = [(10, 10.00), (30, 11.00), (32, 10.40), (60, 12.00), (90, 10.00)]


def load_window() -> dict:
    spec = store.window(SYM, DAY, "07:00", "10:00")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    store.commit_page(job["id"], a, [dict(ts=a + sec, price=px, size=100) for sec, px in TAPE], spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    return spec


def go(sec: float) -> None:
    """The operator moves the playhead (paused there); the Sim feed matches what rests."""
    clock.scrub_to_second(sec)
    clock.set_paused(True)
    feed.match_practice_fills()
